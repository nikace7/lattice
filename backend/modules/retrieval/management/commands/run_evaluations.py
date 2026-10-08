"""Opt-in, read-only evaluation of frozen canonical text using prepared local E5."""

import json
import platform
import time
import uuid
from importlib.metadata import version
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from modules.retrieval.frozen import load_suite, permitted_documents, score_cases
from modules.retrieval.service import digest
from pipeline.chunking import VERSION, InvalidIndex, chunk_blocks
from pipeline.embedding import PROFILE, LocalEmbedder, model_directory
from pipeline.ranking import normalize_query, rank_hits


class Command(BaseCommand):
    help = "Validate r8-v1 or explicitly run offline E5; never seeds or changes application data."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--suite", required=True, choices=["r8-v1"])
        parser.add_argument("--profile", required=True, choices=["local-e5"])
        parser.add_argument(
            "--split", choices=["development", "held-out", "all"], default="development"
        )
        parser.add_argument("--validate-only", action="store_true")
        parser.add_argument("--embedding-only", action="store_true")

    def handle(self, *args, **options):
        if options["profile"] != "local-e5":
            raise CommandError("Only the pinned local-e5 profile is implemented.")
        if not options["validate_only"] and not options["embedding_only"]:
            raise CommandError(
                "Pass --embedding-only. PostgreSQL/hybrid/answer evaluation remains deferred."
            )
        started = time.monotonic()
        try:
            suite = load_suite(settings.REPO_ROOT, options["suite"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CommandError(
                "Frozen suite or source artifacts are invalid. Review the committed fixture."
            ) from error
        if options["validate_only"]:
            self.stdout.write(
                json.dumps(
                    {
                        "suite": suite["version"],
                        "suiteHash": digest(suite),
                        "frozen": True,
                        "documents": len(suite["documents"]),
                        "cases": len(suite["cases"]),
                    }
                )
            )
            return
        if options["split"] not in {"development", "held-out", "all"}:
            raise CommandError("Unknown split.")
        cases = [
            case
            for case in suite["cases"]
            if options["split"] == "all" or case["split"] == options["split"]
        ]
        try:
            model = LocalEmbedder(model_directory(settings.MODEL_CACHE_ROOT))
            chunks = []
            for doc in suite["documents"]:
                source = next(item for item in doc["sources"] if item["id"] == doc["activeSource"])
                blocks = [
                    SimpleNamespace(id=block["id"], text=block["text"], locator=block["locator"])
                    for block in source["blocks"]
                ]
                for position, value in enumerate(
                    chunk_blocks(blocks, model.tokenizer, kind=source["kind"])
                ):
                    chunks.append(
                        SimpleNamespace(
                            id=uuid.uuid5(
                                uuid.NAMESPACE_URL, f"lattice-r8:{source['id']}:{position}"
                            ),
                            document_id=doc["id"],
                            source_id=source["id"],
                            **value,
                        )
                    )

            def embed(texts, query=False):
                return [
                    vector
                    for start in range(0, len(texts), 32)
                    for vector in model.embed(texts[start : start + 32], query=query)
                ]

            vectors = embed([chunk.text for chunk in chunks])
            queries = embed([normalize_query(case["query"]) for case in cases], query=True)
            results = []
            for case, query in zip(cases, queries, strict=True):
                allowed = {doc["id"] for doc in permitted_documents(suite, case)}
                ranked = sorted(
                    [
                        SimpleNamespace(
                            **vars(chunk),
                            score=1 - sum(a * b for a, b in zip(vector, query, strict=True)),
                        )
                        for chunk, vector in zip(chunks, vectors, strict=True)
                        if chunk.document_id in allowed
                    ],
                    key=lambda chunk: (chunk.score, str(chunk.id)),
                )[:20]
                results.append(
                    [
                        {
                            "chunk": str(hit["chunk"].id),
                            "document": hit["chunk"].document_id,
                            "source": hit["chunk"].source_id,
                            "text": hit["chunk"].text,
                            "spans": hit["chunk"].spans,
                        }
                        for hit in rank_hits([], ranked)
                    ]
                )
        except (InvalidIndex, OSError) as error:
            raise CommandError(
                "Prepared local E5 artifacts are unavailable or invalid. No model was downloaded."
            ) from error
        report = {
            "suite": suite["version"],
            "suiteHash": digest(suite),
            "profile": PROFILE,
            "chunker": VERSION,
            "backend": "offline cosine only; canonical fixture scope simulation",
            "mode": "SEMANTIC",
            "split": options["split"],
            "chunks": len(chunks),
            "elapsedSeconds": round(time.monotonic() - started, 2),
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "torch": version("torch"),
                "transformers": version("transformers"),
                "device": "cpu",
                "torchThreads": 2,
            },
            **score_cases(cases, results),
        }
        self.stdout.write(json.dumps(report, indent=2, ensure_ascii=True))
