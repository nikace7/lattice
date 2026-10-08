"""Frozen synthetic labels and offline span scoring, not application authorization."""

import hashlib
import json
from collections import Counter

from pipeline.ranking import normalize_query

from .service import digest

CATEGORIES = {
    "direct": 20,
    "cross-document": 5,
    "unanswerable": 5,
    "conflict": 3,
    "nepali": 3,
    "access": 4,
}
ROLES = {"MEMBER": 0, "CURATOR": 1, "OWNER": 2}


def permitted_documents(suite, case):
    # ponytail: fixture roles simulate scope; verify real grants in PostgreSQL before acceptance.
    persona = suite["personas"][case["persona"]]
    collections = {item["id"]: item for item in suite["collections"]}
    return [
        doc
        for doc in suite["documents"]
        if doc["workspace"] == persona["workspace"]
        and doc["collection"] in case["collections"]
        and ROLES[persona["role"]] >= ROLES[collections[doc["collection"]]["minimumRole"]]
    ]


def validate_suite(suite, root):
    if suite["version"] != "r8-v1" or len(suite["documents"]) != 24:
        raise ValueError("Wrong corpus version or document count")
    documents = {doc["id"]: doc for doc in suite["documents"]}
    collections = {item["id"]: item for item in suite["collections"]}
    if len(documents) != 24 or Counter(doc["workspace"] for doc in documents.values()) != {
        "a": 21,
        "b": 3,
    }:
        raise ValueError("Duplicate documents or incorrect workspace coverage")
    if Counter(item["workspace"] for item in collections.values()) != {"a": 3, "b": 1}:
        raise ValueError("Incorrect collection coverage")
    sources, blocks, kinds = {}, {}, set()
    for doc in documents.values():
        if collections[doc["collection"]]["workspace"] != doc["workspace"]:
            raise ValueError("Collection belongs to another workspace")
        for source in doc["sources"]:
            if source["id"] in sources or source["kind"] not in {"TXT", "MD", "PDF", "DOCX"}:
                raise ValueError("Duplicate source or unknown format")
            sources[source["id"]] = (doc, source)
            kinds.add(source["kind"])
            filename = source["file"]
            if (
                not isinstance(filename, str)
                or any(c in filename for c in "/\\:")
                or filename in {".", ".."}
            ):
                raise ValueError("Source filename must stay inside the frozen corpus")
            path = root / "fixtures/corpus/r8-v1" / filename
            if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("Source checksum mismatch")
            for block in source["blocks"]:
                if block["id"] in blocks or not block["text"].strip():
                    raise ValueError("Duplicate or empty block")
                blocks[block["id"]] = (doc, source, block)
        numbers = [source["number"] for source in doc["sources"]]
        if (
            numbers != list(range(1, len(numbers) + 1))
            or doc["activeSource"] != doc["sources"][-1]["id"]
        ):
            raise ValueError("Incorrect retained source order")
    if kinds != {"TXT", "MD", "PDF", "DOCX"}:
        raise ValueError("Missing source format")
    cases = suite["cases"]
    if len(cases) != 80 or len({case["id"] for case in cases}) != 80:
        raise ValueError("Incorrect or duplicate cases")
    templates = {}
    for split in ("development", "held-out"):
        group = [case for case in cases if case["split"] == split]
        if Counter(case["category"] for case in group) != CATEGORIES:
            raise ValueError("Incorrect split category counts")
        templates[split] = {case["template"] for case in group}
    if templates["development"] & templates["held-out"]:
        raise ValueError("Template crosses the development/held-out boundary")
    for case in cases:
        normalize_query(case["query"])
        if case["language"] not in {"en", "ne"} or not set(case["collections"]).issubset(
            collections
        ):
            raise ValueError("Unknown language or collection")
        allowed = {doc["id"] for doc in permitted_documents(suite, case)}
        if set(case["deniedDocuments"]) - (set(documents) - allowed):
            raise ValueError("A denied document is readable or unknown")
        if bool(case["gold"]) != bool(case["requiredAnswerFacts"]):
            raise ValueError("Answer facts must match available evidence")
        if not case["gold"] and not case["abstentionAllowed"]:
            raise ValueError("Missing evidence requires abstention")
        if len({gold["id"] for gold in case["gold"]}) != len(case["gold"]):
            raise ValueError("Duplicate evidence group")
        for gold in case["gold"]:
            doc, source, block = blocks[gold["block"]]
            start, end = gold["start"], gold["end"]
            if (
                doc["id"] != gold["document"]
                or doc["id"] not in allowed
                or source["id"] != gold["source"]
                or source["number"] != gold["version"]
                or source["id"] != doc["activeSource"]
                or not isinstance(start, int)
                or not isinstance(end, int)
                or not 0 <= start < end <= len(block["text"])
                or block["text"][start:end] != gold["quote"]
            ):
                raise ValueError("Invalid gold span, version or scope")
    return suite


