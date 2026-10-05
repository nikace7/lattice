"""Tokenizer-bounded chunks with exact Python Unicode offsets into source blocks."""

import hashlib
import re
import unicodedata
from bisect import bisect_left, bisect_right
from itertools import groupby

VERSION = "sections-atx-320-384-overlap40-first-row-v1"


class InvalidIndex(ValueError):
    """Safe, actionable indexing error that contains no source content."""


def section(block):
    location = block.locator
    return (location.get("page"), tuple(location.get("headingPath", [])), location.get("table"))


def chunk_blocks(blocks, tokenizer, excluded_pages=(), kind="TXT"):
    chunks = []
    allowed = (b for b in blocks if b.locator.get("page") not in excluded_pages and b.text.strip())
    boundary, previous_line = 0, None

    def group_key(block):
        nonlocal boundary, previous_line
        line = block.locator.get("line")
        if (kind == "MD" and re.match(r"^ {0,3}#{1,6}(?:\s|$)", block.text)) or (
            kind == "TXT"
            and line is not None
            and previous_line is not None
            and line > previous_line + 1
        ):
            boundary += 1
        previous_line = line
        return (*section(block), boundary)

    for key, members in groupby(allowed, key=group_key):
        members = list(members)
        if key[2] is not None:
            rows = [list(items) for _, items in groupby(members, key=lambda b: b.locator["row"])]
            # First-row context is repeated with its real cell spans, not an invented header.
            groups = [rows[0]] + [rows[0] + row for row in rows[1:]]
        else:
            groups = [members]
        for group in groups:
            for chunk in split_section(group, tokenizer, table=key[2] is not None):
                chunks.append(chunk)
                if len(chunks) > 10000:
                    raise InvalidIndex("Source exceeds the 10,000 chunk limit.")
    if not chunks:
        raise InvalidIndex("No accepted source text is available for indexing.")
    return chunks


def split_section(blocks, tokenizer, table=False):
    text = "\n".join(b.text for b in blocks)
    ranges, cursor = [], 0
    for block in blocks:
        ranges.append((block, cursor, cursor + len(block.text)))
        cursor += len(block.text) + 1
    offsets = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True, verbose=False)[
        "offset_mapping"
    ]
    if table and len(offsets) > 384:
        # ponytail: row plus first-row context must fit; add cell-wise context packing if needed.
        raise InvalidIndex(
            "A table row plus first-row context exceeds 384 tokens. "
            "Split wide or long cells in the source."
        )
    token_starts = [left for left, _ in offsets]
    block_ends = [right for _, _, right in ranges]
    block_starts = [left for _, left, _ in ranges]
    start = 0
    while start < len(text):
        token_start = bisect_left(token_starts, start)
        end = (
            len(text)
            if table or len(offsets) - token_start <= 320
            else offsets[token_start + 319][1]
        )
        # Prefer a complete block when it fits; long blocks still make forward progress.
        boundary = bisect_right(block_ends, end) - 1
        if boundary >= 0 and start + (end - start) // 2 < block_ends[boundary] and end < len(text):
            end = block_ends[boundary]
        while end < len(text) and unicodedata.combining(text[end]):
            end += 1
        count = len(tokenizer(text[start:end], add_special_tokens=False)["input_ids"])
        while count > 384 and end > start:
            end -= 1
            while end > start and unicodedata.combining(text[end]):
                end -= 1
            count = len(tokenizer(text[start:end], add_special_tokens=False)["input_ids"])
        if end <= start:
            raise InvalidIndex("A Unicode cluster exceeds the chunk token limit.")
        body = text[start:end]
        if len(tokenizer("passage: " + body)["input_ids"]) > 512:
            raise InvalidIndex("Chunk exceeds the embedding input limit.")
        spans = [
            {
                "block_id": str(block.id),
                "start": max(start, left) - left,
                "end": min(end, right) - left,
                "chunk_start": max(start, left) - start,
                "chunk_end": min(end, right) - start,
            }
            for block, left, right in ranges[
                bisect_right(block_ends, start) : bisect_left(block_starts, end)
            ]
            if max(start, left) < min(end, right)
        ]
        if body.strip():
            yield {
                "text": body,
                "spans": spans,
                "token_count": count,
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
            }
        if end == len(text):
            break
        used = tokenizer(body, add_special_tokens=False, return_offsets_mapping=True)[
            "offset_mapping"
        ]
        next_start = start + used[-40][0] if len(used) > 40 else end
        while next_start < end and unicodedata.combining(text[next_start]):
            next_start += 1
        start = next_start if start < next_start < end else end
