"""Inactive staging, resumable vector batches and lease-fenced index publication."""

import logging
import time
import uuid
from contextlib import contextmanager
from functools import partial
from threading import Event, Thread

from celery import shared_task
from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import F
from django.utils import timezone
from kombu.exceptions import OperationalError

from modules.workspaces.access import can_write
from modules.workspaces.models import Membership, Workspace
from pipeline.chunking import VERSION, InvalidIndex, chunk_blocks
from pipeline.embedding import (
    PROFILE,
    LocalEmbedder,
    load_tokenizer,
    model_directory,
    validate_vectors,
)

from .models import LEASE_DURATION, Chunk, Document, Embedding384, IndexVersion

logger = logging.getLogger(__name__)
RUNNING = ["QUEUED", "CHUNKING", "EMBEDDING"]


class IndexStopped(Exception):
    pass


def configured_profile():
    if settings.RAG_MODE == "LOCAL":
        return PROFILE
    if settings.RAG_MODE == "RETRIEVAL_ONLY":
        return {"provider": "NONE", "dimensions": 0, "tokenizer": PROFILE["tokenizer"]}
    raise InvalidIndex("Indexing currently supports LOCAL and RETRIEVAL_ONLY modes.")


def permitted(index):
    document = index.extraction.source.document
    member = Membership.objects.filter(
        workspace_id=document.collection.workspace_id,
        user=index.requested_by,
        active=True,
        user__is_active=True,
    ).first()
    return member and can_write(document.collection, member)


def enqueue_index(index_id, attempt):
    try:
        build_index.delay(index_id, attempt)
    except OperationalError:
        IndexVersion.objects.filter(pk=index_id, attempt=attempt, state="QUEUED").update(
            state="FAILED",
            error="The indexing queue is unavailable. Please retry.",
            updated_at=timezone.now(),
        )


def renew(index_id, attempt):
    now = timezone.now()
    if not IndexVersion.objects.filter(
        pk=index_id,
        attempt=attempt,
        state__in=RUNNING,
        updated_at__gt=now - LEASE_DURATION,
    ).update(updated_at=now):
        raise IndexStopped


@contextmanager
def heartbeat(index_id, attempt):
    stop, lost = Event(), Event()
    deadline = time.monotonic() + 1200
    renew(index_id, attempt)

    def keep_alive():
        try:
            while not stop.wait(15):
                if time.monotonic() > deadline:
                    raise IndexStopped
                renew(index_id, attempt)
        except Exception:
            lost.set()
        finally:
            close_old_connections()

    thread = Thread(target=keep_alive, daemon=True)
    thread.start()
    try:

        def check():
            if lost.is_set() or time.monotonic() > deadline:
                raise IndexStopped
            renew(index_id, attempt)

        yield check
    finally:
        stop.set()
        thread.join(timeout=5)


@contextmanager
def locked_attempt(index_id, attempt):
    workspace_id = IndexVersion.objects.values_list(
        "extraction__source__document__collection__workspace_id",
        flat=True,
    ).get(pk=index_id)
    with transaction.atomic():
        Workspace.objects.select_for_update().get(pk=workspace_id)
        index = (
            IndexVersion.objects.select_for_update(of=("self",))
            .select_related(
                "extraction__source__document__collection",
                "extraction__source__job",
            )
            .get(pk=index_id)
        )
        if str(index.attempt) != attempt or index.state not in RUNNING or index.lease_expired:
            raise IndexStopped
        if not permitted(index):
            raise InvalidIndex("Contribution access changed. Ask a curator with access to retry.")
        extraction = index.extraction
        if extraction.source.job.state not in {"EXTRACTED", "REVIEWED"} or (
            extraction.warnings and not extraction.accepted_at
        ):
            raise InvalidIndex("Accept extraction warnings before indexing.")
        if index.profile != configured_profile() or index.chunker != VERSION:
            raise InvalidIndex(
                "Index profile changed. Restore the original profile before retrying."
            )
        yield index


