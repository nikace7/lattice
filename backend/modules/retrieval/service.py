"""Both ranking paths start from the same current, authorized active index IDs."""

import hashlib
import json
import logging
import time
from functools import lru_cache
from threading import Lock

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import connection, transaction
from django.db.models import Case, F, Func, OuterRef, Q, Subquery, TextField, UUIDField, Value, When
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Cast, Coalesce
from pgvector.django import CosineDistance
from rest_framework.exceptions import APIException, PermissionDenied, Throttled, ValidationError

from config.api import Conflict
from modules.documents.models import Chunk, IndexVersion, SourceBlock
from modules.workspaces.access import locked_membership, readable_collections
from modules.workspaces.models import Workspace
from pipeline.chunking import InvalidIndex
from pipeline.embedding import PROFILE, LocalEmbedder, model_directory, validate_vectors
from pipeline.ranking import rank_hits

from .models import SearchRun

logger = logging.getLogger(__name__)
model_lock = Lock()


class SearchUnavailable(APIException):
    status_code = 503
    default_detail = "Search is temporarily unavailable. Please retry."


@lru_cache(maxsize=1)
def query_model(root):
    return LocalEmbedder(model_directory(root))


def embed_query(query, workspace_id):
    # ponytail: one CPU inference per API process; a dedicated model service if load warrants it.
    if not model_lock.acquire(blocking=False):
        raise SearchUnavailable("Semantic search is busy. Please retry shortly.")
    try:
        from modules.documents.lifecycle import reserve_embeddings

        model = query_model(settings.MODEL_CACHE_ROOT)
        tokens = len(model.tokenizer("query: " + query, add_special_tokens=True)["input_ids"])
        if tokens > 512:
            raise InvalidIndex("The search query exceeds 512 embedding tokens. Shorten it.")
        with transaction.atomic():
            workspace = Workspace.objects.select_for_update().get(pk=workspace_id)
            reserve_embeddings(workspace, tokens)
        vector = model.embed([query], query=True)
        validate_vectors(vector, 1)
        return vector[0]
    except Throttled:
        raise
    except InvalidIndex as error:
        raise ValidationError(str(error)) from error
    except Exception as error:
        logger.warning("Query embedding failed: %s", type(error).__name__)
        raise SearchUnavailable(
            "Local search model unavailable. Ask an operator to prepare it."
        ) from error
    finally:
        model_lock.release()


def corpus(user, workspace_id, data):
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout = '10s'")
    member = locked_membership(user, workspace_id)
    if data["details"] and member.role not in {"OWNER", "CURATOR"}:
        raise PermissionDenied("Retrieval details are available to curators and owners.")
    collections = readable_collections(user).filter(workspace_id=workspace_id)
    if "collectionIds" in data:
        collections = collections.filter(pk__in=data["collectionIds"])
    scope = sorted(str(pk) for pk in collections.values_list("pk", flat=True))
    indexes = IndexVersion.objects.filter(
        active=True,
        state="READY",
        extraction__source__document__deleted_at__isnull=True,
        extraction__source__purge_requested_at__isnull=True,
        extraction__source__document__collection_id__in=scope,
    )
    rows = list(indexes.order_by("id").values("id", "profile", "chunker", "chunk_count"))
    if data["mode"] != "KEYWORD":
        if settings.RAG_MODE not in {"LOCAL", "RETRIEVAL_ONLY"}:
            raise ValidationError("Semantic search currently requires the local E5 profile.")
        if any(row["profile"] != PROFILE for row in rows):
            raise ValidationError(
                "This scope contains indexes without the current semantic profile. "
                "Choose keyword search or select collections with matching semantic indexes."
            )
    return member, scope, rows


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def candidates(indexes, query, vector, mode):
    chunks = (
        Chunk.objects.filter(index_id__in=[row["id"] for row in indexes])
        .annotate(
            document_id=F("index__extraction__source__document_id"),
        )
        .select_related("index__extraction__source__document")
    )
    lexical, semantic = [], []
    if mode != "SEMANTIC":
        lexical_chunks = chunks.annotate(
            first_block=KeyTextTransform("block_id", KeyTransform(0, "spans"))
        )
        heading = SourceBlock.objects.filter(
            id=Cast(OuterRef("first_block"), UUIDField()),
            extraction_id=OuterRef("index__extraction_id"),
        ).values("locator__headingPath")[:1]
        # NFC is only for matching; returned chunks and source offsets remain untouched.
        lexical_chunks = lexical_chunks.annotate(
            heading=Coalesce(
                Cast(Subquery(heading), TextField()), Value(""), output_field=TextField()
            ),
            search_config=Case(
                When(
                    Q(text__regex="[\u0900-\u097f]")
                    | Q(heading__regex="[\u0900-\u097f]")
                    | Q(index__extraction__source__document__title__regex="[\u0900-\u097f]"),
                    then=Value("simple"),
                ),
                default=Value("english"),
                output_field=TextField(),
            ),
        )
        config = F("search_config")
        search_vector = (
            SearchVector(
                Func(F("index__extraction__source__document__title"), function="normalize"),
                config=config,
                weight="A",
            )
            + SearchVector(Func(F("heading"), function="normalize"), config=config, weight="B")
            + SearchVector(Func(F("text"), function="normalize"), config=config, weight="D")
        )
        search_query = SearchQuery(query, config=config, search_type="websearch")
        lexical = list(
            lexical_chunks.annotate(
                search=search_vector, score=SearchRank(search_vector, search_query)
            )
            .filter(search=search_query)
            .order_by("-score", "id")[:20]
        )
    if mode != "KEYWORD":
        semantic = list(
            chunks.filter(embedding__isnull=False)
            .annotate(score=CosineDistance("embedding__vector", vector))
            .order_by("score", "id")[:20]
        )
    return lexical, semantic


