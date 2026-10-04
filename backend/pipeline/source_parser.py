"""No Django, database or provider access. Production calls this in the offline parser container."""

import csv
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

MAX_BYTES = 25 * 1024 * 1024
MAX_CHARS = 2_000_000
MAX_BLOCKS = 20_000
MAX_DOCX_EXPANDED = 100 * 1024**2
MAX_DOCX_XML = 16 * 1024**2
PARSER_VERSION = "r3-ocr-v1/native-under20/pdfplumber-0.11.10"
OCR_LANGUAGES = {"eng", "nep", "eng+nep"}


class InvalidSource(ValueError):
    pass


def validate_bytes(data, kind):
    if not data or len(data) > MAX_BYTES:
        raise InvalidSource("Choose a nonempty file no larger than 25 MiB.")
    if kind == "PDF":
        if not data.startswith(b"%PDF-"):
            raise InvalidSource("This file does not have a PDF signature.")
        return None
    if kind == "DOCX":
        if not data.startswith(b"PK\x03\x04"):
            raise InvalidSource("This file does not have a DOCX ZIP signature.")
        return None
    if kind not in {"TXT", "MD"}:
        raise InvalidSource("Only PDF, DOCX and UTF-8 TXT/Markdown files are supported.")
    if data.startswith((b"MZ", b"\x7fELF", b"PK", b"%PDF-")):
        raise InvalidSource("This file is not plain UTF-8 text.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InvalidSource("Save text files using UTF-8 encoding.") from error
    if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
        raise InvalidSource("Binary control characters are not allowed in text files.")
    if text.lstrip().lower().startswith(("<!doctype html", "<html", "<script", "<?xml")):
        raise InvalidSource("Upload plain text, not an HTML or XML document.")
    if not text.strip() or len(text) > MAX_CHARS:
        raise InvalidSource("Text must be nonempty and at most 2 million characters.")
    return text


def block(original, text, locator):
    # Identity normalization preserves combining marks and exact Unicode code-point offsets.
    # TXT line terminators remain in originalText but are excluded from canonical text.
    return {
        "originalText": original,
        "text": text,
        "locator": locator,
        "spanMap": [[0, len(text), 0, len(text)]],
    }


def page_timeout(_signum, _frame):
    raise InvalidSource("A page exceeded the 30-second extraction limit.")


def extract_docx(path):
    """Read document text only; never extract ZIP paths or resolve relationships."""
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > 10_000 or len(set(names)) != len(names):
                raise InvalidSource("The DOCX has too many or duplicate ZIP entries.")
            if sum(entry.file_size for entry in entries) > MAX_DOCX_EXPANDED:
                raise InvalidSource("The DOCX exceeds the 100 MiB expanded size limit.")
            for entry in entries:
                name = entry.filename
                if (
                    PurePosixPath(name).is_absolute()
                    or ".." in PurePosixPath(name).parts
                    or "\\" in name
                    or ":" in name
                    or entry.flag_bits & 1
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000
                    or "vbaproject" in name.lower()
                ):
                    raise InvalidSource("Unsafe, encrypted or macro-enabled DOCX entries.")

            def xml(name):
                if archive.getinfo(name).file_size > MAX_DOCX_XML:
                    raise InvalidSource("A DOCX XML part exceeds 16 MiB.")
                with archive.open(name) as stream:
                    data = stream.read(MAX_DOCX_XML + 1)
                if len(data) > MAX_DOCX_XML:
                    raise InvalidSource("A DOCX XML part exceeds 16 MiB.")
                return ElementTree.fromstring(data, forbid_dtd=True)

            types = xml("[Content_Types].xml")
            expected_type = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
            )
            if not any(
                item.get("PartName") == "/word/document.xml"
                and item.get("ContentType") == expected_type
                for item in types
            ):
                raise InvalidSource("Upload a standard DOCX document, not another ZIP format.")
            relationships = xml("_rels/.rels")
            main = [r for r in relationships if r.get("Type", "").endswith("/officeDocument")]
            if (
                len(main) != 1
                or main[0].get("Target") not in {"word/document.xml", "/word/document.xml"}
                or main[0].get("TargetMode") == "External"
            ):
                raise InvalidSource("The DOCX main document relationship is unsupported.")
            root = xml("word/document.xml")
    except (BadZipFile, KeyError, RuntimeError, NotImplementedError) as error:
        raise InvalidSource("The DOCX archive is damaged, encrypted or unsupported.") from error
    except (ParseError, DefusedXmlException) as error:
        raise InvalidSource("The DOCX contains invalid or unsafe XML.") from error

    namespace = root.tag.removesuffix("document")
    if namespace not in {
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}",
        "{http://purl.oclc.org/ooxml/wordprocessingml/main}",
    }:
        raise InvalidSource("The DOCX document XML namespace is unsupported.")
    body = root.find(f"{namespace}body")
    if body is None:
        raise InvalidSource("The DOCX has no document body.")
    paragraphs = {id(p): index for index, p in enumerate(body.iter(f"{namespace}p"), 1)}
    headings, blocks, warnings = [], [], set()
    chars = 0
    if any(re.match(r"word/(header|footer|footnotes|endnotes|comments)", n) for n in names):
        warnings.add("Headers, footers, notes and comments are not extracted. Review the original.")

    def paragraph(element, cell=None):
        nonlocal chars, headings
        parts, pending = [], [element]
        while pending:
            node = pending.pop()
            tag = node.tag.removeprefix(namespace)
            if tag in {"drawing", "pict", "object", "del", "altChunk", "txbxContent"}:
                warnings.add(
                    "Some embedded or revised content is not extracted. Review the original."
                )
                continue
            if tag in {
                "ins",
                "sdt",
                "fldSimple",
                "instrText",
                "numPr",
                "sym",
                "vanish",
            } or tag.startswith("{"):
                warnings.add(
                    "Fields, numbering, revisions or special formatting need review in the source."
                )
            if tag == "t":
                parts.append(node.text or "")
            elif tag in {"tab", "br", "cr"}:
                parts.append("\t" if tag == "tab" else "\n")
            elif tag in {"noBreakHyphen", "softHyphen"}:
                parts.append("\u2011" if tag == "noBreakHyphen" else "\u00ad")
            pending.extend(reversed(list(node)))
        text = "".join(parts)
        if not text.strip():
            return
        chars += len(text)
        if chars > MAX_CHARS or len(blocks) >= MAX_BLOCKS:
            raise InvalidSource("The DOCX exceeds the extracted text limit.")
        style = element.find(f"{namespace}pPr/{namespace}pStyle")
        match = (
            re.fullmatch(r"Heading([1-9])", style.get(f"{namespace}val", ""))
            if style is not None
            else None
        )
        if match and cell is None:
            level = int(match[1])
            headings = [(n, label) for n, label in headings if n < level] + [(level, text[:240])]
        locator = {
            "paragraph": paragraphs[id(element)],
            "headingPath": [label for _, label in headings],
            **(cell or {}),
        }
        blocks.append(block(text, text, locator))

    table = 0
    for child in body:
        if child.tag == f"{namespace}p":
            paragraph(child)
        elif child.tag == f"{namespace}tbl":
            table += 1
            if any(
                n.tag not in {f"{namespace}{t}" for t in ("tr", "tblPr", "tblGrid")} for n in child
            ):
                warnings.add("Unsupported table content was omitted. Review the original.")
            for row_index, row in enumerate(child.findall(f"{namespace}tr"), 1):
                if any(n.tag not in {f"{namespace}tc", f"{namespace}trPr"} for n in row):
                    warnings.add("Unsupported table content was omitted. Review the original.")
                for cell_index, cell in enumerate(row.findall(f"{namespace}tc"), 1):
                    for item in cell:
                        if item.tag == f"{namespace}p":
                            paragraph(item, {"table": table, "row": row_index, "cell": cell_index})
                        elif item.tag != f"{namespace}tcPr":
                            warnings.add(
                                "Nested tables or cell content were omitted. Review the original."
                            )
        elif child.tag != f"{namespace}sectPr":
            warnings.add("Unsupported document sections were omitted. Review the original.")
    if not blocks:
        raise InvalidSource("The DOCX has no supported body text.")
    return blocks, sorted(warnings)


