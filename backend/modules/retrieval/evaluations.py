"""Owner diagnostics for checked-in synthetic development and frozen reports."""

import json

from django.conf import settings
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.workspaces.access import membership_for, require_owner

from .frozen import recorded_report
from .management.commands.evaluate_retrieval import metrics
from .service import digest

REPORT_ID = "r4-embedding-development"
FROZEN_REPORT_ID = "r8-offline-semantic"


class EvaluationUnavailable(APIException):
    status_code = 503
    default_detail = (
        "The recorded evaluation is unavailable. Ask the operator to check its artifact."
    )


def evaluation(report_id):
    if report_id == FROZEN_REPORT_ID:
        try:
            suite, report = recorded_report(settings.REPO_ROOT)
            documents = {doc["id"]: doc for doc in suite["documents"]}
            versions = {
                source["id"]: source["number"]
                for doc in suite["documents"]
                for source in doc["sources"]
            }
            return {
                "id": report_id,
                "suite": report["suite"],
                "suiteHash": report["suiteHash"],
                "profile": report["profile"],
                "backend": report["backend"],
                "elapsedSeconds": report["elapsedSeconds"],
                "description": suite["description"]
                + " Includes 40 development and 40 held-out questions. Fourteen questions have no "
                "permitted gold; abstention was not measured.",
                "metricDefinition": (
                    "Evidence Recall@8 counts required exact gold spans fully covered by a "
                    "retrieved chunk of the same document and source version. Any/full evidence "
                    "and MRR use "
                    "answerable questions only; questions without gold have unmeasured abstention. "
                    "Scope is simulated from canonical fixture personas, not the production "
                    "permission resolver."
                ),
                "rows": [
                    {
                        "mode": f"SEMANTIC / {split}",
                        "language": language,
                        "questions": values["answerableQuestions"],
                        **{
                            key: values[key]
                            for key in (
                                "goldGroupsFound",
                                "goldGroups",
                                "evidenceRecallAt8",
                                "anyHitQuestions",
                                "fullEvidenceQuestions",
                                "meanReciprocalRank",
                            )
                        },
                    }
                    for split, group in report["metrics"].items()
                    for language, values in group.items()
                ],
                "cases": [
                    {
                        "id": row["id"],
                        "mode": f"SEMANTIC / {row['split']} / {row['persona']}",
                        "language": row["language"],
                        "query": row["query"],
                        "fullEvidence": row["fullEvidence"],
                        "expected": [
                            {
                                "id": gold["id"],
                                "title": (
                                    f"{documents[gold['document']]['title']} (v{gold['version']})"
                                ),
                                "text": gold["quote"],
                            }
                            for gold in row["gold"]
                        ],
                        "retrieved": [
                            {
                                "id": hit["chunk"],
                                "title": (
                                    f"{documents[hit['document']]['title']} "
                                    f"(v{versions[hit['source']]})"
                                ),
                                "text": hit["text"],
                            }
                            for hit in row["retrieved"]
                        ],
                    }
                    for row in report["cases"]
                ],
            }
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise EvaluationUnavailable() from error
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
            "metricDefinition": (
                "Evidence Recall@8 counts required gold document groups found in the first eight "
                "results, divided by all required groups. Any evidence counts questions with at "
                "least one gold group; full evidence requires every gold group. MRR averages the "
                "reciprocal rank of the first gold hit. These development labels identify "
                "documents, not exact answer spans."
            ),
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
    fullEvidence = serializers.BooleanField(allow_null=True)
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
    metricDefinition = serializers.CharField()
    rows = EvaluationRowData(many=True)
    cases = EvaluationCaseData(many=True)


class EvaluationView(APIView):
    @extend_schema(responses=EvaluationData(many=True))
    def get(self, request, workspace_id):
        require_owner(membership_for(request.user, workspace_id))
        return Response(
            EvaluationData([evaluation(REPORT_ID), evaluation(FROZEN_REPORT_ID)], many=True).data
        )


class EvaluationDetailView(APIView):
    @extend_schema(responses=EvaluationData)
    def get(self, request, workspace_id, report_id):
        require_owner(membership_for(request.user, workspace_id))
        return Response(EvaluationData(evaluation(report_id)).data)
