"""PostgreSQL tests: numerical vectors are fixtures, not measured E5 quality."""

import hashlib
import uuid
from unittest.mock import patch

import pytest

from modules.collections.models import Collection, CollectionGrant
from modules.documents.models import (
    Chunk,
    Document,
    Embedding384,
    ExtractionJob,
    ExtractionVersion,
    IndexVersion,
    SourceBlock,
    SourceVersion,
)
from modules.retrieval.models import SearchRun
from modules.workspaces.models import Membership, Workspace
from pipeline.embedding import PROFILE
from tests import test_document_sources as sources

library = sources.library
pytestmark = pytest.mark.django_db


def indexed(collection, text, *, title="Same policy", profile=None, vector=None, active=True):
    owner = collection.workspace.memberships.get(role="OWNER").user
    document = Document.objects.create(collection=collection, title=title, created_by=owner)
    digest = hashlib.sha256(text.encode()).hexdigest()
    source = SourceVersion.objects.create(
        document=document,
        filename="policy.txt",
        kind="TXT",
        byte_size=len(text.encode()),
        sha256=digest,
    )
    ExtractionJob.objects.create(source=source, state="EXTRACTED")
    extraction = ExtractionVersion.objects.create(source=source, parser_version="retrieval-fixture")
    block = SourceBlock.objects.create(
        extraction=extraction,
        position=0,
        original_text=text,
        text=text,
        locator={"line": 1},
        span_map=[[0, len(text), 0, len(text)]],
    )
    index = IndexVersion.objects.create(
        extraction=extraction,
        requested_by=owner,
        profile=PROFILE if profile is None else profile,
        chunker="retrieval-fixture",
        state="READY" if active else "EMBEDDING",
        active=active,
        chunk_count=1,
    )
    chunk = Chunk.objects.create(
        index=index,
        position=0,
        text=text,
        sha256=digest,
        spans=[
            {
                "block_id": str(block.pk),
                "start": 0,
                "end": len(text),
                "chunk_start": 0,
                "chunk_end": len(text),
            }
        ],
        token_count=20,
    )
    if index.profile == PROFILE:
        Embedding384.objects.create(chunk=chunk, vector=vector or [1.0] + [0.0] * 383)
    return chunk


def search(client, collection, **data):
    return client.post(
        f"/api/v1/workspaces/{collection.workspace_id}/search",
        {"query": "leave", **data},
        format="json",
    )


