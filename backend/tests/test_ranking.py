from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from pipeline.ranking import normalize_query, rank_hits


def hit(identifier, document="doc", text=None):
    return SimpleNamespace(id=identifier, document_id=document, text=text or identifier)


def test_rrf_ties_overlap_and_document_diversity():
    a, b, c = hit("a"), hit("b", "other"), hit("c")
    ranked = rank_hits([a, b], [c, b])
    assert [row["chunk"].id for row in ranked] == ["b", "a", "c"]
    assert ranked[0]["rrf"] == pytest.approx(2 / 62)
    assert ranked[0]["lexicalRank"] == ranked[0]["vectorRank"] == 2
    same = "A long source passage about the holiday policy and working days."
    chunks = [hit(str(i), "first", same if i < 2 else f"Unique passage {i}") for i in range(5)]
    chunks += [hit("z", "second", "Completely different source")]
    chosen = rank_hits(chunks, [])
    assert [r["chunk"].id for r in chosen] == ["0", "2", "3", "z"]
    assert len(rank_hits([hit(str(i)) for i in range(10)], [])) == 8
    overlapping_a, overlapping_b = hit("left", text=same), hit("right", text=same + " ")
    overlapping_a.spans = overlapping_b.spans = [
        {"block_id": "block", "start": 0, "end": len(same)}
    ]
    assert len(rank_hits([overlapping_a, overlapping_b], [])) == 1


def test_query_normalization_preserves_identifiers_and_nepali():
    assert normalize_query("  e\u0301 API-42 नेपाली  ") == "é API-42 नेपाली"
    for bad in [" ", "x" * 4001, "bad\x00input"]:
        with pytest.raises(ValueError):
            normalize_query(bad)


def test_postgres_query_compilation_keeps_scope_and_parameters_before_top_k():
    from modules.retrieval.service import candidates

    index_id = uuid4()
    compiled = []

    def capture(queryset):
        compiled.append(queryset.query.sql_with_params())
        return []

    with patch("modules.retrieval.service.list", side_effect=capture, create=True):
        candidates([{"id": index_id}], "नेपाली ' OR 1=1", [1.0] + [0.0] * 383, "HYBRID")
    assert len(compiled) == 2
    for sql, params in compiled:
        assert index_id in params and "LIMIT 20" in sql
        assert "WHERE" in sql and '"documents_chunk"."index_id" IN' in sql
        assert "नेपाली ' OR 1=1" not in sql
    assert "websearch_to_tsquery" in compiled[0][0]
    assert "नेपाली ' OR 1=1" in compiled[0][1]
    assert "<=>" in compiled[1][0]


def test_query_model_errors_release_capacity_and_reject_bad_vectors():
    from rest_framework.exceptions import ValidationError

    from modules.retrieval import service

    with patch.object(service, "query_model") as model:
        model.return_value.embed.return_value = [[1.0, 0.0]]
        with pytest.raises(ValidationError):
            service.embed_query("question")
        assert not service.model_lock.locked()
        model.return_value.embed.return_value = [[1.0] + [0.0] * 383]
        assert len(service.embed_query("question")) == 384
        model.return_value.embed.assert_called_with(["question"], query=True)


def test_evaluation_counts_evidence_groups_and_missing_results():
    from modules.retrieval.management.commands.evaluate_retrieval import metrics

    result = metrics(
        [
            {"language": "en", "gold": ["a", "b"], "retrieved": ["x", "a"]},
            {"language": "en", "gold": ["c"], "retrieved": []},
            {"language": "ne", "gold": ["d"], "retrieved": ["d"]},
        ]
    )
    assert result["en"]["goldGroupsFound"] == 1
    assert result["en"]["evidenceRecallAt8"] == pytest.approx(1 / 3)
    assert result["en"]["meanReciprocalRank"] == 0.25
    assert result["en"]["fullEvidenceQuestions"] == 0
    assert result["ne"]["fullEvidenceQuestions"] == 1
