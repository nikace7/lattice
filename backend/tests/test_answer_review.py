from copy import deepcopy

import pytest

from modules.retrieval.answer_review import review_template, score_review
from modules.retrieval.service import digest


def capture():
    rows = [
        {
            "id": "direct",
            "category": "direct",
            "gold": ["g"],
            "state": "COMPLETED",
            "answer": {
                "status": "ANSWERED",
                "blocks": [{"text": "Request leave five days ahead."}],
            },
            "citationChecks": [True],
        },
        {
            "id": "unsupported",
            "category": "unanswerable",
            "gold": [],
            "state": "COMPLETED",
            "answer": {"status": "INSUFFICIENT_EVIDENCE", "blocks": []},
            "citationChecks": [],
        },
        {
            "id": "missing",
            "category": "direct",
            "gold": ["g"],
            "state": "NOT_RUN",
            "answer": None,
            "citationChecks": [],
        },
    ]
    data = {"suite": "r8-v1", "suiteHash": "hash", "split": "held-out", "cases": rows}
    return {**data, "captureHash": digest(data)}


def test_unreviewed_and_missing_answers_never_count_as_success():
    report = score_review(capture(), review_template(capture()))
    assert report["humanSupportedClaims"] is None
    assert report["unsupportedAbstention"] is None
    assert report["reviewedCases"] == 0
    assert report["reviewComplete"] is False


def test_human_annotations_score_only_reviewed_claims_and_expose_incomplete_coverage():
    review = review_template(capture())
    review["reviewer"] = "Reviewer A"
    review["cases"][0].update(
        claims=[
            {
                "block": 0,
                "start": 0,
                "end": len("Request leave five days ahead."),
                "text": "Request leave five days ahead.",
                "supported": True,
                "note": "Exact policy quotation",
            }
        ],
        factsComplete=True,
    )
    review["cases"][1]["abstentionCorrect"] = True
    report = score_review(capture(), review)
    assert report["humanSupportedClaims"] == 1
    assert report["unsupportedAbstention"] == 1
    assert report["reviewedCases"] == 2
    assert report["missingAnswers"] == 1
    assert report["reviewComplete"] is False


def test_duplicate_claims_are_rejected_instead_of_inflating_support():
    original = capture()
    review = review_template(original)
    review["cases"][0]["claims"] *= 2
    with pytest.raises(ValueError, match="Duplicate claims"):
        score_review(original, review)


def test_partial_claim_annotation_cannot_hide_unreviewed_answer_text():
    original = capture()
    review = review_template(original)
    review["reviewer"] = "Reviewer A"
    review["cases"][0]["claims"] = [
        {
            "block": 0,
            "start": 0,
            "end": 7,
            "text": "Request",
            "supported": True,
            "note": "Only part of the answer",
        }
    ]
    review["cases"][0]["factsComplete"] = True
    report = score_review(original, review)
    assert report["humanSupportedClaims"] is None and report["reviewedCases"] == 0


def test_offline_command_generates_blank_review_and_preserves_missing_answers(tmp_path, capsys):
    import json

    from django.conf import settings
    from django.core.management import call_command

    from modules.retrieval.frozen import load_suite

    suite = load_suite(settings.REPO_ROOT, "r8-v1")
    data = {
        "suite": "r8-v1",
        "suiteHash": digest(suite),
        "split": "development",
        "cases": [
            {**case, "state": "NOT_RUN", "answer": None, "citationChecks": []}
            for case in suite["cases"]
            if case["split"] == "development"
        ],
    }
    path = tmp_path / "capture.json"
    path.write_text(json.dumps({**data, "captureHash": digest(data)}))
    call_command("review_answers", capture=str(path))
    template = json.loads(capsys.readouterr().out)
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(template))
    call_command("review_answers", capture=str(path), review=str(review_path))
    report = json.loads(capsys.readouterr().out)
    assert report["missingAnswers"] == 40 and report["reviewedCases"] == 0
    assert report["citationValidity"] is None and not report["reviewComplete"]