@shared_task(time_limit=1260, soft_time_limit=1230)
def build_index(index_id, attempt):
    if not IndexVersion.objects.filter(pk=index_id, attempt=attempt, state="QUEUED").update(
        state="CHUNKING",
        updated_at=timezone.now(),
    ):
        return
    try:
        with heartbeat(index_id, attempt) as check:
            with locked_attempt(index_id, attempt) as index:
                extraction = index.extraction
            directory = model_directory(settings.MODEL_CACHE_ROOT)
            tokenizer = load_tokenizer(directory)
            chunks = chunk_blocks(
                extraction.blocks.order_by("position"),
                tokenizer,
                extraction.excluded_pages,
                kind=extraction.source.kind,
            )
            check()
            with locked_attempt(index_id, attempt) as index:
                existing = list(index.chunks.order_by("position"))
                if existing:
                    if len(existing) != len(chunks) or any(
                        c.sha256 != data["sha256"] or c.spans != data["spans"]
                        for c, data in zip(existing, chunks, strict=True)
                    ):
                        raise InvalidIndex("Staged chunks no longer match this extraction.")
                else:
                    Chunk.objects.bulk_create(
                        [
                            Chunk(index=index, position=position, **data)
                            for position, data in enumerate(chunks)
                        ],
                        batch_size=500,
                    )
                index.state, index.chunk_count = "EMBEDDING", len(chunks)
                index.save(update_fields=["state", "chunk_count", "updated_at"])
            if index.profile["provider"] != "NONE":
                embedder = LocalEmbedder(directory)
                while True:
                    check()
                    pending = list(
                        index.chunks.filter(embedding__isnull=True).order_by("position")[:32]
                    )
                    if not pending:
                        break
                    vectors = embedder.embed([c.text for c in pending])
                    validate_vectors(vectors, len(pending))
                    check()
                    with locked_attempt(index_id, attempt):
                        Embedding384.objects.bulk_create(
                            [
                                Embedding384(chunk=c, vector=v)
                                for c, v in zip(pending, vectors, strict=True)
                            ]
                        )
            check()
            with locked_attempt(index_id, attempt) as index:
                if (
                    index.chunk_count < 1
                    or index.chunks.count() != index.chunk_count
                    or (
                        index.profile["provider"] != "NONE"
                        and index.chunks.filter(embedding__isnull=True).exists()
                    )
                ):
                    raise InvalidIndex("The index is incomplete and cannot be activated.")
                index.active, index.state, index.error = True, "READY", ""
                index.save(update_fields=["active", "state", "error", "updated_at"])
                Document.objects.filter(pk=extraction.source.document_id).update(
                    revision=F("revision") + 1
                )
    except IndexStopped:
        return
    except Exception as error:
        logger.error("Indexing failed index=%s error_type=%s", index_id, type(error).__name__)
        safe = (
            str(error)[:240]
            if isinstance(error, InvalidIndex)
            else "Local indexing unavailable. Check model setup and retry."
        )
        IndexVersion.objects.filter(pk=index_id, attempt=attempt, state__in=RUNNING).update(
            state="FAILED",
            active=False,
            error=safe,
            updated_at=timezone.now(),
        )


@shared_task
def recover_indexes():
    expired = list(
        IndexVersion.objects.filter(
            state__in=RUNNING,
            updated_at__lte=timezone.now() - LEASE_DURATION,
        )
        .order_by("updated_at")
        .values_list("pk", "extraction__source__document__collection__workspace_id")[:100]
    )
    for index_id, workspace_id in expired:
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=workspace_id)
            index = (
                IndexVersion.objects.select_for_update(of=("self",))
                .select_related(
                    "extraction__source__document__collection",
                )
                .get(pk=index_id)
            )
            if not index.lease_expired:
                continue
            if index.recoveries >= 3 or not permitted(index):
                index.state = "FAILED"
                index.error = (
                    "Automatic index recovery stopped. Check access and workers, then retry."
                )
            else:
                index.state, index.error, index.attempt = "QUEUED", "", uuid.uuid4()
                index.recoveries += 1
                transaction.on_commit(partial(enqueue_index, str(index.pk), str(index.attempt)))
            index.save()
            Document.objects.filter(pk=index.extraction.source.document_id).update(
                revision=F("revision") + 1
            )
