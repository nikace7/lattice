import hashlib
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from modules.collections.models import Collection, CollectionGrant
from modules.documents.models import Document
from modules.documents.tasks import extract_source
from modules.workspaces.models import Membership, Workspace
from pipeline.source_parser import extract
from tests.pdf_fixture import pdf_bytes

pytestmark = pytest.mark.django_db


@pytest.fixture
def library(settings, tmp_path):
    settings.STORAGE_ROOT = tmp_path / "private"
    owner = get_user_model().objects.create_user("writer")
    reader = get_user_model().objects.create_user("reader")
    workspace = Workspace.objects.create(name="Same library")
    Membership.objects.create(user=owner, workspace=workspace, role="OWNER")
    Membership.objects.create(user=reader, workspace=workspace, role="VIEWER")
    collection = Collection.objects.create(workspace=workspace, title="Policies")
    client = APIClient()
    client.force_login(owner)
    return client, reader, collection


def upload(client, collection, body=b"First line\r\nSecond line\n", name="policy.txt", **extra):
    return client.post(
        f"/api/v1/collections/{collection.pk}/documents",
        {"uploadId": str(uuid.uuid4()), "file": SimpleUploadedFile(name, body), **extra},
        format="multipart",
    )


def local_parser(source):
    from modules.documents.storage import source_path

    return extract(
        source_path(source), source.kind, source_path(source).parent, source.ocr_language
    )


def process(document_id):
    document = Document.objects.get(pk=document_id)
    with patch("modules.documents.tasks.parse_source", side_effect=local_parser):
        extract_source(str(document.source.pk), str(document.source.job.attempt))
    return document


