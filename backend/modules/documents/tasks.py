import json
import logging
import shutil
import time
import uuid
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from kombu.exceptions import OperationalError

from modules.workspaces.access import can_write
from modules.workspaces.models import Membership, Workspace
from pipeline.source_parser import MAX_BLOCKS, MAX_BYTES, MAX_CHARS, InvalidSource

from .models import ExtractionJob, ExtractionVersion, SourceBlock, SourceVersion
from .storage import source_directory, source_path

logger = logging.getLogger(__name__)


def enqueue(source_id, attempt):
    try:
        extract_source.delay(source_id, attempt)
    except OperationalError:
        ExtractionJob.objects.filter(source_id=source_id, attempt=attempt, state="QUEUED").update(
            state="FAILED",
            error="The extraction queue is unavailable. Please retry.",
            retryable=True,
            updated_at=timezone.now(),
        )


def parse_source(source):
    root = Path(settings.PARSER_SPOOL_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = (root / str(uuid.uuid4())).resolve()
    if directory.parent != root:
        raise RuntimeError("Invalid parser spool directory.")
    directory.mkdir()
    try:
        shutil.copyfile(source_path(source), directory / "input")
        (directory / "request.tmp").write_text(
            json.dumps({"kind": source.kind, "ocrLanguage": source.ocr_language})
        )
        (directory / "request.tmp").rename(directory / "request")
        deadline = time.monotonic() + settings.PARSER_TIMEOUT_SECONDS
        result_path = directory / "result.json"
        while not result_path.exists():
            if time.monotonic() > deadline:
                raise TimeoutError("Parser unavailable or timed out.")
            time.sleep(0.25)
        if result_path.stat().st_size > 16 * 1024**2:
            raise InvalidSource("Extracted content exceeds the output limit.")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise InvalidSource("Invalid extraction result.")
        if "error" in result:
            raise InvalidSource(str(result["error"])[:240])
        validate_result(result, source.kind)
        artifact = source_directory(source) / str(source.job.attempt)
        artifact.mkdir(exist_ok=True)
        preview_bytes = 0
        for report in result["pageReports"]:
            if not report["preview"]:
                continue
            page = report["page"]
            image = directory / f"page-{page}.png"
            if image.is_symlink() or image.stat().st_size > 16 * 1024**2:
                raise InvalidSource("Invalid page preview.")
            preview_bytes += image.stat().st_size
            if preview_bytes > MAX_BYTES:
                raise InvalidSource("The PDF exceeds the total preview size limit.")
            with image.open("rb") as stream:
                if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                    raise InvalidSource("Invalid page preview.")
            shutil.copyfile(image, artifact / image.name)
        return result
    finally:
        # directory is a fresh UUID, resolved and checked against the dedicated spool above.
        shutil.rmtree(directory, ignore_errors=True)


def validate_result(result, kind):
    import math

    if (
        not isinstance(result, dict)
        or not isinstance(result.get("pageCount"), int)
        or not 0 <= result["pageCount"] <= 100
    ):
        raise InvalidSource("Invalid extraction result.")
    if (
        kind not in {"PDF", "DOCX", "TXT", "MD"}
        or (kind != "PDF" and result["pageCount"] != 0)
        or (kind == "PDF" and result["pageCount"] == 0)
    ):
        raise InvalidSource("Invalid extraction format or page count.")
    reports = result.get("pageReports")
    if not isinstance(reports, list) or len(reports) != result["pageCount"]:
        raise InvalidSource("Invalid extraction page reports.")
    for number, report in enumerate(reports, 1):
        if (
            not isinstance(report, dict)
            or report.get("page") != number
            or report.get("status") not in {"NATIVE", "OCR", "EMPTY", "FAILED"}
            or not isinstance(report.get("preview"), bool)
            or report.get("language") not in {"", "eng", "nep", "eng+nep"}
            or not isinstance(report.get("engine"), str)
            or len(report["engine"]) > 80
            or (
                report.get("confidence") is not None
                and (
                    not isinstance(report["confidence"], (int, float))
                    or not 0 <= report["confidence"] <= 100
                )
            )
        ):
            raise InvalidSource("Invalid extraction page report.")
        if report["status"] in {"NATIVE", "OCR", "EMPTY"} and not report["preview"]:
            raise InvalidSource("Successful page extraction requires a preview.")
        if report["status"] in {"OCR", "EMPTY"} and (
            not report["language"]
            or not report["engine"]
            or (report["status"] == "OCR" and report.get("confidence") is None)
        ):
            raise InvalidSource("OCR provenance is incomplete.")
    blocks = result.get("blocks")
    if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
        raise InvalidSource("Invalid extraction blocks.")
    if (
        not isinstance(result.get("warnings"), list)
        or len(result["warnings"]) > 100
        or any(not isinstance(w, str) or len(w) > 240 for w in result["warnings"])
    ):
        raise InvalidSource("Invalid extraction warnings.")
    if any(report["status"] != "NATIVE" for report in reports) and not result["warnings"]:
        raise InvalidSource("OCR and incomplete pages must require review.")
    if not isinstance(result.get("parserVersion"), str) or len(result["parserVersion"]) > 80:
        raise InvalidSource("Invalid parser version.")
    count = 0
    for item in blocks:
        if not isinstance(item, dict):
            raise InvalidSource("Invalid source block.")
        text, original, location = item.get("text"), item.get("originalText"), item.get("locator")
        if (
            not isinstance(text, str)
            or not isinstance(original, str)
            or not isinstance(location, dict)
        ):
            raise InvalidSource("Invalid source block.")
        count += len(original)
        if (
            count > MAX_CHARS + MAX_BLOCKS * 2
            or original[: len(text)] != text
            or item.get("spanMap") != [[0, len(text), 0, len(text)]]
        ):
            raise InvalidSource("Invalid source span mapping.")
        if kind == "PDF":
            box = location.get("bbox", [])
            if (
                not isinstance(location.get("page"), int)
                or not 1 <= location["page"] <= result["pageCount"]
                or not isinstance(box, list)
                or len(box) != 4
                or not all(
                    isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in box
                )
                or box[0] > box[2]
                or box[1] > box[3]
                or reports[location["page"] - 1]["status"] in {"FAILED", "EMPTY"}
                or (
                    (reports[location["page"] - 1]["status"] == "OCR")
                    != (location.get("method") == "OCR")
                )
                or (
                    location.get("method") == "OCR"
                    and (
                        not isinstance(location.get("confidence"), (int, float))
                        or not 0 <= location["confidence"] <= 100
                    )
                )
            ):
                raise InvalidSource("Invalid PDF locator.")
        elif kind == "DOCX":
            heading = location.get("headingPath")
            if (
                not isinstance(location.get("paragraph"), int)
                or location["paragraph"] < 1
                or not isinstance(heading, list)
                or len(heading) > 9
                or any(not isinstance(label, str) or len(label) > 240 for label in heading)
                or "page" in location
                or (
                    any(key in location for key in ("table", "row", "cell"))
                    and not all(
                        isinstance(location.get(key), int) and location[key] >= 1
                        for key in ("table", "row", "cell")
                    )
                )
            ):
                raise InvalidSource("Invalid DOCX locator.")
        elif (
            not isinstance(location.get("line"), int)
            or location["line"] < 1
            or not isinstance(location.get("offset"), int)
            or location["offset"] < 0
        ):
            raise InvalidSource("Invalid text locator.")


@shared_task
def extract_source(source_id, attempt):
    claimed = ExtractionJob.objects.filter(
        source_id=source_id, attempt=attempt, state="QUEUED"
    ).update(state="EXTRACTING", updated_at=timezone.now())
    if not claimed:
        return
    source = SourceVersion.objects.select_related("document__collection", "job").get(pk=source_id)
    try:
        result = parse_source(source)
        validate_result(result, source.kind)
        with transaction.atomic():
            workspace = Workspace.objects.select_for_update().get(
                pk=source.document.collection.workspace_id
            )
            job = ExtractionJob.objects.select_for_update().get(source=source)
            if str(job.attempt) != attempt or job.state != "EXTRACTING":
                return
            member = Membership.objects.filter(
                workspace=workspace,
                user=source.document.created_by,
                active=True,
                user__is_active=True,
            ).first()
            source.document.collection.refresh_from_db()
            if not member or not can_write(source.document.collection, member):
                raise InvalidSource(
                    "The uploader's contribution access changed. Ask an owner to upload again."
                )
            extraction = ExtractionVersion.objects.create(
                id=attempt,
                source=source,
                parser_version=result["parserVersion"],
                page_count=result["pageCount"],
                warnings=result["warnings"],
                page_reports=result["pageReports"],
            )
            SourceBlock.objects.bulk_create(
                [
                    SourceBlock(
                        extraction=extraction,
                        position=index,
                        text=item["text"],
                        original_text=item["originalText"],
                        locator=item["locator"],
                        span_map=item["spanMap"],
                    )
                    for index, item in enumerate(result["blocks"])
                ],
                batch_size=500,
            )
            job.state = "NEEDS_REVIEW" if result["warnings"] else "EXTRACTED"
            job.save(update_fields=["state", "updated_at"])
    except Exception as error:
        safe_error = (
            str(error)[:240]
            if isinstance(error, InvalidSource)
            else "Extraction is temporarily unavailable. Check the parser service and retry."
        )
        if not isinstance(error, InvalidSource):
            logger.error(
                "Extraction failed source=%s error_type=%s", source_id, type(error).__name__
            )
        ExtractionJob.objects.filter(
            source_id=source_id, attempt=attempt, state="EXTRACTING"
        ).update(
            state="FAILED",
            error=safe_error,
            retryable=not isinstance(error, InvalidSource),
            updated_at=timezone.now(),
        )
