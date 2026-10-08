"""Real PostgreSQL lifecycle checks; no model quality is inferred from fixtures."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, transaction
from rest_framework.exceptions import Throttled

from modules.documents.models import Document, IndexVersion
from modules.documents.storage import source_directory
from tests import test_document_sources as sources
from tests import test_indexing as indexing_tests
from tests.test_retrieval import indexed, search

library = sources.library
index_runtime = indexing_tests.index_runtime
run_index = indexing_tests.run_index
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def private_spool(settings, tmp_path):
    settings.PARSER_SPOOL_ROOT = tmp_path / "parser"


def test_replacement_keeps_searchable_version_and_replays(library):
    client, _, collection = library
    old = indexed(collection, "Old leave policy")
    document = old.index.extraction.source.document
    key = str(uuid.uuid4())

    def replace(body=b"New leave policy"):
        with patch("modules.documents.tasks.extract_source.delay"):
            return client.post(
                f"/api/v1/documents/{document.pk}/replace",
                {
                    "uploadId": key,
                    "expectedRevision": 1,
                    "file": SimpleUploadedFile("new.txt", body),
                },
                format="multipart",
            )

    first = replace()
    assert first.status_code == 201, first.data
    assert first.data["currentSourceId"] == str(old.index.extraction.source_id)
    assert replace().status_code == 200
    assert replace(b"different").status_code == 409
    assert document.versions.count() == 2
    old.index.refresh_from_db()
    assert old.index.active
    assert search(client, collection, mode="KEYWORD").status_code == 200


def test_delete_denies_reads_fences_workers_and_purge_replays(library):
    from modules.documents.lifecycle import purge_documents

    client, reader, collection = library
    chunk = indexed(collection, "Private leave text")
    source = chunk.index.extraction.source
    document = source.document
    directory = source_directory(source)
    directory.mkdir(parents=True)
    (directory / "original").write_text("Private leave text")
    response = client.post(
        f"/api/v1/documents/{document.pk}/delete", {"expectedRevision": 1}, format="json"
    )
    assert response.status_code == 204
    assert client.get(f"/api/v1/documents/{document.pk}").status_code == 404
    assert client.get(f"/api/v1/sources/{source.pk}/original").status_code == 404
    assert not IndexVersion.objects.filter(extraction__source=source, active=True).exists()
    purge_documents()
    purge_documents()
    assert not directory.exists()
    assert not document.versions.exists()
    assert Document.objects.get(pk=document.pk).purged_at is not None


def test_reader_cannot_delete_or_replace(library):
    client, reader, collection = library
    chunk = indexed(collection, "Leave policy")
    document = chunk.index.extraction.source.document
    client.force_login(reader)
    assert (
        client.post(
            f"/api/v1/documents/{document.pk}/delete", {"expectedRevision": 1}, format="json"
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/documents/{document.pk}/replace",
            {
                "uploadId": str(uuid.uuid4()),
                "expectedRevision": 1,
                "file": SimpleUploadedFile("new.txt", b"replacement"),
            },
            format="multipart",
        ).status_code
        == 403
    )


def test_shadow_reindex_switches_all_at_once_and_retains_old_indexes(library, index_runtime):
    from modules.documents.models import Reindex

    client, _, collection = library
    old = [
        indexed(collection, "First leave policy").index,
        indexed(collection, "Second leave policy").index,
    ]
    with patch("modules.documents.indexing.build_index.delay"):
        response = client.post(
            f"/api/v1/workspaces/{collection.workspace_id}/reindex",
            {"profile": "NONE"},
            format="json",
        )
    assert response.status_code == 202, response.data
    batch = Reindex.objects.get(pk=response.data["id"])
    staged = list(batch.indexes.order_by("id"))
    run_index(staged[0])
    assert IndexVersion.objects.filter(pk__in=[i.pk for i in old], active=True).count() == 2
    run_index(staged[1])
    batch.refresh_from_db()
    assert batch.state == "READY" and batch.indexes.filter(active=True).count() == 2
    assert not IndexVersion.objects.filter(pk__in=[i.pk for i in old], active=True).exists()
    assert all(i.chunks.exists() for i in old)
    collection.workspace.refresh_from_db()
    assert collection.workspace.index_profile["provider"] == "NONE"


def test_purge_scrubs_dependent_history_and_reapplies_after_restore(library, settings):
    from modules.conversations.models import Turn
    from modules.documents.lifecycle import purge_documents, reapply_tombstones
    from tests.test_conversations import ask, run

    settings.RAG_MODE = "LOCAL"
    client, _, collection = library
    chunk = indexed(collection, "Request leave five working days ahead.")
    response, _ = ask(client, collection)
    turn = Turn.objects.get(pk=response.data["id"])
    run(turn)
    assert turn.answer
    document = chunk.index.extraction.source.document
    assert (
        client.post(
            f"/api/v1/documents/{document.pk}/delete", {"expectedRevision": 1}, format="json"
        ).status_code
        == 204
    )
    assert client.get(f"/api/v1/turns/{turn.pk}").data["unavailable"]
    # Simulate restoring pre-delete database rows with the current independent journal.
    Document.objects.filter(pk=document.pk).update(deleted_at=None)
    document.versions.update(purge_requested_at=None)
    reapply_tombstones()
    purge_documents()
    turn.refresh_from_db()
    assert turn.answer is None and turn.answer_purged
    assert client.get(f"/api/v1/turns/{turn.pk}").data["unavailable"]


def test_newer_replacement_fences_old_attempt_then_activates(library, index_runtime):
    from modules.documents.models import SourceVersion
    from modules.documents.tasks import extract_source

    client, _, collection = library
    old = indexed(collection, "Original leave policy")
    document = old.index.extraction.source.document
    keys = [uuid.uuid4(), uuid.uuid4()]
    with patch("modules.documents.tasks.extract_source.delay"):
        for revision, key in enumerate(keys, 1):
            response = client.post(
                f"/api/v1/documents/{document.pk}/replace",
                {
                    "uploadId": str(key),
                    "expectedRevision": revision,
                    "file": SimpleUploadedFile("new.txt", b"Replacement leave policy"),
                },
                format="multipart",
            )
            assert response.status_code == 201
    abandoned = SourceVersion.objects.get(pk=keys[0])
    extract_source(str(abandoned.pk), str(abandoned.job.attempt))
    assert not hasattr(abandoned, "extraction") and abandoned.job.state == "CANCELLED"
    sources.process(document.pk)
    with patch("modules.documents.indexing.build_index.delay"):
        assert indexing_tests.request_index(client, document).status_code == 200
    replacement = document.source.extraction.index
    run_index(replacement)
    old.index.refresh_from_db()
    assert replacement.active and not old.index.active
    assert old.index.chunks.exists()
    assert client.get(f"/api/v1/sources/{old.index.extraction.source_id}/blocks").status_code == 200


def test_cancelled_shadow_cannot_publish_and_failed_shadow_keeps_old(library, index_runtime):
    from modules.documents.lifecycle import fail_reindexes
    from modules.documents.models import Reindex

    client, _, collection = library
    old = indexed(collection, "Original leave policy").index
    path = f"/api/v1/workspaces/{collection.workspace_id}/reindex"
    with patch("modules.documents.indexing.build_index.delay"):
        response = client.post(path, {"profile": "NONE"}, format="json")
    batch = Reindex.objects.get(pk=response.data["id"])
    queued = batch.indexes.get()
    assert client.delete(path).status_code == 204
    run_index(queued)
    old.refresh_from_db()
    assert old.active and not queued.active
    with patch("modules.documents.indexing.build_index.delay"):
        response = client.post(path, {"profile": "E5"}, format="json")
    batch = Reindex.objects.get(pk=response.data["id"])
    batch.indexes.update(state="FAILED")
    fail_reindexes()
    batch.refresh_from_db()
    old.refresh_from_db()
    assert batch.state == "FAILED" and old.active


def test_embedding_reservations_are_atomic(library):
    from modules.documents.lifecycle import reserve_embeddings
    from modules.documents.models import EmbeddingUsage
    from modules.workspaces.models import Workspace

    _, _, collection = library
    Workspace.objects.filter(pk=collection.workspace_id).update(daily_embedding_tokens=100)

    def reserve(_):
        close_old_connections()
        try:
            with transaction.atomic():
                workspace = Workspace.objects.select_for_update().get(pk=collection.workspace_id)
                reserve_embeddings(workspace, 60)
            return True
        except Throttled:
            return False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [False, True]
    assert list(EmbeddingUsage.objects.values_list("tokens", flat=True)) == [60]


def test_purge_failure_keeps_tombstone_and_retries(library):
    from modules.documents.lifecycle import purge_documents, remove_source_files

    client, _, collection = library
    chunk = indexed(collection, "Private leave policy")
    source = chunk.index.extraction.source
    directory = source_directory(source)
    directory.mkdir(parents=True)
    (directory / "original").write_text("private")
    client.post(
        f"/api/v1/documents/{source.document_id}/delete", {"expectedRevision": 1}, format="json"
    )

    def interrupted(value):
        remove_source_files(value)
        raise OSError("Simulated crash after files were removed")

    with patch("modules.documents.lifecycle.remove_source_files", side_effect=interrupted):
        with pytest.raises(OSError):
            purge_documents()
    assert source.document.versions.exists()
    assert client.get(f"/api/v1/sources/{source.pk}/original").status_code == 404
    purge_documents()
    assert not source.document.versions.exists()
