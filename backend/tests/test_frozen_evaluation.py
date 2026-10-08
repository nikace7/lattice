import json
from copy import deepcopy

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from modules.retrieval.frozen import load_suite, score_cases, validate_suite


def test_frozen_suite_has_separate_templates_exact_gold_and_verified_files():
    suite = load_suite(settings.REPO_ROOT, "r8-v1")
    assert len(suite["documents"]) == 24
    assert len(suite["cases"]) == 80
    assert len(suite["documents"][0]["sources"]) == 2


def test_frozen_native_assets_reproduce_canonical_text_and_scan_has_no_native_text(tmp_path):
    import pdfplumber

    from pipeline.source_parser import extract

    suite = load_suite(settings.REPO_ROOT, "r8-v1")
    checked = 0
    for doc in suite["documents"]:
        for source in doc["sources"]:
            path = settings.REPO_ROOT / "fixtures/corpus/r8-v1" / source["file"]
            if source["canonicalOrigin"].startswith("manual OCR"):
                with pdfplumber.open(path) as pdf:
                    assert not pdf.pages[0].chars and pdf.pages[0].images
                continue
            directory = tmp_path / source["id"]
            directory.mkdir()
            result = extract(path, source["kind"], directory)
            assert not result["warnings"]
            assert [block["text"] for block in result["blocks"]] == [
                block["text"] for block in source["blocks"]
            ]
            assert [block["locator"] for block in result["blocks"]] == [
                block["locator"] for block in source["blocks"]
            ]
            checked += 1
    assert checked == 24


@pytest.mark.parametrize("change", ["quote", "scope", "template", "counts", "checksum"])
def test_freeze_rejects_bad_gold_scope_split_or_artifact(change):
    suite = deepcopy(load_suite(settings.REPO_ROOT, "r8-v1"))
    if change == "quote":
        suite["cases"][0]["gold"][0]["quote"] = "Invented quotation"
    elif change == "scope":
        suite["cases"][0]["persona"] = "b-owner"
    elif change == "template":
        suite["cases"][40]["template"] = suite["cases"][0]["template"]
    elif change == "counts":
        suite["cases"].pop()
    else:
        suite["documents"][0]["sources"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        validate_suite(suite, settings.REPO_ROOT)


def test_metrics_require_exact_span_coverage_and_exclude_unanswerable():
    gold = {
        "id": "g",
        "document": "doc",
        "source": "doc-v2",
        "block": "block",
        "start": 4,
        "end": 9,
    }
    cases = [
        {"id": "hit", "split": "held-out", "category": "direct", "language": "en", "gold": [gold]},
        {"id": "miss", "split": "held-out", "category": "direct", "language": "en", "gold": [gold]},
        {
            "id": "empty",
            "split": "held-out",
            "category": "unanswerable",
            "language": "en",
            "gold": [],
        },
    ]
    hit = {
        "document": "doc",
        "source": "doc-v2",
        "spans": [{"block_id": "block", "start": 0, "end": 9}],
    }
    wrong_version = {**hit, "source": "doc-v1"}
    partial = {**hit, "spans": [{"block_id": "block", "start": 5, "end": 9}]}
    result = score_cases(cases, [[hit], [wrong_version, partial], [hit]])
    row = result["metrics"]["held-out"]["en"]
    assert row["goldGroupsFound"] == 1 and row["goldGroups"] == 2
    assert row["answerableQuestions"] == 2 and row["questions"] == 3
    assert row["fullEvidenceQuestions"] == 1
    assert row["evidenceRecallAt8"] == 0.5
    assert result["cases"][2]["fullEvidence"] is None
    assert result["unmeasured"]["abstention"] is None


def test_validate_command_does_not_load_models_or_database(capsys):
    call_command("run_evaluations", suite="r8-v1", profile="local-e5", validate_only=True)
    report = json.loads(capsys.readouterr().out)
    assert report["documents"] == 24 and report["cases"] == 80
    assert report["frozen"] is True


def test_command_requires_explicit_offline_backend_and_allowlisted_suite():
    with pytest.raises(CommandError, match="embedding-only"):
        call_command("run_evaluations", suite="r8-v1", profile="local-e5")
    with pytest.raises(CommandError):
        call_command("run_evaluations", suite="../../.env", profile="local-e5", validate_only=True)
