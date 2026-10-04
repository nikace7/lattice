from unittest.mock import patch

import pytest

from pipeline import source_parser
from tests.pdf_fixture import pdf_bytes


def test_ocr_word_boxes_form_lines_without_losing_unicode(tmp_path):
    path = tmp_path / "words.tsv"
    path.write_text(
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t90\tनेपाली\n"
        "5\t1\t1\t1\t1\t2\t45\t20\t20\t10\t80\té\n",
        encoding="utf-8",
    )
    blocks, confidence = source_parser.read_ocr_tsv(path, 100, 100, 2)
    assert blocks[0]["text"] == "नेपाली é"
    assert blocks[0]["locator"]["bbox"] == [0.1, 0.2, 0.65, 0.3]
    assert blocks[0]["locator"]["page"] == 2
    assert blocks[0]["locator"]["method"] == "OCR"
    assert confidence == 85


def test_blank_pdf_attempts_ocr_and_records_review_metadata(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(pdf_bytes(text=""))
    blocks = [
        source_parser.block(
            "Recognized",
            "Recognized",
            {"page": 1, "bbox": [0, 0, 1, 1], "method": "OCR", "confidence": 88},
        )
    ]
    with patch.object(
        source_parser, "ocr_page", return_value=(blocks, 88, "tesseract 5.test")
    ) as ocr:
        result = source_parser.extract(path, "PDF", tmp_path, "nep")
    assert ocr.call_args.args[4] == "nep"
    assert result["warnings"]
    assert result["pageReports"][0] == {
        "page": 1,
        "status": "OCR",
        "preview": True,
        "confidence": 88,
        "language": "nep",
        "engine": "tesseract 5.test",
    }


def test_unavailable_ocr_does_not_discard_other_pages(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(pdf_bytes(pages=2, text=""))
    with patch.object(
        source_parser, "ocr_page", side_effect=source_parser.InvalidSource("OCR unavailable.")
    ):
        result = source_parser.extract(path, "PDF", tmp_path)
    assert len(result["pageReports"]) == 2
    assert all(page["status"] == "FAILED" for page in result["pageReports"])
    assert result["blocks"] == [] and result["warnings"]


def test_partial_review_requires_all_failed_pages_to_be_excluded():
    from modules.documents.serializers import ReviewInput

    serializer = ReviewInput(
        data={"expectedRevision": 1, "excludedPages": [2, 2], "reason": "Checked the source"}
    )
    assert not serializer.is_valid()
    from rest_framework.exceptions import ValidationError

    from modules.documents.api import validate_review_pages

    reports = [{"page": 1, "status": "OCR"}, {"page": 2, "status": "FAILED"}]
    with pytest.raises(ValidationError):
        validate_review_pages(reports, [], 2)
    validate_review_pages(reports, [2], 2)
    with pytest.raises(ValidationError):
        validate_review_pages(reports, [3], 2)


@pytest.mark.parametrize(
    "change", ["warnings", "preview", "language", "engine", "confidence", "method"]
)
def test_worker_rejects_incoherent_ocr_results(change):
    from modules.documents.tasks import validate_result

    result = {
        "pageCount": 1,
        "parserVersion": "test",
        "warnings": ["Review OCR"],
        "pageReports": [
            {
                "page": 1,
                "status": "OCR",
                "preview": True,
                "language": "eng",
                "engine": "tesseract test",
                "confidence": 90,
            }
        ],
        "blocks": [
            source_parser.block(
                "Text",
                "Text",
                {
                    "page": 1,
                    "bbox": [0, 0, 1, 1],
                    "method": "OCR",
                    "confidence": 90,
                },
            )
        ],
    }
    validate_result(result, "PDF")
    if change == "warnings":
        result["warnings"] = []
    elif change == "method":
        result["blocks"][0]["locator"].pop("method")
    else:
        result["pageReports"][0][change] = {"preview": False, "confidence": None}.get(change, "")
    with pytest.raises(source_parser.InvalidSource):
        validate_result(result, "PDF")


def test_failed_ocr_page_preserves_successful_following_page(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(pdf_bytes(pages=2, text=""))
    blocks = [
        source_parser.block(
            "Recovered",
            "Recovered",
            {
                "page": 2,
                "bbox": [0, 0, 1, 1],
                "method": "OCR",
                "confidence": 88,
            },
        )
    ]
    with patch.object(
        source_parser,
        "ocr_page",
        side_effect=[
            source_parser.InvalidSource("OCR timeout"),
            (blocks, 88, "tesseract test"),
        ],
    ):
        result = source_parser.extract(path, "PDF", tmp_path)
    assert [p["status"] for p in result["pageReports"]] == ["FAILED", "OCR"]
    assert result["blocks"] == blocks


def test_ocr_tsv_preserves_literal_quotes(tmp_path):
    path = tmp_path / "words.tsv"
    path.write_text(
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        '5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t90\t"quoted\n'
        '5\t1\t1\t1\t1\t2\t45\t20\t20\t10\t80\tword"\n',
        encoding="utf-8",
    )
    blocks, _ = source_parser.read_ocr_tsv(path, 100, 100, 1)
    assert blocks[0]["text"] == '"quoted word"'


def test_ocr_timeout_is_bounded_and_cleans_output(tmp_path):
    import subprocess

    image = tmp_path / "page-1.png"
    output = tmp_path / "ocr-1.tsv"
    output.write_text("partial")
    with (
        patch.object(source_parser.shutil, "which", return_value="/usr/bin/tesseract"),
        patch.object(
            source_parser.subprocess,
            "run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=b"tesseract test\n"),
                subprocess.TimeoutExpired("tesseract", 2),
            ],
        ) as command,
        pytest.raises(source_parser.InvalidSource, match="deadline"),
    ):
        source_parser.ocr_page(image, 100, 100, 1, "eng", 2)
    assert 0 < command.call_args.kwargs["timeout"] <= 2
    assert command.call_args.kwargs["env"]["OMP_THREAD_LIMIT"] == "1"
    assert not output.exists()
