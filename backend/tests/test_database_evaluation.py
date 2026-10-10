from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from modules.retrieval.database_evaluation import canonical_hit


def test_database_evaluation_requires_demo_mode_before_model_or_database(settings):
    settings.DEMO_MODE = False
    with pytest.raises(CommandError, match="DEMO_MODE"):
        call_command("run_evaluations", suite="r8-v1", profile="local-e5", database=True)


def test_backend_choices_cannot_silently_override_each_other():
    with pytest.raises(CommandError, match="exactly one"):
        call_command(
            "run_evaluations", suite="r8-v1", profile="local-e5", database=True, embedding_only=True
        )


def test_canonical_hit_maps_database_ids_and_refuses_unauthorized_or_invalid_spans():
    chunk = SimpleNamespace(
        pk="chunk",
        document_id="doc-db",
        index=SimpleNamespace(extraction=SimpleNamespace(source_id="source-db")),
        text="policy",
        spans=[{"block_id": "block-db", "start": 0, "end": 6, "chunk_start": 0, "chunk_end": 6}],
    )
    labels = {
        "documents": {"doc-db": "doc"},
        "sources": {"source-db": "source"},
        "blocks": {"block-db": {"id": "block", "text": "policy", "source": "source"}},
    }
    hit = canonical_hit(chunk, labels, {"doc"})
    assert hit["document"] == "doc" and hit["spans"][0]["block_id"] == "block"
    with pytest.raises(ValueError, match="scope"):
        canonical_hit(chunk, labels, set())
    chunk.text = "invent"
    with pytest.raises(ValueError, match="provenance"):
        canonical_hit(chunk, labels, {"doc"})


@pytest.mark.django_db
@pytest.mark.parametrize("failure", [False, True])
def test_database_runner_uses_real_scopes_and_rolls_back_all_fixture_data(monkeypatch, failure):
    from django.conf import settings

    from modules.identity.models import User
    from modules.retrieval.database_evaluation import evaluate_database
    from modules.retrieval.frozen import load_suite
    from modules.workspaces.models import Workspace

    suite = load_suite(settings.REPO_ROOT, "r8-v1")
    chunks, vectors = [], []
    for doc in suite["documents"]:
        source = doc["sources"][-1]
        for block in source["blocks"]:
            chunks.append(
                SimpleNamespace(
                    id=block["id"],
                    document_id=doc["id"],
                    source_id=source["id"],
                    text=block["text"],
                    sha256="0" * 64,
                    token_count=20,
                    spans=[
                        {
                            "block_id": block["id"],
                            "start": 0,
                            "end": len(block["text"]),
                            "chunk_start": 0,
                            "chunk_end": len(block["text"]),
                        }
                    ],
                )
            )
            vectors.append([1.0] + [0.0] * 383)
    before = Workspace.objects.count()
    users_before = User.objects.count()
    cases = [
        suite["cases"][0],
        next(case for case in suite["cases"] if case["persona"] == "a-curator"),
        next(case for case in suite["cases"] if case["persona"] == "b-owner"),
    ]
    cases.append(
        next(case for case in suite["cases"] if case["category"] == "access" and not case["gold"])
    )
    cases.append({**cases[-1], "collections": ["finance"]})
    if failure:

        def broken(*_):
            raise ValueError("Injected ranking failure")

        monkeypatch.setattr("modules.retrieval.database_evaluation.candidates", broken)
        with pytest.raises(ValueError, match="Injected"):
            evaluate_database(suite, cases, chunks, vectors, [vectors[0]] * len(cases))
    else:
        report = evaluate_database(suite, cases, chunks, vectors, [vectors[0]] * len(cases))
        assert set(report) == {"KEYWORD", "SEMANTIC", "HYBRID"}
        assert all(len(mode["cases"]) == len(cases) for mode in report.values())
        assert all(mode["unauthorizedHits"] == 0 for mode in report.values())
        assert report["SEMANTIC"]["cases"][-2]["retrieved"]
        assert all(mode["cases"][-1]["retrieved"] == [] for mode in report.values())
    assert Workspace.objects.count() == before
    assert User.objects.count() == users_before