def test_upload_extract_original_mapping_and_idempotency(
    library, django_capture_on_commit_callbacks
):
    client, _, collection = library
    body = "One\r\nनेपाली e\u0301\n".encode()
    upload_id = str(uuid.uuid4())
    with (
        patch("modules.documents.tasks.extract_source.delay") as queued,
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = upload(client, collection, body, uploadId=upload_id)
    assert response.status_code == 201, response.data
    assert queued.call_count == 1
    document = process(response.data["id"])
    detail = client.get(f"/api/v1/documents/{document.pk}")
    assert detail.data["state"] == "EXTRACTED"
    source_id = detail.data["sourceId"]
    blocks = client.get(f"/api/v1/sources/{source_id}/blocks").data["results"]
    assert [b["text"] for b in blocks] == ["One", "नेपाली e\u0301"]
    assert blocks[1]["locator"] == {"line": 2, "offset": 5}
    assert blocks[1]["originalText"] == "नेपाली e\u0301\n"
    assert blocks[1]["spanMap"] == [[0, len("नेपाली e\u0301"), 0, len("नेपाली e\u0301")]]
    original = client.get(f"/api/v1/sources/{source_id}/original")
    assert b"".join(original.streaming_content) == body
    assert original["Cache-Control"] == "no-store"
    assert original["Content-Disposition"].startswith("attachment;")
    assert document.source.sha256 == hashlib.sha256(body).hexdigest()
    assert upload(client, collection, body, uploadId=upload_id).status_code == 200
    assert upload(client, collection, b"changed", uploadId=upload_id).status_code == 409
    assert Document.objects.count() == 1


@pytest.mark.parametrize(
    "name,body",
    [
        ("fake.pdf", b"not pdf"),
        ("fake.txt", b"MZbinary"),
        ("fake.txt", b"<!doctype html><html>hello</html>"),
        ("fake.txt", b"\xff\x00"),
        ("page.html", b"hello"),
        ("empty.txt", b""),
    ],
)
def test_invalid_uploads_leave_no_records(library, name, body):
    client, _, collection = library
    assert upload(client, collection, body, name).status_code == 400
    assert Document.objects.count() == 0


def test_scoped_list_source_and_original_revocation(library):
    client, reader, collection = library
    collection.access = "RESTRICTED"
    collection.save()
    member = Membership.objects.get(user=reader)
    grant = CollectionGrant.objects.create(collection=collection, membership=member)
    response = upload(client, collection)
    document = process(response.data["id"])
    other = APIClient()
    other.force_login(reader)
    path = f"/api/v1/workspaces/{collection.workspace_id}/documents"
    assert len(other.get(path).data["results"]) == 1
    assert upload(other, collection).status_code == 403
    grant.delete()
    assert other.get(path).data["results"] == []
    for endpoint in [
        f"/documents/{document.pk}",
        f"/sources/{document.source.pk}/blocks",
        f"/sources/{document.source.pk}/original",
        f"/sources/{document.source.pk}/pages/1",
    ]:
        assert other.get("/api/v1" + endpoint).status_code == 404


def test_limits_queue_failure_retry_and_duplicate_task(
    library, settings, django_capture_on_commit_callbacks
):
    from kombu.exceptions import OperationalError

    client, _, collection = library
    settings.MAX_WORKSPACE_STORAGE_BYTES = 3
    assert upload(client, collection).status_code == 429
    settings.MAX_WORKSPACE_STORAGE_BYTES = 1000
    with (
        patch("modules.documents.tasks.extract_source.delay", side_effect=OperationalError),
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = upload(client, collection)
    document = Document.objects.get(pk=result.data["id"])
    assert document.source.job.state == "FAILED"
    assert document.source.job.retryable
    response = client.post(
        f"/api/v1/documents/{document.pk}/retry", {"expectedRevision": 1}, format="json"
    )
    assert response.status_code == 200, response.data
    process(document.pk)
    with patch("modules.documents.tasks.parse_source") as parser:
        extract_source(str(document.source.pk), str(document.source.job.attempt))
    parser.assert_not_called()


def test_text_extraction_bounds_and_never_renders_html(tmp_path):
    path = tmp_path / "input"
    path.write_text("plain <script>alert(1)</script>\r\n\n", encoding="utf-8", newline="")
    result = extract(path, "TXT", tmp_path)
    assert result["blocks"][0]["text"] == "plain <script>alert(1)</script>"
    assert result["blocks"][0]["locator"]["line"] == 1
    assert result["pageCount"] == 0


def test_native_pdf_mapping_preview_and_page_limit(tmp_path):
    from pipeline.source_parser import InvalidSource

    path = tmp_path / "input.pdf"
    path.write_bytes(pdf_bytes())
    result = extract(path, "PDF", tmp_path)
    assert result["pageCount"] == 1
    assert result["warnings"] == []
    line = result["blocks"][0]
    assert line["text"] == "Submit requests five working days ahead."
    assert line["originalText"] == line["text"]
    assert line["locator"]["page"] == 1
    assert line["locator"]["bbox"][0] == pytest.approx(50 / 612)
    assert 0.10 < line["locator"]["bbox"][1] < 0.12
    assert (tmp_path / "page-1.png").read_bytes().startswith(b"\x89PNG")
    path.write_bytes(pdf_bytes(pages=101))
    with pytest.raises(InvalidSource, match="100 pages"):
        extract(path, "PDF", tmp_path)


def test_blank_pdf_needs_review_and_corrupt_pdf_fails(library, tmp_path):
    client, _, collection = library
    path = tmp_path / "blank.pdf"
    path.write_bytes(pdf_bytes(text=""))
    result = extract(path, "PDF", tmp_path)
    assert result["warnings"] and not result["blocks"]
    response = upload(client, collection, pdf_bytes(text=""), "scan.pdf")
    document = process(response.data["id"])
    assert client.get(f"/api/v1/documents/{document.pk}").data["state"] == "NEEDS_REVIEW"
    response = upload(client, collection, b"%PDF-1.4 broken", "broken.pdf")
    document = process(response.data["id"])
    assert client.get(f"/api/v1/documents/{document.pk}").data["state"] == "FAILED"


def test_cross_workspace_sources_and_upload_limit(library, monkeypatch):
    client, reader, collection = library
    result = upload(client, collection)
    document = process(result.data["id"])
    other_workspace = Workspace.objects.create(name="Same library")
    outsider = get_user_model().objects.create_user("outsider")
    Membership.objects.create(user=outsider, workspace=other_workspace, role="OWNER")
    other_collection = Collection.objects.create(workspace=other_workspace, title="Policies")
    other = APIClient()
    other.force_login(outsider)
    upload(other, other_collection)
    assert len(other.get(f"/api/v1/workspaces/{other_workspace.pk}/documents").data["results"]) == 1
    assert other.get(f"/api/v1/documents/{document.pk}").status_code == 404
    assert other.get(f"/api/v1/sources/{document.source.pk}/original").status_code == 404
    assert upload(other, collection).status_code == 404
    monkeypatch.setattr("modules.documents.uploads.MAX_BYTES", 3)
    too_large = upload(client, collection, b"four")
    assert too_large.status_code == 400
    assert "25 MiB" in too_large.data["error"]["message"]


def test_access_change_during_extraction_prevents_publication(library):
    from modules.documents.models import ExtractionVersion

    client, _, collection = library
    response = upload(client, collection)
    document = Document.objects.get(pk=response.data["id"])

    def revoke(source):
        result = local_parser(source)
        Membership.objects.filter(user=source.document.created_by).update(active=False)
        return result

    with patch("modules.documents.tasks.parse_source", side_effect=revoke):
        extract_source(str(document.source.pk), str(document.source.job.attempt))
    document.source.job.refresh_from_db()
    assert document.source.job.state == "FAILED"
    assert "access changed" in document.source.job.error
    assert not ExtractionVersion.objects.exists()


def test_upload_requires_csrf(library):
    owner, _, collection = library
    client = APIClient(enforce_csrf_checks=True)
    user = Membership.objects.get(workspace=collection.workspace, role="OWNER").user
    client.force_login(user)
    assert upload(client, collection).status_code == 403


@pytest.mark.parametrize("kind,name", [("DOCX", "policy.docx"), ("MD", "policy.md")])
def test_new_formats_use_scoped_upload_and_source_routes(library, kind, name):
    from tests.test_document_formats import docx_bytes

    client, _, collection = library
    body = (
        docx_bytes("<w:p><w:r><w:t>Body text</w:t></w:r></w:p>")
        if kind == "DOCX"
        else b"# Policy\nBody text"
    )
    response = upload(client, collection, body, name)
    assert response.status_code == 201
    document = process(response.data["id"])
    detail = client.get(f"/api/v1/documents/{document.pk}").data
    assert detail["kind"] == kind and detail["state"] == "EXTRACTED"
    blocks = client.get(f"/api/v1/sources/{document.source.pk}/blocks").data["results"]
    assert blocks[-1]["text"] == "Body text"
    assert "page" not in blocks[-1]["locator"]
    assert client.get(f"/api/v1/sources/{document.source.pk}/pages/1").status_code == 404


def test_stale_attempt_cannot_publish(library):
    from modules.documents.models import ExtractionJob, ExtractionVersion

    client, _, collection = library
    document = Document.objects.get(pk=upload(client, collection).data["id"])
    next_attempt = uuid.uuid4()

    def replace_attempt(source):
        result = local_parser(source)
        ExtractionJob.objects.filter(source=source).update(attempt=next_attempt, state="QUEUED")
        return result

    with patch("modules.documents.tasks.parse_source", side_effect=replace_attempt):
        extract_source(str(document.source.pk), str(document.source.job.attempt))
    document.source.job.refresh_from_db()
    assert document.source.job.attempt == next_attempt
    assert document.source.job.state == "QUEUED"
    assert not ExtractionVersion.objects.exists()
    process(document.pk)
    assert ExtractionVersion.objects.get().pk == next_attempt


@pytest.mark.parametrize("filename", ["r2-encrypted.pdf", "r2-encrypted-empty.pdf"])
def test_password_encryption_is_rejected(tmp_path, filename):
    from pipeline.source_parser import InvalidSource

    path = Path(__file__).resolve().parents[2] / "fixtures" / "corpus" / filename
    with pytest.raises(InvalidSource, match="Password-protected"):
        extract(path, "PDF", tmp_path)


def test_partial_review_enforces_access_revision_and_exclusions(library):
    from modules.documents.models import ExtractionVersion, SourceBlock

    client, reader, collection = library
    response = upload(client, collection, pdf_bytes(pages=2), "scan.pdf", ocrLanguage="nep")
    document = Document.objects.get(pk=response.data["id"])
    assert document.source.ocr_language == "nep"
    job = document.source.job
    job.state = "NEEDS_REVIEW"
    job.save()
    extraction = ExtractionVersion.objects.create(
        source=document.source,
        parser_version="test",
        page_count=2,
        page_reports=[{"page": 1, "status": "OCR"}, {"page": 2, "status": "FAILED"}],
        warnings=["Review OCR"],
    )
    SourceBlock.objects.create(
        extraction=extraction,
        position=0,
        text="Text",
        original_text="Text",
        locator={"page": 1},
        span_map=[[0, 4, 0, 4]],
    )
    path = f"/api/v1/documents/{document.pk}/accept-review"
    payload = {"expectedRevision": 1, "excludedPages": [2], "reason": "Checked against source"}
    other = APIClient()
    other.force_login(reader)
    assert other.post(path, payload, format="json").status_code == 403
    collection.access = "RESTRICTED"
    collection.save()
    assert other.post(path, payload, format="json").status_code == 404
    assert client.post(path, {**payload, "expectedRevision": 9}, format="json").status_code == 409
    assert client.post(path, {**payload, "excludedPages": []}, format="json").status_code == 400
    assert client.post(path, {**payload, "excludedPages": [1, 2]}, format="json").status_code == 400
    assert client.post(path, {**payload, "reason": " "}, format="json").status_code == 400
    accepted = client.post(path, payload, format="json")
    assert accepted.status_code == 200, accepted.data
    assert accepted.data["state"] == "REVIEWED"
    assert accepted.data["excludedPages"] == [2]
    assert accepted.data["revision"] == 2
    extraction.refresh_from_db()
    assert extraction.accepted_by_id == document.created_by_id
    assert extraction.accepted_at and extraction.review_reason == payload["reason"]
    assert client.post(path, payload, format="json").status_code == 409
    assert client.post(path, {**payload, "expectedRevision": 2}, format="json").status_code == 409


def test_cancel_permissions_revision_and_late_worker_fence(library):
    from modules.documents.models import ExtractionVersion

    client, reader, collection = library
    document = Document.objects.get(pk=upload(client, collection).data["id"])
    path = f"/api/v1/documents/{document.pk}/cancel"
    other = APIClient()
    other.force_login(reader)
    assert other.post(path, {"expectedRevision": 1}, format="json").status_code == 403
    collection.access = "RESTRICTED"
    collection.save()
    assert other.post(path, {"expectedRevision": 1}, format="json").status_code == 404
    assert client.post(path, {"expectedRevision": 2}, format="json").status_code == 409

    def cancel_during_parse(source):
        result = local_parser(source)
        cancelled = client.post(path, {"expectedRevision": 1}, format="json")
        assert cancelled.status_code == 200
        assert cancelled.data["state"] == "CANCELLED" and cancelled.data["retryable"]
        return result

    with patch("modules.documents.tasks.parse_source", side_effect=cancel_during_parse):
        extract_source(str(document.source.pk), str(document.source.job.attempt))
    assert not ExtractionVersion.objects.exists()
    assert client.post(path, {"expectedRevision": 1}, format="json").status_code == 409
    original = client.get(f"/api/v1/sources/{document.source.pk}/original")
    assert b"".join(original.streaming_content)
    retried = client.post(
        f"/api/v1/documents/{document.pk}/retry", {"expectedRevision": 2}, format="json"
    )
    assert retried.status_code == 200
    assert not retried.data["retryable"]
    process(document.pk)
    assert ExtractionVersion.objects.count() == 1
    assert client.post(path, {"expectedRevision": 3}, format="json").status_code == 409


def test_recovery_requeues_expired_jobs_with_new_attempts_and_stops_at_limit(
    library,
    django_capture_on_commit_callbacks,
):
    from datetime import timedelta

    from django.utils import timezone

    from modules.documents.models import ExtractionJob
    from modules.documents.tasks import recover_extractions

    client, _, collection = library
    document = Document.objects.get(pk=upload(client, collection).data["id"])
    job = document.source.job
    with patch("modules.documents.tasks.enqueue") as enqueue:
        recover_extractions()
        enqueue.assert_not_called()
        for recovery in range(4):
            old_attempt = str(job.attempt)
            ExtractionJob.objects.filter(pk=job.pk).update(
                state="EXTRACTING" if recovery % 2 else "QUEUED",
                updated_at=timezone.now() - timedelta(seconds=91),
            )
            with django_capture_on_commit_callbacks(execute=True):
                recover_extractions()
            job.refresh_from_db()
            assert job.recoveries == min(recovery + 1, 3)
            assert job.state == ("QUEUED" if recovery < 3 else "FAILED")
            with patch("modules.documents.tasks.parse_source") as parser:
                extract_source(str(document.source.pk), old_attempt)
            parser.assert_not_called()
        assert enqueue.call_count == 3
    assert job.retryable

    # Manual retry resets the bounded recovery budget.
    document.refresh_from_db()
    response = client.post(
        f"/api/v1/documents/{document.pk}/retry",
        {"expectedRevision": document.revision},
        format="json",
    )
    assert response.status_code == 200
    job.refresh_from_db()
    assert job.recoveries == 0
    Membership.objects.filter(user=document.created_by).update(active=False)
    ExtractionJob.objects.filter(pk=job.pk).update(
        updated_at=timezone.now() - timedelta(seconds=91)
    )
    with patch("modules.documents.tasks.enqueue") as enqueue:
        recover_extractions()
        enqueue.assert_not_called()
    job.refresh_from_db()
    assert job.state == "FAILED" and not job.retryable
