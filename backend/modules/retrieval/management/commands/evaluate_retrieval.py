"""A small reproducible development check; never seeds permanent application data."""

import hashlib
import json
import math
import time
import uuid
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from modules.collections.models import Collection
from modules.documents.models import (
    Chunk,
    Document,
    Embedding384,
    ExtractionVersion,
    IndexVersion,
    SourceBlock,
    SourceVersion,
)
from modules.retrieval.service import candidates, digest
from modules.workspaces.models import Workspace
from pipeline.chunking import VERSION, chunk_blocks
from pipeline.embedding import PROFILE, LocalEmbedder, model_directory
from pipeline.ranking import normalize_query, rank_hits


def metrics(rows):
    report = {}
    for language in sorted({row["language"] for row in rows}):
        group = [row for row in rows if row["language"] == language]
        found = sum(len(set(row["gold"]) & set(row["retrieved"][:8])) for row in group)
        required = sum(len(row["gold"]) for row in group)
        reciprocal = [
            1
            / next((i for i, doc in enumerate(row["retrieved"], 1) if doc in row["gold"]), math.inf)
            for row in group
        ]
        report[language] = {
            "questions": len(group),
            "goldGroupsFound": found,
            "goldGroups": required,
            "evidenceRecallAt8": found / required,
            "anyHitQuestions": sum(bool(set(row["gold"]) & set(row["retrieved"])) for row in group),
            "fullEvidenceQuestions": sum(
                set(row["gold"]).issubset(row["retrieved"]) for row in group
            ),
            "meanReciprocalRank": sum(reciprocal) / len(group),
        }
    return report


class Command(BaseCommand):
    help = "Evaluate the bundled development corpus with real E5; PostgreSQL data is rolled back."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--embedding-only",
            action="store_true",
            help="Offline cosine check only; does not validate PostgreSQL or keyword/hybrid.",
        )

    def handle(self, *args, **options):
        started = time.monotonic()
        suite_path = settings.REPO_ROOT / "fixtures/evals/r4-development.json"
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
        model = LocalEmbedder(model_directory(settings.MODEL_CACHE_ROOT))
        chunks, blocks = [], []
        for doc in suite["documents"]:
            block = SimpleNamespace(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "lattice-r4:" + doc["id"]),
                text=doc["text"],
                locator={"line": 1},
            )
            blocks.append(block)
            for position, value in enumerate(chunk_blocks([block], model.tokenizer)):
                chunks.append(
                    SimpleNamespace(
                        id=uuid.uuid5(block.id, str(position)), document_id=doc["id"], **value
                    )
                )
        vectors = model.embed([chunk.text for chunk in chunks])
        questions = model.embed(
            [normalize_query(case["query"]) for case in suite["cases"]], query=True
        )
        modes = ["SEMANTIC"] if options["embedding_only"] else ["KEYWORD", "SEMANTIC", "HYBRID"]
        results = {mode: [] for mode in modes}

        def evaluate(indexes=None):
            for case, query_vector in zip(suite["cases"], questions, strict=True):
                for mode in modes:
                    if indexes is None:
                        ranked = sorted(
                            [
                                SimpleNamespace(
                                    **vars(chunk),
                                    score=1
                                    - sum(a * b for a, b in zip(vector, query_vector, strict=True))
                                    / math.sqrt(
                                        sum(a * a for a in vector)
                                        * sum(b * b for b in query_vector)
                                    ),
                                )
                                for chunk, vector in zip(chunks, vectors, strict=True)
                            ],
                            key=lambda chunk: (chunk.score, str(chunk.id)),
                        )[:20]
                        selected = rank_hits([], ranked)
                    else:
                        selected = rank_hits(
                            *candidates(indexes, normalize_query(case["query"]), query_vector, mode)
                        )
                    labels = {chunk.id: chunk.document_id for chunk in chunks}
                    results[mode].append(
                        {
                            **case,
                            "goldChunkIds": [
                                str(chunk.id)
                                for chunk in chunks
                                if chunk.document_id in case["gold"]
                            ],
                            "retrieved": [labels[row["chunk"].id] for row in selected],
                        }
                    )

        if options["embedding_only"]:
            evaluate()
        else:
            # No inference inside this temporary transaction; all vectors were prepared above.
            with transaction.atomic():
                user = get_user_model().objects.create_user("eval-" + uuid.uuid4().hex)
                workspace = Workspace.objects.create(name="Temporary R4 evaluation")
                collection = Collection.objects.create(workspace=workspace, title="Development")
                indexes = []
                for doc, block in zip(suite["documents"], blocks, strict=True):
                    document = Document.objects.create(
                        collection=collection, title=doc["title"], created_by=user
                    )
                    source = SourceVersion.objects.create(
                        document=document,
                        filename="synthetic.txt",
                        kind="TXT",
                        byte_size=len(block.text.encode()),
                        sha256=hashlib.sha256(block.text.encode()).hexdigest(),
                    )
                    extraction = ExtractionVersion.objects.create(
                        source=source, parser_version="development-canonical-v1"
                    )
                    SourceBlock.objects.create(
                        id=block.id,
                        extraction=extraction,
                        position=0,
                        text=block.text,
                        original_text=block.text,
                        locator=block.locator,
                        span_map=[[0, len(block.text), 0, len(block.text)]],
                    )
                    selected = [
                        (chunk, vector)
                        for chunk, vector in zip(chunks, vectors, strict=True)
                        if chunk.document_id == doc["id"]
                    ]
                    index = IndexVersion.objects.create(
                        extraction=extraction,
                        requested_by=user,
                        profile=PROFILE,
                        chunker=VERSION,
                        active=True,
                        state="READY",
                        chunk_count=len(selected),
                    )
                    indexes.append({"id": index.pk})
                    for position, (chunk, vector) in enumerate(selected):
                        record = Chunk.objects.create(
                            id=chunk.id,
                            index=index,
                            position=position,
                            text=chunk.text,
                            sha256=chunk.sha256,
                            spans=chunk.spans,
                            token_count=chunk.token_count,
                        )
                        Embedding384.objects.create(chunk=record, vector=vector)
                evaluate(indexes)
                transaction.set_rollback(True)
        report = {
            "suite": suite["version"],
            "suiteHash": digest(suite),
            "profile": PROFILE,
            "backend": "offline cosine only"
            if options["embedding_only"]
            else "PostgreSQL/pgvector",
            "elapsedSeconds": round(time.monotonic() - started, 2),
            "metrics": {mode: metrics(rows) for mode, rows in results.items()},
            "cases": results,
        }
        # ASCII-escaped JSON also works with Windows terminals using a legacy code page.
        self.stdout.write(json.dumps(report, indent=2))