def read_ocr_tsv(path, width, height, page):
    if path.stat().st_size > 8 * 1024**2:
        raise InvalidSource("OCR output exceeds its size limit.")
    lines, scores, characters = {}, [], 0
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            for index, row in enumerate(
                csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
            ):
                if index > 200_000:
                    raise InvalidSource("OCR output exceeds its word limit.")
                if row["level"] != "5" or not row["text"].strip():
                    continue
                text = row["text"]
                confidence = float(row["conf"])
                x, y, w, h = (int(row[key]) for key in ("left", "top", "width", "height"))
                if not (
                    0 <= confidence <= 100 and 0 <= x < x + w <= width and 0 <= y < y + h <= height
                ):
                    raise InvalidSource("Invalid OCR word location or confidence.")
                key = tuple(int(row[k]) for k in ("block_num", "par_num", "line_num"))
                if min(key) < 1:
                    raise InvalidSource("Invalid OCR line reference.")
                entry = lines.setdefault(
                    key, {"words": [], "box": [x, y, x + w, y + h], "scores": []}
                )
                entry["words"].append(text)
                entry["scores"].append(confidence)
                box = entry["box"]
                entry["box"] = [
                    min(box[0], x),
                    min(box[1], y),
                    max(box[2], x + w),
                    max(box[3], y + h),
                ]
                scores.append(confidence)
                characters += len(text) + 1
                if characters > MAX_CHARS or len(lines) > MAX_BLOCKS:
                    raise InvalidSource("OCR text exceeds its content limit.")
    except (KeyError, TypeError, ValueError, csv.Error, UnicodeError) as error:
        raise InvalidSource("Invalid OCR output.") from error
    blocks = []
    for entry in lines.values():
        text = " ".join(entry["words"])
        x0, y0, x1, y1 = entry["box"]
        blocks.append(
            block(
                text,
                text,
                {
                    "page": page,
                    "bbox": [x0 / width, y0 / height, x1 / width, y1 / height],
                    "method": "OCR",
                    "confidence": round(sum(entry["scores"]) / len(entry["scores"]), 2),
                },
            )
        )
    return blocks, round(sum(scores) / len(scores), 2) if scores else None


