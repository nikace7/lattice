"""Workspace-serialized activation and replayable, fail-closed deletion."""

import json
import logging
import os
import shutil
import time
import uuid
from functools import partial
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, Throttled

from config.api import Conflict
from modules.conversations.models import Turn
from modules.workspaces.models import Workspace
from pipeline.chunking import VERSION, InvalidIndex
from pipeline.embedding import PROFILE

from .models import Document, EmbeddingUsage, ExtractionJob, IndexVersion, Reindex, SourceVersion
from .storage import source_directory

RUNNING = ["QUEUED", "CHUNKING", "EMBEDDING"]
logger = logging.getLogger(__name__)


class LifecycleUnavailable(APIException):
    status_code = 503
    default_detail = (
        "Deletion could not be recorded safely. Ask an operator to check private storage."
    )


def cancel_reindex(batch):
    batch.indexes.filter(state__in=RUNNING).update(state="CANCELLED", updated_at=timezone.now())
    batch.state = "CANCELLED"
    batch.save(update_fields=["state"])


def cancel_pending(document, except_source=None):
    sources = document.versions.exclude(pk=except_source)
    ExtractionJob.objects.filter(source__in=sources, state__in=["QUEUED", "EXTRACTING"]).update(
        state="CANCELLED", retryable=False, updated_at=timezone.now()
    )
    IndexVersion.objects.filter(extraction__source__in=sources, state__in=RUNNING).update(
        state="CANCELLED", updated_at=timezone.now()
    )
    for batch in Reindex.objects.filter(workspace=document.collection.workspace, state="BUILDING"):
        cancel_reindex(batch)


def publish_index(index):
    """Called with the workspace lock and a fresh authorized worker attempt."""
    document = index.extraction.source.document
    workspace = document.collection.workspace
    index.state, index.error = "READY", ""
    index.save(update_fields=["state", "error", "updated_at"])
    if index.reindex_id:
        batch = Reindex.objects.get(pk=index.reindex_id)
        if batch.state != "BUILDING":
            raise InvalidIndex("This reindex was superseded.")
        if batch.indexes.exclude(state="READY").exists():
            return
        current = sorted(
            str(pk)
            for pk in IndexVersion.objects.filter(
                active=True, extraction__source__document__collection__workspace=workspace
            ).values_list("pk", flat=True)
        )
        if current != sorted(batch.previous_indexes):
            raise InvalidIndex("Searchable sources changed; start a fresh reindex.")
        IndexVersion.objects.filter(pk__in=current).update(active=False)
        batch.indexes.update(active=True)
        workspace.index_profile = batch.profile
        batch.state = "READY"
        batch.save(update_fields=["state"])
        documents = Document.objects.filter(versions__pk__in=batch.source_ids)
    else:
        IndexVersion.objects.filter(extraction__source__document=document, active=True).update(
            active=False
        )
        index.active = True
        index.save(update_fields=["active"])
        workspace.index_profile = workspace.index_profile or index.profile
        documents = Document.objects.filter(pk=document.pk)
    workspace.access_epoch += 1
    workspace.save(update_fields=["index_profile", "access_epoch", "updated_at"])
    documents.update(revision=F("revision") + 1)


def start_reindex(workspace, user, profile):
    from .indexing import enqueue_index

    if Reindex.objects.filter(workspace=workspace, state="BUILDING").exists():
        raise Conflict("A workspace reindex is already running.")
    indexes = list(
        IndexVersion.objects.filter(
            active=True,
            extraction__source__document__collection__workspace=workspace,
            extraction__source__document__deleted_at__isnull=True,
        ).select_related("extraction__source__document")
    )
    if not indexes:
        raise Conflict("Prepare at least one searchable document first.")
    if any(i.extraction.source.document.source.pk != i.extraction.source_id for i in indexes):
        raise Conflict("Finish indexing pending replacements before reindexing the workspace.")
    batch = Reindex.objects.create(
        workspace=workspace,
        profile=profile,
        source_ids=[str(i.extraction.source_id) for i in indexes],
        previous_indexes=[str(i.pk) for i in indexes],
    )
    for old in indexes:
        index = IndexVersion.objects.create(
            extraction=old.extraction,
            requested_by=user,
            profile=profile,
            chunker=VERSION,
            reindex=batch,
        )
        transaction.on_commit(partial(enqueue_index, str(index.pk), str(index.attempt)))
    return batch


def reserve_embeddings(workspace, tokens, index=None):
    """Charge known token counts before dispatch; failed/ambiguous calls keep their charge."""
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    used = (
        EmbeddingUsage.objects.filter(workspace=workspace, created_at__gte=today).aggregate(
            total=Sum("tokens")
        )["total"]
        or 0
    )
    if used + tokens > workspace.daily_embedding_tokens:
        raise Throttled(detail="The daily embedding token budget is exhausted. Retry tomorrow.")
    EmbeddingUsage.objects.create(workspace=workspace, index=index, tokens=tokens)


def fail_reindexes():
    for batch_id, workspace_id in Reindex.objects.filter(state="BUILDING").values_list(
        "pk", "workspace_id"
    ):
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=workspace_id)
            batch = Reindex.objects.get(pk=batch_id)
            if (
                batch.state == "BUILDING"
                and batch.indexes.filter(state__in=["FAILED", "CANCELLED"]).exists()
            ):
                cancel_reindex(batch)
                batch.state = "FAILED"
                batch.save(update_fields=["state"])


