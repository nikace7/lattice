"""Format checks run without PostgreSQL, Redis or Docker."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from pipeline.source_parser import InvalidSource, extract

WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def docx_bytes(body, extra=None, document=None):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            f'<Override PartName="/word/document.xml" ContentType="{CONTENT_TYPE}"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            document or f'<w:document xmlns:w="{WORD}"><w:body>{body}</w:body></w:document>',
        )
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return output.getvalue()


def parse(tmp_path, data, kind):
    from modules.documents.tasks import validate_result

    path = tmp_path / "input"
    path.write_bytes(data)
    result = extract(path, kind, tmp_path)
    validate_result(result, kind)
    return result


def test_docx_paragraph_and_cell_anchors_preserve_unicode(tmp_path):
    result = parse(
        tmp_path,
        docx_bytes(
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            "<w:r><w:t>Leave policy</w:t></w:r></w:p><w:p/>"
            "<w:p><w:r><w:t>नेपाली é</w:t><w:tab/><w:t>notes</w:t></w:r></w:p>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Five days</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>Approval</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        ),
        "DOCX",
    )
    assert result["pageCount"] == 0 and result["warnings"] == []
    blocks = result["blocks"]
    assert [b["text"] for b in blocks] == [
        "Leave policy",
        "नेपाली é\tnotes",
        "Five days",
        "Approval",
    ]
    assert blocks[1]["locator"] == {"paragraph": 3, "headingPath": ["Leave policy"]}
    assert blocks[2]["locator"] == {
        "paragraph": 4,
        "headingPath": ["Leave policy"],
        "table": 1,
        "row": 1,
        "cell": 1,
    }
    assert all("page" not in b["locator"] for b in blocks)
    assert blocks[1]["originalText"] == blocks[1]["text"]
    size = len(blocks[1]["text"])
    assert blocks[1]["spanMap"] == [[0, size, 0, size]]


def test_markdown_is_literal_text_with_exact_line_offsets(tmp_path):
    text = "# Policy\r\n\n![remote](https://example.invalid/image.png)\n<script>example</script>\nनेपाली"
    result = parse(tmp_path, text.encode(), "MD")
    assert result["blocks"][1]["locator"] == {"line": 3, "offset": 11}
    assert result["blocks"][1]["text"].startswith("![remote]")
    assert result["blocks"][2]["originalText"] == "<script>example</script>\n"
    assert result["pageCount"] == 0


@pytest.mark.parametrize("name", ["../escape", "/absolute", "word\\bad", "word/vbaProject.bin"])
def test_docx_rejects_unsafe_archive_members(tmp_path, name):
    with pytest.raises(InvalidSource):
        parse(tmp_path, docx_bytes("<w:p/>", {name: b"unsafe"}), "DOCX")


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_docx_rejects_dtd_and_entities(tmp_path, encoding):
    xml = (
        '<?xml version="1.0" encoding="' + encoding + '"?>'
        '<!DOCTYPE document [<!ENTITY sample "expanded">]>'
        f'<w:document xmlns:w="{WORD}"><w:body><w:p><w:r><w:t>&sample;</w:t>'
        "</w:r></w:p></w:body></w:document>"
    )
    with pytest.raises(InvalidSource, match="XML"):
        parse(tmp_path, docx_bytes("", document=xml.encode(encoding)), "DOCX")


def test_docx_limits_and_unsupported_content_are_explicit(tmp_path, monkeypatch):
    data = docx_bytes(
        "<w:p><w:r><w:t>Body</w:t><w:drawing/></w:r></w:p>",
        {"word/header1.xml": b"<header/>"},
    )
    assert parse(tmp_path, data, "DOCX")["warnings"]
    monkeypatch.setattr("pipeline.source_parser.MAX_DOCX_EXPANDED", 100)
    with pytest.raises(InvalidSource, match="expanded"):
        parse(tmp_path, data, "DOCX")


def test_docx_requires_a_word_package(tmp_path):
    with pytest.raises(InvalidSource):
        parse(tmp_path, b"PK\x03\x04broken", "DOCX")
    with pytest.raises(InvalidSource, match="text"):
        parse(tmp_path, docx_bytes("<w:p/>"), "DOCX")


def test_docx_boundary_rejects_invented_page_and_incomplete_cell(tmp_path):
    from modules.documents.tasks import validate_result

    result = parse(tmp_path, docx_bytes("<w:p><w:r><w:t>Body</w:t></w:r></w:p>"), "DOCX")
    result["blocks"][0]["locator"]["page"] = 1
    with pytest.raises(InvalidSource, match="DOCX locator"):
        validate_result(result, "DOCX")
    del result["blocks"][0]["locator"]["page"]
    result["blocks"][0]["locator"]["table"] = 1
    with pytest.raises(InvalidSource, match="DOCX locator"):
        validate_result(result, "DOCX")


def test_existing_pdf_and_txt_still_keep_source_locations(tmp_path):
    from tests.pdf_fixture import pdf_bytes

    result = parse(tmp_path, pdf_bytes(), "PDF")
    assert result["blocks"][0]["locator"]["page"] == 1
    assert (tmp_path / "page-1.png").read_bytes().startswith(b"\x89PNG")
    result = parse(tmp_path, "One\r\nनेपाली é\n".encode(), "TXT")
    assert result["blocks"][1]["locator"] == {"line": 2, "offset": 5}
