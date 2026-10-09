"""Human annotations are separate from captured model answers and automatic citation checks."""

from .service import digest


def review_template(capture):
    return {
        "captureHash": capture["captureHash"],
        "reviewer": "",
        "cases": [
            {
                "id": row["id"],
                "claims": [
                    {
                        "block": i,
                        "start": 0,
                        "end": len(block["text"]),
                        "text": block["text"],
                        "supported": None,
                        "note": "",
                    }
                    for i, block in enumerate((row["answer"] or {}).get("blocks", []))
                ],
                "factsComplete": None,
                "abstentionCorrect": None,
                "conflictAttributed": None,
            }
            for row in capture["cases"]
        ],
    }


def score_review(capture, review):
    if (
        capture["captureHash"]
        != digest({key: value for key, value in capture.items() if key != "captureHash"})
        or review["captureHash"] != capture["captureHash"]
    ):
        raise ValueError("Capture changed or review belongs to another capture")
    rows = {row["id"]: row for row in capture["cases"]}
    annotations = {row["id"]: row for row in review["cases"]}
    if (
        len(rows) != len(capture["cases"])
        or len(annotations) != len(review["cases"])
        or rows.keys() != annotations.keys()
    ):
        raise ValueError("Review must contain every captured case exactly once")
    claims, abstentions, facts, conflicts = [], [], [], []
    reviewed = 0
    citations = [check for row in rows.values() for check in row["citationChecks"]]
    if any(type(check) is not bool for check in citations):
        raise ValueError("Citation checks must be booleans")
    for key, row in rows.items():
        annotation = annotations[key]
        blocks = (row["answer"] or {}).get("blocks", [])
        for field in ["factsComplete", "abstentionCorrect", "conflictAttributed"]:
            if annotation[field] is not None and type(annotation[field]) is not bool:
                raise ValueError("Human verdicts must be true, false or null")
        covered = {i: set() for i in range(len(blocks))}
        seen = set()
        for claim in annotation["claims"]:
            block = claim["block"]
            start, end = claim["start"], claim["end"]
            if (
                type(block) is not int
                or not 0 <= block < len(blocks)
                or type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(blocks[block]["text"])
                or not isinstance(claim["text"], str)
                or not claim["text"].strip()
                or claim["text"] != blocks[block]["text"][start:end]
                or (claim["supported"] is not None and type(claim["supported"]) is not bool)
            ):
                raise ValueError("Claims must quote a captured answer block with a boolean verdict")
            if (block, start, end) in seen:
                raise ValueError("Duplicate claims would inflate the human support denominator")
            seen.add((block, start, end))
            positions = set(range(start, end))
            if covered[block] & positions:
                raise ValueError("Claim spans must not overlap")
            covered[block].update(positions)
        if row["state"] != "COMPLETED" or row["answer"] is None:
            if annotation["claims"] or any(
                annotation[field] is not None
                for field in ["factsComplete", "abstentionCorrect", "conflictAttributed"]
            ):
                raise ValueError("Missing or unfinished answers cannot be human-labelled")
            continue
        complete = (
            all(claim["supported"] is not None for claim in annotation["claims"])
            and all(
                all(
                    pos in covered[i]
                    for pos, char in enumerate(block["text"])
                    if not char.isspace()
                )
                for i, block in enumerate(blocks)
            )
            and (
                annotation["factsComplete"] is not None
                if row["gold"]
                else annotation["abstentionCorrect"] is not None
            )
            and (row["category"] != "conflict" or annotation["conflictAttributed"] is not None)
        )
        if not complete:
            continue
        if not isinstance(review["reviewer"], str) or not review["reviewer"].strip():
            raise ValueError("Name the human reviewer before reporting reviewed results")
        reviewed += 1
        claims.extend(claim["supported"] for claim in annotation["claims"])
        if row["gold"]:
            facts.append(annotation["factsComplete"])
        else:
            abstentions.append(
                annotation["abstentionCorrect"]
                and row["answer"]["status"] == "INSUFFICIENT_EVIDENCE"
            )
        if row["category"] == "conflict":
            conflicts.append(
                annotation["conflictAttributed"]
                and row["answer"]["status"] == "CONFLICTING_EVIDENCE"
            )

    def rate(values):
        return sum(values) / len(values) if values else None

    return {
        "suite": capture["suite"],
        "suiteHash": capture["suiteHash"],
        "captureHash": capture["captureHash"],
        "split": capture["split"],
        "totalCases": len(rows),
        "reviewedCases": reviewed,
        "missingAnswers": sum(
            row["state"] != "COMPLETED" or row["answer"] is None for row in rows.values()
        ),
        "claimCount": len(claims),
        "supportedClaims": sum(claims),
        "humanSupportedClaims": rate(claims),
        "citationCount": len(citations),
        "validCitations": sum(citations),
        "citationValidity": rate(citations),
        "answerableCasesReviewed": len(facts),
        "requiredFactsComplete": rate(facts),
        "unsupportedCasesReviewed": len(abstentions),
        "unsupportedAbstention": rate(abstentions),
        "conflictCasesReviewed": len(conflicts),
        "conflictHandling": rate(conflicts),
        "reviewComplete": bool(rows) and reviewed == len(rows),
        "scope": "Demo answers and human annotations; full-stack acceptance stays separate",
    }
