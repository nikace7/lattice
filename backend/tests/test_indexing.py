"""PostgreSQL index publication checks. Model math is separately checked by models:check."""

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from modules.documents import indexing
from modules.documents.models import IndexVersion
from modules.workspaces.models import Membership
from tests import test_document_sources as sources
from tests.test_chunking_embedding import CharacterTokenizer
from tests.test_document_formats import docx_bytes
from tests.test_document_sources import process, upload

library = sources.library

pytestmark = pytest.mark.django_db


@contextmanager
def inline_heartbeat(index_id, attempt):
    yield lambda: indexing.renew(index_id, attempt)


@pytest.fixture
def index_runtime(settings):
    settings.RAG_MODE = "LOCAL"
    with (
        patch.object(indexing, "model_directory", return_value="test-only"),
        patch.object(indexing, "load_tokenizer", return_value=CharacterTokenizer()),
        patch.object(indexing, "LocalEmbedder") as model,
        patch.object(indexing, "heartbeat", side_effect=inline_heartbeat),
    ):
        model.return_value.embed.side_effect = lambda texts: [[1.0] + [0.0] * 383 for _ in texts]
        yield model.return_value


def request_index(client, document):
    revision = client.get(f"/api/v1/documents/{document.pk}").data["revision"]
    return client.post(f"/api/v1/documents/{document.pk}/index", {"expectedRevision": revision})


def run_index(index):
    indexing.build_index(str(index.pk), str(index.attempt))
    index.refresh_from_db()


def test_index_scope_review_and_complete_publication(library, index_runtime):
    client, reader, collection = library
    document = process(upload(client, collection).data["id"])
    owner = document.created_by
    client.force_login(reader)
    assert request_index(client, document).status_code == 403
    client.force_login(owner)
    extraction = document.source.extraction
    extraction.warnings = ["Review required"]
    extraction.save()
    assert request_index(client, document).status_code == 409
    extraction.warnings = []
    extraction.save()
    assert request_index(client, document).status_code == 200
    index = IndexVersion.objects.get(extraction=extraction)
    assert not index.active
    run_index(index)
    assert index.active and index.state == "READY"
    assert index.chunk_count == index.chunks.filter(embedding__isnull=False).count() > 0
    assert request_index(client, document).status_code == 409
    run_index(index)  # Duplicate delivery does not duplicate chunks or vectors.
    assert index.chunk_count == index.chunks.count()


def test_partial_batches_resume_without_publishing_and_cancel_fences_late_batch(
    library, index_runtime
):
    client, _, collection = library
    document = process(upload(client, collection, b"Text " * 4000).data["id"])
    assert request_index(client, document).status_code == 200
    index = IndexVersion.objects.get(extraction__source__document=document)
    index_runtime.embed.side_effect = [
        [[1.0] + [0.0] * 383] * 32,
        RuntimeError("test interruption"),
    ]
    run_index(index)
    assert index.state == "FAILED" and not index.active
    assert index.chunks.filter(embedding__isnull=False).count() == 32
    old_attempt = str(index.attempt)
    assert request_index(client, document).status_code == 200
    index.refresh_from_db()
    indexing.build_index(str(index.pk), old_attempt)
    index.refresh_from_db()
    assert index.state == "QUEUED"

    def cancel_during_batch(texts):
        revision = client.get(f"/api/v1/documents/{document.pk}").data["revision"]
        assert (
            client.post(
                f"/api/v1/documents/{document.pk}/cancel-index", {"expectedRevision": revision}
            ).status_code
            == 200
        )
        return [[1.0] + [0.0] * 383 for _ in texts]

    index_runtime.embed.side_effect = cancel_during_batch
    run_index(index)
    assert index.state == "CANCELLED" and not index.active
    assert index.chunks.filter(embedding__isnull=False).count() == 32
    assert request_index(client, document).status_code == 200
    index.refresh_from_db()
    index_runtime.embed.side_effect = lambda texts: [[1.0] + [0.0] * 383 for _ in texts]
    run_index(index)
    assert index.active


def test_revocation_and_expiry_prevent_publication(library, index_runtime):
    client, _, collection = library
    document = process(upload(client, collection).data["id"])
    request_index(client, document)
    index = IndexVersion.objects.get(extraction__source__document=document)

    def revoke(texts):
        Membership.objects.filter(user=document.created_by, workspace=collection.workspace).update(
            active=False
        )
        return [[1.0] + [0.0] * 383 for _ in texts]

    index_runtime.embed.side_effect = revoke
    run_index(index)
    assert index.state == "FAILED" and not index.active
    assert not index.chunks.filter(embedding__isnull=False).exists()
    assert client.get(f"/api/v1/documents/{document.pk}").status_code in {403, 404}
    Membership.objects.filter(user=document.created_by, workspace=collection.workspace).update(
        active=True
    )
    request_index(client, document)
    index.refresh_from_db()
    old_attempt = index.attempt
    IndexVersion.objects.filter(pk=index.pk).update(
        updated_at=timezone.now() - timedelta(seconds=91)
    )
    indexing.recover_indexes()
    index.refresh_from_db()
    assert index.attempt != old_attempt and index.recoveries == 1
    indexing.build_index(str(index.pk), str(old_attempt))
    index.refresh_from_db()
    assert index.state == "QUEUED" and not index.active


def test_accepted_exclusions_and_explicit_lexical_profile(library, index_runtime, settings):
    client, _, collection = library
    document = process(upload(client, collection).data["id"])
    extraction = document.source.extraction
    first, second = list(extraction.blocks.order_by("position"))
    first.locator, second.locator = {"page": 1}, {"page": 2}
    first.save()
    second.save()
    extraction.excluded_pages = [2]
    extraction.save()
    settings.RAG_MODE = "RETRIEVAL_ONLY"
    assert request_index(client, document).status_code == 200
    index = IndexVersion.objects.get(extraction=extraction)
    run_index(index)
    assert index.active and index.profile["provider"] == "NONE"
    assert not index.chunks.filter(embedding__isnull=False).exists()
    assert all(span["block_id"] == str(first.pk) for c in index.chunks.all() for span in c.spans)
    index_runtime.embed.assert_not_called()


def test_word_omissions_require_review_without_invented_pages(library, index_runtime):
    client, _, collection = library
    data = docx_bytes(
        "<w:p><w:r><w:t>Policy text</w:t></w:r></w:p>", extra={"word/header1.xml": "omitted"}
    )
    document = process(upload(client, collection, data, "policy.docx").data["id"])
    assert request_index(client, document).status_code == 409
    revision = client.get(f"/api/v1/documents/{document.pk}").data["revision"]
    review = {"expectedRevision": revision, "excludedPages": [1], "reason": "Reviewed omissions"}
    assert (
        client.post(
            f"/api/v1/documents/{document.pk}/accept-review", review, format="json"
        ).status_code
        == 400
    )
    review["excludedPages"] = []
    assert (
        client.post(
            f"/api/v1/documents/{document.pk}/accept-review", review, format="json"
        ).status_code
        == 200
    )
    assert request_index(client, document).status_code == 200
    index = IndexVersion.objects.get(extraction__source__document=document)
    run_index(index)
    assert index.active