def write_tombstone(document, source=None):
    root = (Path(settings.STORAGE_ROOT) / "tombstones").resolve()
    root.mkdir(parents=True, exist_ok=True)
    key = f"source-{source.pk}" if source else f"document-{document.pk}"
    path = root / f"{key}.json"
    payload = {
        "document": str(document.pk),
        "workspace": str(document.collection.workspace_id),
        "source": str(source.pk) if source else None,
    }
    if path.exists():
        if path.is_symlink() or json.loads(path.read_text(encoding="utf-8")) != payload:
            raise RuntimeError("Conflicting tombstone record.")
        return
    temporary = root / f"{uuid.uuid4()}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def tombstone(document, source=None, *, journal=True):
    if journal:
        try:
            write_tombstone(document, source)
        except (OSError, ValueError, RuntimeError) as error:
            logger.error(
                "Tombstone failed document=%s error_type=%s", document.pk, type(error).__name__
            )
            raise LifecycleUnavailable from error
    now = timezone.now()
    if source:
        source.purge_requested_at = now
        source.save(update_fields=["purge_requested_at"])
    else:
        document.deleted_at = document.deleted_at or now
        document.revision += 1
        document.save(update_fields=["deleted_at", "revision"])
        document.versions.update(purge_requested_at=now)
        cancel_pending(document)
    indexes = (
        IndexVersion.objects.filter(extraction__source=source)
        if source
        else IndexVersion.objects.filter(extraction__source__document=document)
    )
    indexes.update(active=False)
    Workspace.objects.filter(pk=document.collection.workspace_id).update(
        access_epoch=F("access_epoch") + 1
    )


def clear_dependent_answers(source):
    ids = (
        set(str(pk) for pk in source.extraction.indexes.values_list("chunks__pk", flat=True))
        if hasattr(source, "extraction")
        else set()
    )
    if not ids:
        return
    turns = Turn.objects.filter(
        conversation__workspace_id=source.document.collection.workspace_id, answer__isnull=False
    ).select_related("search_run")
    # ponytail: scan one workspace's retained answers; normalize dependencies if histories grow.
    for turn in turns.iterator(chunk_size=100):
        selected = turn.search_run.metadata.get("selected", []) if turn.search_run else []
        cited = [c for b in turn.answer["blocks"] for c in b["citations"]]
        if ids.intersection(str(c["chunkId"]) for c in selected + cited):
            turn.answer, turn.answer_purged = None, True
            turn.save(update_fields=["answer", "answer_purged"])


def remove_source_files(source):
    root = (Path(settings.STORAGE_ROOT) / "sources").resolve()
    path = source_directory(source)
    if path.is_symlink() or path.resolve().parent != root:
        raise RuntimeError("Source purge path is outside private storage.")
    if path.exists():
        shutil.rmtree(path)


@shared_task
def purge_documents():
    # Files first, database last: interruption leaves a tombstone and a retryable source row.
    ids = list(
        SourceVersion.objects.filter(purge_requested_at__isnull=False).values_list("pk", flat=True)[
            :100
        ]
    )
    for source_id in ids:
        source = (
            SourceVersion.objects.select_related("document__collection")
            .filter(pk=source_id)
            .first()
        )
        if source is None:
            continue
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=source.document.collection.workspace_id)
            source = (
                SourceVersion.objects.select_related("document__collection")
                .filter(pk=source_id, purge_requested_at__isnull=False)
                .first()
            )
            if source is None:
                continue
            clear_dependent_answers(source)
            remove_source_files(source)
            source.delete()
    Document.objects.filter(
        deleted_at__isnull=False, versions__isnull=True, purged_at__isnull=True
    ).update(purged_at=timezone.now(), title="Deleted document")
    clean_orphan_files()


def clean_orphan_files():
    # Parser children are killed by their supervisor after 305 seconds. Leave a full hour.
    cutoff = time.time() - 3600
    roots = [
        (Path(settings.PARSER_SPOOL_ROOT), False),
        (Path(settings.STORAGE_ROOT) / "sources", True),
    ]
    for directory, is_source in roots:
        root = directory.resolve()
        if not root.exists():
            continue
        for path in root.iterdir():
            try:
                key = uuid.UUID(path.name)
            except ValueError:
                continue
            if path.is_symlink() or path.resolve().parent != root or not path.is_dir():
                continue
            if path.stat().st_mtime >= cutoff:
                continue
            if is_source and SourceVersion.objects.filter(pk=key).exists():
                continue
            shutil.rmtree(path)


def reapply_tombstones():
    root = Path(settings.STORAGE_ROOT) / "tombstones"
    for path in root.glob("*.json"):
        if path.is_symlink() or path.stat().st_size > 1024:
            raise ValueError("Invalid tombstone file.")
        data = json.loads(path.read_text(encoding="utf-8"))
        document_id, workspace_id = uuid.UUID(data["document"]), uuid.UUID(data["workspace"])
        source_id = uuid.UUID(data["source"]) if data["source"] else None
        with transaction.atomic():
            workspace = Workspace.objects.select_for_update().filter(pk=workspace_id).first()
            if workspace is None:
                continue
            document = (
                Document.objects.select_related("collection")
                .filter(pk=document_id, collection__workspace=workspace)
                .first()
            )
            if document is None:
                continue
            source = document.versions.filter(pk=source_id).first() if source_id else None
            if source_id and source is None:
                continue
            if source and document.source.pk == source.pk:
                # An older backup may predate the replacement. Never expose a purged source.
                source = None
            tombstone(document, source, journal=False)


def selected_profile(name):
    if name == "E5":
        return PROFILE
    return {"provider": "NONE", "dimensions": 0, "tokenizer": PROFILE["tokenizer"]}
