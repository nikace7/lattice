from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate

from modules.retrieval.evaluations import EvaluationView, evaluation


def test_recorded_report_resolves_evidence_and_does_not_invent_answer_metrics():
    report = evaluation("r4-embedding-development")
    assert report["suite"] == "r4-development-v1"
    assert report["rows"][0]["goldGroupsFound"] == 6
    assert len(report["cases"]) == 10
    case = report["cases"][0]
    assert case["fullEvidence"]
    assert "five working days" in case["expected"][0]["text"]
    assert case["retrieved"][0]["id"] == "leave"
    assert "actualAnswer" not in case


def test_report_id_is_an_allowlist_not_a_file_path():
    from django.http import Http404

    with pytest.raises(Http404):
        evaluation("../../.env")


def test_frozen_report_resolves_exact_gold_and_excludes_unknown_abstention_from_rates():
    report = evaluation("r8-offline-semantic")
    assert len(report["cases"]) == 80
    row = next(
        row
        for row in report["rows"]
        if row["mode"] == "SEMANTIC / held-out" and row["language"] == "en"
    )
    assert row["questions"] == 30 and row["goldGroups"] == 38
    assert "exact" in report["metricDefinition"]
    case = report["cases"][0]
    assert "six working days" in case["expected"][0]["text"]
    assert "v2" in case["expected"][0]["title"]
    assert report["cases"][25]["fullEvidence"] is None


def test_mismatched_corpus_is_withheld():
    import json
    from pathlib import Path

    from modules.retrieval.evaluations import EvaluationUnavailable

    original = Path.read_text

    def changed(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path.name == "r4-development.json":
            suite = json.loads(value)
            suite["documents"][0]["text"] = "changed"
            return json.dumps(suite)
        return value

    with patch.object(Path, "read_text", changed), pytest.raises(EvaluationUnavailable):
        evaluation("r4-embedding-development")


def test_evaluation_api_checks_owner_before_reading_artifact():
    request = APIRequestFactory().get("/evaluations")
    force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
    with (
        patch("modules.retrieval.evaluations.membership_for") as member,
        patch("modules.retrieval.evaluations.require_owner", side_effect=PermissionDenied),
        patch("modules.retrieval.evaluations.evaluation") as read,
    ):
        response = EvaluationView.as_view()(request, workspace_id="workspace")
    assert response.status_code == 403
    member.assert_called_once()
    read.assert_not_called()


def test_document_status_query_compiles_with_current_source_and_scope():
    import uuid

    from django.contrib.auth import get_user_model
    from django.db.models.sql.compiler import SQLAggregateCompiler

    from modules.documents.api import DocumentStatusView

    request = APIRequestFactory().get("/document-status")
    user = get_user_model()(id=uuid.uuid4(), is_active=True)
    force_authenticate(request, user=user)
    statements = []

    def compiled(compiler, *args, **kwargs):
        sql, params = compiler.as_sql()
        statements.append((sql, params))
        return (2, 1, 1)

    with (
        patch("modules.documents.api.membership_for"),
        patch.object(SQLAggregateCompiler, "execute_sql", compiled),
    ):
        response = DocumentStatusView.as_view()(request, workspace_id=uuid.uuid4())
    assert response.status_code == 200
    assert response.data == {"total": 2, "ready": 1, "processing": 1}
    sql, params = statements[0]
    assert 'ORDER BY U0."number" DESC LIMIT 1' in sql
    assert '"deleted_at" IS NULL' in sql and '"active"' in sql
    assert str(user.pk) in {str(value) for value in params}