def search(user, workspace_id, data):
    started = time.monotonic()
    # Do model loading/inference outside the workspace lock, then recheck the complete scope.
    with transaction.atomic():
        member, scope, indexes = corpus(user, workspace_id, data)
        snapshot = digest([member.workspace.access_epoch, scope, indexes])
    vector = (
        embed_query(data["query"], workspace_id) if indexes and data["mode"] != "KEYWORD" else None
    )
    with transaction.atomic():
        member, scope, indexes = corpus(user, workspace_id, data)
        if digest([member.workspace.access_epoch, scope, indexes]) != snapshot:
            raise Conflict("Search scope changed. Please search again.")
        lexical, semantic = candidates(indexes, data["query"], vector, data["mode"])
        selected = rank_hits(lexical, semantic)
        results = []
        block_ids = {span["block_id"] for row in selected for span in row["chunk"].spans}
        locations = {
            str(block.pk): block.locator
            for block in SourceBlock.objects.filter(
                pk__in=block_ids, extraction__indexes__id__in=[row["id"] for row in indexes]
            )
        }
        for row in selected:
            chunk = row["chunk"]
            extraction = chunk.index.extraction
            source = extraction.source
            results.append(
                {
                    "chunkId": str(chunk.pk),
                    "documentId": str(source.document_id),
                    "sourceId": str(source.pk),
                    "indexId": str(chunk.index_id),
                    "title": source.document.title,
                    "text": chunk.text,
                    "partial": bool(
                        extraction.excluded_pages or (source.kind == "DOCX" and extraction.warnings)
                    ),
                    "spans": chunk.spans,
                    "locations": [locations[span["block_id"]] for span in chunk.spans],
                }
            )
        metadata = {
            "mode": data["mode"],
            "scope": scope,
            "corpusHash": snapshot,
            "profileHash": digest([row["profile"] for row in indexes]),
            "indexIds": [str(row["id"]) for row in indexes],
            "accessEpoch": member.workspace.access_epoch,
            "elapsedMs": round((time.monotonic() - started) * 1000),
            "lexical": [{"chunkId": str(c.pk), "score": c.score} for c in lexical],
            "vector": [{"chunkId": str(c.pk), "distance": c.score} for c in semantic],
            "selected": [
                {"chunkId": str(row["chunk"].pk), **{k: v for k, v in row.items() if k != "chunk"}}
                for row in selected
            ],
        }
        run = SearchRun.objects.create(workspace_id=workspace_id, actor=user, metadata=metadata)
        return {
            "runId": str(run.pk),
            "mode": data["mode"],
            "results": results,
            "diagnostics": metadata if data["details"] else None,
        }