def load_suite(root, suite_id):
    if suite_id != "r8-v1":
        raise ValueError("Only the frozen r8-v1 suite is supported")
    suite = json.loads((root / "fixtures/evals/r8-v1.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "fixtures/evals/r8-v1.lock.json").read_text(encoding="utf-8"))
    if lock != {"version": suite_id, "suiteHash": digest(suite)}:
        raise ValueError("Frozen suite hash mismatch; version changes require deliberate review")
    return validate_suite(suite, root)


def covers(hit, gold):
    return (
        hit["document"] == gold["document"]
        and hit["source"] == gold["source"]
        and any(
            span["block_id"] == gold["block"]
            and span["start"] <= gold["start"]
            and span["end"] >= gold["end"]
            for span in hit["spans"]
        )
    )


def recorded_report(root):
    from pipeline.chunking import VERSION
    from pipeline.embedding import PROFILE

    suite = load_suite(root, "r8-v1")
    report = json.loads(
        (root / "docs/evaluations/r8-offline-semantic.json").read_text(encoding="utf-8")
    )
    if (
        report["suiteHash"] != digest(suite)
        or report["suite"] != suite["version"]
        or report["profile"] != PROFILE
        or report["chunker"] != VERSION
        or report["mode"] != "SEMANTIC"
        or report["split"] != "all"
        or report["backend"] != "offline cosine only; canonical fixture scope simulation"
    ):
        raise ValueError("Recorded run does not match the frozen suite/profile/backend")
    blocks = {
        block["id"]: (doc, source, block)
        for doc in suite["documents"]
        for source in doc["sources"]
        for block in source["blocks"]
    }
    for case, row in zip(suite["cases"], report["cases"], strict=True):
        if any(row[key] != value for key, value in case.items()) or len(row["retrieved"]) > 8:
            raise ValueError("Recorded case differs from the frozen labels")
        allowed = {doc["id"] for doc in permitted_documents(suite, case)}
        for hit in row["retrieved"]:
            if hit["document"] not in allowed or not hit["spans"]:
                raise ValueError("Recorded hit violates fixture scope or lacks provenance")
            for span in hit["spans"]:
                doc, source, block = blocks[span["block_id"]]
                start, end = span["start"], span["end"]
                left, right = span["chunk_start"], span["chunk_end"]
                if (
                    doc["id"] != hit["document"]
                    or source["id"] != hit["source"]
                    or source["id"] != doc["activeSource"]
                    or not 0 <= start < end <= len(block["text"])
                    or not 0 <= left < right <= len(hit["text"])
                    or block["text"][start:end] != hit["text"][left:right]
                ):
                    raise ValueError("Recorded chunk has invalid text/version/span provenance")
    computed = score_cases(suite["cases"], [row["retrieved"] for row in report["cases"]])
    if any(report[key] != value for key, value in computed.items()):
        raise ValueError("Recorded scores differ from recomputed span coverage")
    return suite, report


def score_cases(cases, retrieved):
    rows = []
    for case, hits in zip(cases, retrieved, strict=True):
        hits = hits[:8]
        found = [gold["id"] for gold in case["gold"] if any(covers(hit, gold) for hit in hits)]
        first = next(
            (i for i, hit in enumerate(hits, 1) if any(covers(hit, gold) for gold in case["gold"])),
            None,
        )
        rows.append(
            {
                **case,
                "retrieved": hits,
                "foundGoldGroups": found,
                "fullEvidence": len(found) == len(case["gold"]) if case["gold"] else None,
                "reciprocalRank": 1 / first if first else 0,
            }
        )
    metrics = {}
    for split, language in sorted({(row["split"], row["language"]) for row in rows}):
        group = [row for row in rows if row["split"] == split and row["language"] == language]
        answerable = [row for row in group if row["gold"]]
        found = sum(len(row["foundGoldGroups"]) for row in group)
        required = sum(len(row["gold"]) for row in group)
        metrics.setdefault(split, {})[language] = {
            "questions": len(group),
            "answerableQuestions": len(answerable),
            "goldGroupsFound": found,
            "goldGroups": required,
            "evidenceRecallAt8": found / required if required else None,
            "anyHitQuestions": sum(bool(row["foundGoldGroups"]) for row in answerable),
            "fullEvidenceQuestions": sum(row["fullEvidence"] for row in answerable),
            "meanReciprocalRank": sum(row["reciprocalRank"] for row in answerable) / len(answerable)
            if answerable
            else None,
        }
    return {
        "metrics": metrics,
        "cases": rows,
        "unmeasured": {
            name: None
            for name in (
                "citationValidity",
                "humanSupportedClaims",
                "abstention",
                "conflictHandling",
                "productionPermissionIsolation",
                "answerLatency",
                "generationTokens",
                "postgresKeyword",
                "postgresHybrid",
                "ingestionOCR",
                "freshFullStackSetup",
            )
        },
    }
