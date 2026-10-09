"""Export actual demo turns for human annotation, or score an existing capture offline."""

import json
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.http import Http404
from django.utils import timezone

from modules.conversations.models import Turn
from modules.conversations.serializers import SourceQuoteData, TurnData
from modules.conversations.service import citation_data, read_turn
from modules.retrieval.answer_review import review_template, score_review
from modules.retrieval.frozen import load_suite, permitted_documents
from modules.retrieval.service import digest
from modules.workspaces import demo
from modules.workspaces.models import DemoInstallation
from pipeline.ranking import normalize_query


def read_json(filename):
    path = Path(filename)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Review input exceeds 8 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


class Command(BaseCommand):
    help = "Export demo answers or score human annotations. No generation or database writes."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--split", choices=["development", "held-out", "all"], default="development"
        )
        parser.add_argument(
            "--turn-map", help="JSON object mapping frozen case IDs to actual demo turn UUIDs"
        )
        parser.add_argument("--capture", help="Previously exported capture JSON")
        parser.add_argument("--review", help="Human annotation JSON; omit to emit a blank template")

    def handle(self, *args, **options):
        try:
            if (
                bool(options["turn_map"]) == bool(options["capture"])
                or options["review"]
                and not options["capture"]
            ):
                raise ValueError("Choose --turn-map to export or --capture with optional --review")
            suite = load_suite(settings.REPO_ROOT, "r8-v1")
            if options["capture"]:
                capture = read_json(options["capture"])
                if capture["split"] not in {"development", "held-out", "all"}:
                    raise ValueError("Unknown captured split")
                expected = [
                    case
                    for case in suite["cases"]
                    if capture["split"] == "all" or case["split"] == capture["split"]
                ]
                if (
                    capture["suiteHash"] != digest(suite)
                    or capture["suite"] != suite["version"]
                    or len(capture["cases"]) != len(expected)
                    or any(
                        any(row.get(key) != value for key, value in case.items())
                        for case, row in zip(expected, capture["cases"], strict=True)
                    )
                ):
                    raise ValueError("Capture must match the entire frozen split and labels")
                result = (
                    score_review(capture, read_json(options["review"]))
                    if options["review"]
                    else review_template(capture)
                )
                if not options["review"]:
                    score_review(capture, result)
            else:
                result = self.capture(suite, options["split"], read_json(options["turn_map"]))
            self.stdout.write(json.dumps(result, indent=2, ensure_ascii=True))
        except (OSError, ValueError, KeyError, TypeError, Turn.DoesNotExist) as error:
            raise CommandError(
                "Invalid review input, frozen labels or demo turn mapping. No data changed."
            ) from error

    def capture(self, suite, split, mapping):
        root = demo.environment()
        installation = DemoInstallation.objects.get(pk=1)
        demo.check_marker(root, installation)
        if installation.state != "READY" or installation.suite_hash != digest(suite):
            raise CommandError("A matching READY demo installation is required")
        cases = [case for case in suite["cases"] if split == "all" or case["split"] == split]
        if not isinstance(mapping, dict) or set(mapping) - {case["id"] for case in cases}:
            raise ValueError("Unknown case IDs in turn mapping")
        turn_ids = [uuid.UUID(value) for value in mapping.values()]
        if len(set(turn_ids)) != len(turn_ids):
            raise ValueError("A turn cannot represent more than one case")
        rows = []
        for case in cases:
            row = {
                **case,
                "state": "NOT_RUN",
                "answer": None,
                "citationChecks": [],
                "sourceQuotes": [],
                "modelDigest": None,
                "turnId": None,
                "usage": [],
            }
            if case["id"] in mapping:
                turn = Turn.objects.select_related("conversation").get(pk=mapping[case["id"]])
                expected_scope = sorted(
                    str(demo.fixture_id(installation, "collection:" + key))
                    for key in {doc["collection"] for doc in permitted_documents(suite, case)}
                )
                if (
                    turn.conversation.owner_id
                    != demo.fixture_id(installation, "user:" + case["persona"])
                    or turn.conversation.workspace_id
                    != demo.fixture_id(
                        installation, "workspace:" + suite["personas"][case["persona"]]["workspace"]
                    )
                    or normalize_query(turn.question) != normalize_query(case["query"])
                    or sorted(turn.collection_ids) != expected_scope
                ):
                    raise ValueError(
                        "Turn question, owner, workspace or source scope differs from frozen case"
                    )
                data = TurnData(read_turn(turn.conversation.owner, turn.pk)).data
                row.update(
                    state=data["state"],
                    answer=data["answer"],
                    turnId=str(turn.pk),
                    modelDigest=turn.model_digest or None,
                    usage=turn.usage,
                )
                if row["answer"] is not None:
                    if not re.fullmatch(r"[0-9a-f]{64}", turn.model_digest):
                        raise ValueError("An actual model digest is required for captured answers")
                    allowed_sources = {
                        str(demo.fixture_id(installation, "source:" + doc["activeSource"]))
                        for doc in permitted_documents(suite, case)
                    }
                    for block_index, block in enumerate(row["answer"]["blocks"]):
                        for cite_index, cite in enumerate(block["citations"]):
                            if cite["sourceId"] not in allowed_sources:
                                raise ValueError(
                                    "Citation differs from the frozen current permitted source"
                                )
                            try:
                                row["sourceQuotes"].append(
                                    SourceQuoteData(
                                        citation_data(
                                            turn.conversation.owner,
                                            turn.pk,
                                            block_index,
                                            cite_index,
                                        )
                                    ).data
                                )
                                row["citationChecks"].append(True)
                            except Http404:
                                row["citationChecks"].append(False)
            rows.append(row)
        result = {
            "suite": suite["version"],
            "suiteHash": digest(suite),
            "split": split,
            "capturedAt": timezone.now().isoformat(),
            "cases": rows,
        }
        return {**result, "captureHash": digest(result)}
