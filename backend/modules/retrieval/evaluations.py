"""Owner diagnostics for the checked-in synthetic development report."""

import json

from django.conf import settings
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.workspaces.access import membership_for, require_owner

from .management.commands.evaluate_retrieval import metrics
from .service import digest

REPORT_ID = "r4-embedding-development"


class EvaluationUnavailable(APIException):
    status_code = 503
    default_detail = (
        "The recorded evaluation is unavailable. Ask the operator to check its artifact."
    )


def evaluation(report_id):
    if report_id != REPORT_ID:
        raise Http404
    try:
        suite = json.loads(
            (settings.REPO_ROOT / "fixtures/evals/r4-development.json").read_text(encoding="utf-8")
        )
        report = json.loads(
            (settings.REPO_ROOT / "docs/evaluations/r4-embedding-development.json").read_text(
                encoding="utf-8"
            )
        )
        if report["suiteHash"] != digest(suite) or report["suite"] != suite["version"]:
            raise ValueError("Suite mismatch")
        documents = {doc["id"]: doc for doc in suite["documents"]}
        gold = {case["id"]: case for case in suite["cases"]}
        rows, cases = [], []
        for mode, results in report["cases"].items():
            if len(results) != len(gold) or {case["id"] for case in results} != set(gold):
                raise ValueError("Incomplete cases")
            for case in results:
                if any(case[key] != gold[case["id"]][key] for key in ("query", "gold", "language")):
                    raise ValueError("Case mismatch")
                retrieved = case["retrieved"][:8]
                cases.append(
                    {
                        "id": f"{mode}:{case['id']}",
                        "mode": mode,
                        "language": case["language"],
                        "query": case["query"],
                        "fullEvidence": set(case["gold"]).issubset(retrieved),
                        "expected": [documents[key] for key in case["gold"]],
                        "retrieved": [documents[key] for key in retrieved],
                    }
                )
            rows.extend(
                {"mode": mode, "language": language, **values}
                for language, values in metrics(results).items()
            )
        return {
            "id": report_id,
            "suite": report["suite"],
            "suiteHash": report["suiteHash"],
            "profile": report["profile"],
            "backend": report["backend"],
            "elapsedSeconds": report["elapsedSeconds"],
            "description": suite["description"],
            "rows": rows,
            "cases": cases,
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise EvaluationUnavailable() from error


class EvaluationDocumentData(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    text = serializers.CharField()


class EvaluationCaseData(serializers.Serializer):
    id = serializers.CharField()
    mode = serializers.CharField()
    language = serializers.CharField()
    query = serializers.CharField()
    fullEvidence = serializers.BooleanField()
    expected = EvaluationDocumentData(many=True)
    retrieved = EvaluationDocumentData(many=True)


class EvaluationRowData(serializers.Serializer):
    mode = serializers.CharField()
    language = serializers.CharField()
    questions = serializers.IntegerField()
    goldGroupsFound = serializers.IntegerField()
    goldGroups = serializers.IntegerField()
    evidenceRecallAt8 = serializers.FloatField()
    anyHitQuestions = serializers.IntegerField()
    fullEvidenceQuestions = serializers.IntegerField()
    meanReciprocalRank = serializers.FloatField()


class EvaluationData(serializers.Serializer):
    id = serializers.CharField()
    suite = serializers.CharField()
    suiteHash = serializers.CharField()
    profile = serializers.JSONField()
    backend = serializers.CharField()
    elapsedSeconds = serializers.FloatField()
    description = serializers.CharField()
    rows = EvaluationRowData(many=True)
    cases = EvaluationCaseData(many=True)


class EvaluationView(APIView):
    @extend_schema(responses=EvaluationData(many=True))
    def get(self, request, workspace_id):
        require_owner(membership_for(request.user, workspace_id))
        return Response(EvaluationData([evaluation(REPORT_ID)], many=True).data)


class EvaluationDetailView(APIView):
    @extend_schema(responses=EvaluationData)
    def get(self, request, workspace_id, report_id):
        require_owner(membership_for(request.user, workspace_id))
        return Response(EvaluationData(evaluation(report_id)).data)
