"""No Django, database or provider access. Production calls this in the offline parser container."""

import json
import math
import signal
import sys
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
MAX_CHARS = 2_000_000
MAX_BLOCKS = 20_000
PARSER_VERSION = "r2-identity-v1/pdfplumber-0.11.10"


class InvalidSource(ValueError):
    pass


def validate_bytes(data, kind):
    if not data or len(data) > MAX_BYTES:
        raise InvalidSource("Choose a nonempty file no larger than 25 MiB.")
    if kind == "PDF":
        if not data.startswith(b"%PDF-"):
            raise InvalidSource("This file does not have a PDF signature.")
        return None
    if kind != "TXT":
        raise InvalidSource("Only PDF and UTF-8 TXT files are supported.")
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


def extract(path, kind, output):
    path, output = Path(path), Path(output)
    if path.stat().st_size > MAX_BYTES:
        raise InvalidSource("The file exceeds 25 MiB.")
    text = validate_bytes(path.read_bytes(), kind)
    blocks, warnings, pages = [], [], 0
    if kind == "TXT":
        offset = 0
        for number, original in enumerate(text.splitlines(keepends=True), 1):
            canonical = original.rstrip("\r\n")
            if canonical:
                blocks.append(block(original, canonical, {"line": number, "offset": offset}))
            offset += len(original)
            if len(blocks) > MAX_BLOCKS:
                raise InvalidSource("The file exceeds 20,000 text blocks.")
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
                if hasattr(signal, "SIGALRM"):
                    signal.signal(signal.SIGALRM, page_timeout)
                    signal.alarm(30)
                width, height = page.width, page.height
                if (
                    not all(math.isfinite(v) and 0 < v <= 3000 for v in (width, height))
                    or width * height > 4_000_000
                ):
                    raise InvalidSource("A PDF page exceeds the preview size limit.")
                page_chars = 0
                for line in page.extract_text_lines(return_chars=False, expand_ligatures=False):
                    text = line["text"]
                    bbox = [
                        (line["x0"] - page.bbox[0]) / width,
                        (line["top"] - page.bbox[1]) / height,
                        (line["x1"] - page.bbox[0]) / width,
                        (line["bottom"] - page.bbox[1]) / height,
                    ]
                    if not all(math.isfinite(v) and 0 <= v <= 1 for v in bbox):
                        raise InvalidSource("A PDF text location falls outside its page.")
                    blocks.append(block(text, text, {"page": page.page_number, "bbox": bbox}))
                    characters += len(text)
                    page_chars += len(text.strip())
                    if characters > MAX_CHARS or len(blocks) > MAX_BLOCKS:
                        raise InvalidSource("The PDF exceeds the extracted text limit.")
                if page_chars < 20:
                    warnings.append(
                        f"Page {page.page_number} has little or no text. OCR/review is required."
                    )
                image_path = output / f"page-{page.page_number}.png"
                image = page.to_image(resolution=72, force_mediabox=True)
                image.save(image_path, format="PNG")
                preview_bytes += image_path.stat().st_size
                if preview_bytes > MAX_BYTES:
                    raise InvalidSource("The PDF exceeds the total preview size limit.")
                page.close()
                if hasattr(signal, "SIGALRM"):
                    signal.alarm(0)
    return {
        "parserVersion": PARSER_VERSION,
        "pageCount": pages,
        "warnings": warnings,
        "blocks": blocks,
    }


def main():
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (900 * 1024**2, 900 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    directory = Path(sys.argv[1]).resolve()
    try:
        kind = (directory / "working").read_text()
        result = extract(directory / "input", kind, directory)
    except InvalidSource as error:
        result = {"error": str(error)}
    except Exception:
        # Parser exception details can contain source text; never emit them into shared logs.
        result = {
            "error": "The PDF is damaged, encrypted or unsupported. Try an unencrypted export."
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
