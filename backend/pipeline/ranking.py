"""Deterministic RRF and bounded source diversity; scores are not probabilities."""

import unicodedata
from collections import Counter
from difflib import SequenceMatcher


def normalize_query(value):
    if not isinstance(value, str) or len(value) > 4000:
        raise ValueError("Enter a search of at most 4,000 characters.")
    value = unicodedata.normalize("NFC", value).strip()
    if not value or any(unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in value):
        raise ValueError("Enter a nonempty search without control characters.")
    return value


def overlapping(a, b):
    return any(
        left["block_id"] == right["block_id"]
        and max(left["start"], right["start"]) < min(left["end"], right["end"])
        for left in getattr(a, "spans", [])
        for right in getattr(b, "spans", [])
    )


def rank_hits(lexical, vector):
    hits = {}
    for name, candidates in [("lexicalRank", lexical), ("vectorRank", vector)]:
        for rank, chunk in enumerate(candidates[:20], 1):
            row = hits.setdefault(
                chunk.id,
                {
                    "chunk": chunk,
                    "lexicalRank": None,
                    "vectorRank": None,
                    "rrf": 0.0,
                    "lexicalScore": None,
                    "cosineDistance": None,
                },
            )
            row[name] = rank
            row["rrf"] += 1 / (60 + rank)
            row["lexicalScore" if name == "lexicalRank" else "cosineDistance"] = getattr(
                chunk, "score", None
            )
    ranked = sorted(hits.values(), key=lambda row: (-row["rrf"], str(row["chunk"].id)))[:12]
    unique = []
    for row in ranked:
        chunk = row["chunk"]
        # ponytail: compare at most 12 small chunks; replace heuristic only after recall evaluation.
        duplicate = any(
            chunk.document_id == other["chunk"].document_id
            and (
                chunk.text == other["chunk"].text
                or (
                    overlapping(chunk, other["chunk"])
                    and SequenceMatcher(
                        None, chunk.text, other["chunk"].text, autojunk=False
                    ).ratio()
                    >= 0.9
                )
            )
            for other in unique
        )
        if not duplicate:
            unique.append(row)
    counts = Counter()
    cap = 8 if len({row["chunk"].document_id for row in unique}) < 2 else 3
    chosen = []
    for row in unique:
        document = row["chunk"].document_id
        if counts[document] < cap:
            counts[document] += 1
            chosen.append(row)
        if len(chosen) == 8:
            break
    return chosen