def test_capture_requires_demo_mode_before_database(tmp_path, settings):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.DEMO_MODE = False
    path = tmp_path / "turns.json"
    path.write_text("{}")
    with pytest.raises(CommandError, match="DEMO_MODE"):
        call_command("review_answers", turn_map=str(path))


@pytest.mark.django_db
@pytest.mark.parametrize("category", ["unanswerable", "access"])
def test_capture_binds_actual_demo_turn_owner_question_and_scope(
    tmp_path, settings, monkeypatch, capsys, category
):
    import json

    from django.core.management import call_command
    from django.core.management.base import CommandError
    from django.utils import timezone

    from modules.conversations.models import Conversation, Turn
    from modules.retrieval.frozen import load_suite, permitted_documents
    from modules.workspaces import demo
    from modules.workspaces.models import DemoInstallation

    repo = settings.REPO_ROOT
    suite = load_suite(repo, "r8-v1")
    settings.REPO_ROOT = tmp_path
    settings.DEMO_MODE = True
    settings.STORAGE_ROOT = tmp_path / ".data/demo-storage"
    settings.PARSER_SPOOL_ROOT = tmp_path / ".data/demo-parser"
    monkeypatch.setattr(demo, "database_name", lambda: "lattice_demo")
    monkeypatch.setattr(demo, "corpus_root", lambda: repo)
    demo.seed(settings.STORAGE_ROOT, "Fictional-Fixture-Only-Password")
    installation = DemoInstallation.objects.get(pk=1)
    case = next(
        case
        for case in suite["cases"]
        if case["category"] == category and case["split"] == "development" and not case["gold"]
    )
    conversation = Conversation.objects.create(
        workspace_id=demo.fixture_id(
            installation, "workspace:" + suite["personas"][case["persona"]]["workspace"]
        ),
        owner_id=demo.fixture_id(installation, "user:" + case["persona"]),
        title="Test evaluation",
    )
    import uuid

    turn = Turn.objects.create(
        conversation=conversation,
        idempotency_key=uuid.uuid4(),
        question=case["query"],
        collection_ids=[
            str(demo.fixture_id(installation, "collection:" + key))
            for key in {doc["collection"] for doc in permitted_documents(suite, case)}
        ],
        snapshot="fixture",
        payload_hash="fixture",
        lease_until=timezone.now(),
        charged_tokens=0,
        state="COMPLETED",
        model_digest="f" * 64,
        answer={
            "status": "INSUFFICIENT_EVIDENCE",
            "blocks": [],
            "repaired": False,
            "omittedPassages": 0,
        },
    )
    path = tmp_path / "turns.json"
    path.write_text(json.dumps({case["id"]: str(turn.pk)}))
    # Fixture validation uses the real suite; command roots remain isolated.
    from modules.retrieval.management.commands import review_answers

    monkeypatch.setattr(review_answers, "load_suite", lambda *_: suite)
    call_command("review_answers", turn_map=str(path))
    report = json.loads(capsys.readouterr().out)
    row = next(row for row in report["cases"] if row["id"] == case["id"])
    assert row["turnId"] == str(turn.pk) and row["state"] == "COMPLETED"
    turn.question = "A different question"
    turn.save(update_fields=["question"])
    with pytest.raises(CommandError, match="Invalid review"):
        call_command("review_answers", turn_map=str(path))


@pytest.mark.parametrize("change", ["hash", "duplicate", "invented", "boolean", "capture"])
def test_review_refuses_changed_capture_duplicate_case_invented_claim_and_non_boolean(change):
    original = capture()
    review = review_template(original)
    if change == "hash":
        review["captureHash"] = "other"
    elif change == "duplicate":
        review["cases"].append(deepcopy(review["cases"][0]))
    elif change == "invented":
        review["cases"][0]["claims"][0]["text"] = "Outside answer"
    elif change == "boolean":
        review["cases"][0]["factsComplete"] = "yes"
    else:
        original["cases"][0]["answer"]["blocks"][0]["text"] = "Altered answer"
    with pytest.raises(ValueError):
        score_review(original, review)
