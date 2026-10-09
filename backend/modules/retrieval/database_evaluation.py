"""Real scoped PostgreSQL ranking on temporary canonical fixtures, always rolled back."""

import time
import uuid

from django.db import connection, transaction

from modules.collections.models import Collection, CollectionGrant
from modules.documents.models import (
    Chunk,
    Document,
    Embedding384,
    ExtractionVersion,
    IndexVersion,
    SourceBlock,
    SourceVersion,
)
from modules.identity.models import User
from modules.workspaces.models import Membership, Workspace
from pipeline.chunking import VERSION
from pipeline.embedding import PROFILE
from pipeline.ranking import normalize_query, rank_hits

from .frozen import permitted_documents, score_cases
from .service import candidates, corpus


def canonical_hit(chunk, labels, allowed):
    document = labels["documents"][str(chunk.document_id)]
    source = labels["sources"][str(chunk.index.extraction.source_id)]
    if document not in allowed:
        raise ValueError("Retrieved hit violates the frozen scope")
    spans = []
    for span in chunk.spans:
        block = labels["blocks"][span["block_id"]]
        start, end = span["start"], span["end"]
        left, right = span["chunk_start"], span["chunk_end"]
        if not (
            block["source"] == source
            and 0 <= start < end <= len(block["text"])
            and 0 <= left < right <= len(chunk.text)
            and block["text"][start:end] == chunk.text[left:right]
        ):
            raise ValueError("Retrieved span has invalid provenance")
        spans.append({**span, "block_id": block["id"]})
    if not spans:
        raise ValueError("Retrieved hit has no span provenance")
    return {
        "chunk": str(chunk.pk),
        "document": document,
        "source": source,
        "text": chunk.text,
        "spans": spans,
    }


def evaluate_database(suite, cases, chunks, vectors, queries):
    results = {mode: [] for mode in ["KEYWORD", "SEMANTIC", "HYBRID"]}
    timings = {mode: [] for mode in results}
    labels = {"documents": {}, "sources": {}, "blocks": {}}
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(782034801)")
            if not cursor.fetchone()[0]:
                raise ValueError("Another demo or database evaluation command is running")
        # Random namespaces isolate fixture records from existing demo data.
        namespace = uuid.uuid4()

        def key(value):
            return uuid.uuid5(namespace, value)

        workspaces = {
            name: Workspace.objects.create(name="Temporary R8 " + name)
            for name in {item["workspace"] for item in suite["documents"]}
        }
        members = {}
        for name, persona in suite["personas"].items():
            user = User.objects.create_user(username="eval-" + key(name).hex)
            members[name] = Membership.objects.create(
                workspace=workspaces[persona["workspace"]],
                user=user,
                role=persona["role"],
            )
        collections = {}
        for item in suite["collections"]:
            collection = Collection.objects.create(
                workspace=workspaces[item["workspace"]],
                title=item["id"],
                access="WORKSPACE" if item["minimumRole"] == "MEMBER" else "RESTRICTED",
            )
            collections[item["id"]] = collection
            if item["minimumRole"] == "CURATOR":
                for member in members.values():
                    if member.workspace_id == collection.workspace_id and member.role == "CURATOR":
                        CollectionGrant.objects.create(
                            collection=collection, membership=member, can_write=True
                        )
        for item in suite["documents"]:
            owner = members[f"{item['workspace']}-owner"].user
            document = Document.objects.create(
                collection=collections[item["collection"]], title=item["title"], created_by=owner
            )
            labels["documents"][str(document.pk)] = item["id"]
            for version in item["sources"]:
                source = SourceVersion.objects.create(
                    document=document,
                    number=version["number"],
                    kind=version["kind"],
                    filename=version["file"],
                    byte_size=0,
                    sha256=version["sha256"],
                    created_by=owner,
                )
                labels["sources"][str(source.pk)] = version["id"]
                if version["id"] != item["activeSource"]:
                    continue
                extraction = ExtractionVersion.objects.create(
                    source=source, parser_version="frozen-canonical-r8-v1"
                )
                for position, block in enumerate(version["blocks"]):
                    block_id = key(block["id"])
                    SourceBlock.objects.create(
                        id=block_id,
                        extraction=extraction,
                        position=position,
                        text=block["text"],
                        original_text=block["text"],
                        locator=block["locator"],
                        span_map=[[0, len(block["text"]), 0, len(block["text"])]],
                    )
                    labels["blocks"][str(block_id)] = {**block, "source": version["id"]}
                selected = [
                    (chunk, vector)
                    for chunk, vector in zip(chunks, vectors, strict=True)
                    if chunk.source_id == version["id"]
                ]
                index = IndexVersion.objects.create(
                    extraction=extraction,
                    requested_by=owner,
                    state="READY",
                    active=True,
                    profile=PROFILE,
                    chunker=VERSION,
                    chunk_count=len(selected),
                )
                for position, (chunk, vector) in enumerate(selected):
                    value = Chunk.objects.create(
                        id=uuid.uuid5(uuid.NAMESPACE_URL, f"lattice-r8:{version['id']}:{position}"),
                        index=index,
                        position=position,
                        text=chunk.text,
                        sha256=chunk.sha256,
                        token_count=chunk.token_count,
                        spans=[
                            {**span, "block_id": str(key(span["block_id"]))} for span in chunk.spans
                        ],
                    )
                    Embedding384.objects.create(chunk=value, vector=vector)
        for case, query in zip(cases, queries, strict=True):
            member = members[case["persona"]]
            allowed = {doc["id"] for doc in permitted_documents(suite, case)}
            for mode in results:
                started = time.monotonic()
                data = {
                    "mode": mode,
                    "details": False,
                    "collectionIds": [str(collections[name].pk) for name in case["collections"]],
                }
                _, scope, indexes = corpus(member.user, member.workspace_id, data)
                scoped_docs = set(
                    Document.objects.filter(collection_id__in=scope).values_list("pk", flat=True)
                )
                if {labels["documents"][str(pk)] for pk in scoped_docs} != allowed:
                    raise ValueError("Real collection grants differ from the frozen scope")
                hits = rank_hits(*candidates(indexes, normalize_query(case["query"]), query, mode))
                results[mode].append([canonical_hit(hit["chunk"], labels, allowed) for hit in hits])
                timings[mode].append(round((time.monotonic() - started) * 1000, 2))
        transaction.set_rollback(True)
    reports = {}
    for mode, retrieved in results.items():
        report = score_cases(cases, retrieved)
        report["unmeasured"].pop("postgresKeyword")
        report["unmeasured"].pop("postgresHybrid")
        reports[mode] = {**report, "unauthorizedHits": 0, "retrievalMs": timings[mode]}
    return reports