def ocr_page(image, width, height, page, language, timeout):
    executable = shutil.which("tesseract")
    if not executable or language not in OCR_LANGUAGES:
        raise InvalidSource("OCR is unavailable for the selected language.")
    base = image.parent / f"ocr-{page}"
    deadline = time.monotonic() + timeout
    try:
        version = (
            subprocess.run(
                [executable, "--version"],
                capture_output=True,
                check=True,
                timeout=min(3, timeout),
            )
            .stdout.decode("utf-8", errors="replace")
            .splitlines()[0][:80]
        )
        subprocess.run(
            [executable, str(image), str(base), "-l", language, "--oem", "1", "--psm", "3", "tsv"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={"PATH": os.environ.get("PATH", os.defpath), "OMP_THREAD_LIMIT": "1"},
            timeout=max(0.01, deadline - time.monotonic()),
            check=True,
        )
        blocks, confidence = read_ocr_tsv(base.with_suffix(".tsv"), width, height, page)
        return blocks, confidence, version
    except (OSError, subprocess.SubprocessError, IndexError) as error:
        raise InvalidSource(
            "OCR failed or exceeded its page deadline. Review or exclude this page."
        ) from error
    finally:
        base.with_suffix(".tsv").unlink(missing_ok=True)


def extract(path, kind, output, ocr_language="eng"):
    if ocr_language not in OCR_LANGUAGES:
        raise InvalidSource("Choose English, Nepali or English + Nepali for OCR.")
    path, output = Path(path), Path(output)
    if path.stat().st_size > MAX_BYTES:
        raise InvalidSource("The file exceeds 25 MiB.")
    text = validate_bytes(path.read_bytes(), kind)
    blocks, warnings, pages, reports = [], [], 0, []
    if kind in {"TXT", "MD"}:
        offset = 0
        for number, original in enumerate(text.splitlines(keepends=True), 1):
            canonical = original.rstrip("\r\n")
            if canonical:
                blocks.append(block(original, canonical, {"line": number, "offset": offset}))
            offset += len(original)
            if len(blocks) > MAX_BLOCKS:
                raise InvalidSource("The file exceeds 20,000 text blocks.")
    elif kind == "DOCX":
        blocks, warnings = extract_docx(path)
    else:
        import pdfplumber
        from pdfminer.pdfdocument import PDFPasswordIncorrect
        from pdfplumber.utils.exceptions import PdfminerException

        try:
            opened = pdfplumber.open(path)
        except PdfminerException as error:
            if isinstance(error.__context__, PDFPasswordIncorrect):
                raise InvalidSource("Password-protected PDFs are not supported.") from error
            raise InvalidSource("The PDF is damaged or unsupported.") from error
        with opened as pdf:
            if pdf.doc.encryption:
                raise InvalidSource("Password-protected PDFs are not supported.")
            pages = len(pdf.pages)
            if not 1 <= pages <= 100:
                raise InvalidSource("PDFs must contain between 1 and 100 pages.")
            characters, preview_bytes = 0, 0
            for page in pdf.pages:
                started = time.monotonic()
                report = {
                    "page": page.page_number,
                    "status": "FAILED",
                    "preview": False,
                    "confidence": None,
                    "language": "",
                    "engine": "",
                }
                page_blocks = []
                image_path = output / f"page-{page.page_number}.png"
                if hasattr(signal, "SIGALRM"):
                    signal.signal(signal.SIGALRM, page_timeout)
                    signal.alarm(30)
                try:
                    width, height = page.width, page.height
                    if (
                        not all(math.isfinite(v) and 0 < v <= 3000 for v in (width, height))
                        or width * height > 4_000_000
                    ):
                        raise InvalidSource("Page exceeds its size limit.")
                    for line in page.extract_text_lines(return_chars=False, expand_ligatures=False):
                        text = line["text"]
                        bbox = [
                            (line["x0"] - page.bbox[0]) / width,
                            (line["top"] - page.bbox[1]) / height,
                            (line["x1"] - page.bbox[0]) / width,
                            (line["bottom"] - page.bbox[1]) / height,
                        ]
                        if not all(math.isfinite(v) and 0 <= v <= 1 for v in bbox):
                            raise InvalidSource("A text location falls outside its page.")
                        page_blocks.append(
                            block(text, text, {"page": page.page_number, "bbox": bbox})
                        )
                    needs_ocr = sum(not c.isspace() for b in page_blocks for c in b["text"]) < 20
                    dpi = min(
                        150 if needs_ocr else 72, 72 * math.sqrt(4_000_000 / (width * height))
                    )
                    image = page.to_image(resolution=dpi, force_mediabox=True)
                    image.save(image_path, format="PNG")
                    report["preview"] = True
                    if needs_ocr:
                        report["language"] = ocr_language
                        page_blocks, confidence, engine = ocr_page(
                            image_path,
                            *image.original.size,
                            page.page_number,
                            ocr_language,
                            max(0.01, 30 - (time.monotonic() - started)),
                        )
                        report.update(
                            status="OCR" if page_blocks else "EMPTY",
                            confidence=confidence,
                            engine=engine,
                        )
                        warnings.append(
                            f"Page {page.page_number}: OCR text needs review."
                            if page_blocks
                            else f"Page {page.page_number}: no readable text; exclude this page."
                        )
                    else:
                        report["status"] = "NATIVE"
                except Exception:
                    page_blocks = []
                    report["status"] = "FAILED"
                    warnings.append(
                        f"Page {page.page_number}: extraction failed; exclude it or upload again."
                    )
                finally:
                    if hasattr(signal, "SIGALRM"):
                        signal.alarm(0)
                    page.close()
                reports.append(report)
                blocks.extend(page_blocks)
                characters += sum(len(b["text"]) for b in page_blocks)
                if characters > MAX_CHARS or len(blocks) > MAX_BLOCKS:
                    raise InvalidSource("The PDF exceeds the extracted text limit.")
                if report["preview"]:
                    preview_bytes += image_path.stat().st_size
                if preview_bytes > MAX_BYTES:
                    raise InvalidSource("The PDF exceeds the total preview size limit.")
    return {
        "parserVersion": PARSER_VERSION,
        "pageCount": pages,
        "warnings": warnings,
        "blocks": blocks,
        "pageReports": reports,
    }


def main():
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (900 * 1024**2, 900 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    directory = Path(sys.argv[1]).resolve()
    try:
        request = (directory / "working").read_text()
        # Existing queued R2/R3 requests contained only the kind.
        options = json.loads(request) if request.startswith("{") else {"kind": request}
        result = extract(
            directory / "input", options["kind"], directory, options.get("ocrLanguage", "eng")
        )
    except InvalidSource as error:
        result = {"error": str(error)}
    except Exception:
        # Parser exception details can contain source text; never emit them into shared logs.
        result = {
            "error": "The file is damaged, encrypted or unsupported. Try an unencrypted export."
        }
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)
    payload = json.dumps(result, ensure_ascii=False).encode()
    if len(payload) > 16 * 1024**2:
        payload = b'{"error":"Extracted content exceeds the output limit."}'
    (directory / "result.tmp").write_bytes(payload)
    (directory / "result.tmp").replace(directory / "result.json")


if __name__ == "__main__":
    main()