def test_all_paths_filter_before_limit_and_reject_forged_scope(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, reader, collection = library
    permitted = indexed(collection, "leave notice five days", vector=[0.0, 1.0] + [0.0] * 382)
    restricted = Collection.objects.create(
        workspace=collection.workspace, title="Policies", access="RESTRICTED"
    )
    for _ in range(21):
        indexed(restricted, "leave leave leave confidential")
    other = Workspace.objects.create(name="Same library")
    Membership.objects.create(workspace=other, user=permitted.index.requested_by, role="OWNER")
    foreign = Collection.objects.create(workspace=other, title=collection.title)
    indexed(foreign, "leave confidential foreign")
    indexed(collection, "leave unpublished", active=False)
    client.force_login(reader)
    with patch("modules.retrieval.service.embed_query", return_value=[1.0] + [0.0] * 383):
        for mode in ["KEYWORD", "SEMANTIC", "HYBRID"]:
            response = search(client, collection, mode=mode)
            assert response.status_code == 200, response.data
            assert [h["chunkId"] for h in response.data["results"]] == [str(permitted.pk)]
            assert response.data["diagnostics"] is None
            assert response["Cache-Control"] == "no-store"
        for scope in [[], [str(restricted.pk)], [str(foreign.pk)], [str(uuid.uuid4())]]:
            response = search(client, collection, collectionIds=scope)
            assert response.status_code == 200 and not response.data["results"]
    assert search(client, collection, details=True).status_code == 403
    assert search(client, foreign).status_code == 404
    assert search(client, collection, query="x" * 4001).status_code == 400


def test_lexical_unicode_heading_weights_ties_and_source_scope(library):
    client, _, collection = library
    title = indexed(collection, "General procedure", title="leave")
    body = indexed(collection, "leave notice five days")
    tied = indexed(collection, "leave notice five days")
    nepali = indexed(collection, "बिदा पाँच दिन अगाडि माग्नुहोस्।", title="बिदा नीति")
    decomposed = indexed(collection, "Cafe\u0301 rules", title="Unicode")
    response = search(client, collection, details=True)
    assert response.status_code == 200, response.data
    assert response.data["results"][0]["chunkId"] == str(title.pk)
    ranks = response.data["diagnostics"]["lexical"]
    tied_ids = [r["chunkId"] for r in ranks if r["chunkId"] in {str(body.pk), str(tied.pk)}]
    assert tied_ids == sorted(tied_ids)
    assert search(client, collection, query="बिदा").data["results"][0]["chunkId"] == str(nepali.pk)
    assert search(client, collection, query="Café").data["results"][0]["chunkId"] == str(
        decomposed.pk
    )
    source = body.index.extraction.source
    url = f"/api/v1/sources/{source.pk}/blocks?chunkId="
    assert client.get(url + str(body.pk)).data["results"][0]["text"] == body.text
    assert client.get(url + str(nepali.pk)).status_code == 404
    assert client.get(url + "invalid").status_code == 400
    assert all("query" not in run.metadata for run in SearchRun.objects.all())
    body.index.extraction.blocks.update(locator={"line": 1, "headingPath": ["Reimbursement"]})
    heading_result = search(client, collection, query="Reimbursement")
    assert heading_result.data["results"][0]["chunkId"] == str(body.pk)


def test_profiles_empty_scope_and_revocation_during_embedding(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, reader, collection = library
    chunk = indexed(collection, "leave notice")
    with patch("modules.retrieval.service.embed_query") as embedding:
        assert not search(client, collection, mode="HYBRID", collectionIds=[]).data["results"]
        embedding.assert_not_called()
    chunk.index.profile = {"provider": "NONE", "dimensions": 0}
    chunk.index.save()
    with patch("modules.retrieval.service.embed_query") as embedding:
        assert search(client, collection, mode="HYBRID").status_code == 400
        embedding.assert_not_called()
    chunk.index.profile = PROFILE
    chunk.index.save()
    collection.access = "RESTRICTED"
    collection.save()
    member = Membership.objects.get(workspace=collection.workspace, user=reader)
    grant = CollectionGrant.objects.create(collection=collection, membership=member, can_read=True)
    client.force_login(reader)

    run_count = SearchRun.objects.count()

    def revoke(_, workspace_id):
        grant.delete()
        return [1.0] + [0.0] * 383

    with patch("modules.retrieval.service.embed_query", side_effect=revoke):
        assert search(client, collection, mode="HYBRID").status_code == 409
    assert SearchRun.objects.count() == run_count


def test_semantic_order_and_safe_details_do_not_elevate_curator(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, reader, collection = library
    best = indexed(collection, "Vacation schedule", vector=[1.0] + [0.0] * 383)
    worse = indexed(collection, "Leave calendar", vector=[0.0, 1.0] + [0.0] * 382)
    Membership.objects.filter(user=reader).update(role="CURATOR")
    hidden = Collection.objects.create(
        workspace=collection.workspace, title="Secrets", access="RESTRICTED"
    )
    secret = indexed(hidden, "Secret leave calendar")
    client.force_login(reader)
    with patch("modules.retrieval.service.embed_query", return_value=[1.0] + [0.0] * 383):
        response = search(client, collection, mode="SEMANTIC", details=True)
    assert response.status_code == 200, response.data
    assert [h["chunkId"] for h in response.data["results"]] == [str(best.pk), str(worse.pk)]
    assert [h["distance"] for h in response.data["diagnostics"]["vector"]] == [0.0, 1.0]
    assert str(secret.pk) not in str(response.data)
    Membership.objects.filter(user=reader).update(active=False)
    assert search(client, collection).status_code == 404
