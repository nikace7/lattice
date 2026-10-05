"""Offline boundary checks; real pinned-model verification is models:check."""

import math
import uuid
from types import SimpleNamespace

import pytest

from pipeline.chunking import chunk_blocks
from pipeline.embedding import model_directory, validate_vectors


class CharacterTokenizer:
    """Deliberately pessimistic tokenizer to exercise Unicode boundaries without a model."""

    def __call__(self, text, **kwargs):
        result = {"input_ids": list(range(len(text)))}
        if kwargs.get("return_offsets_mapping"):
            result["offset_mapping"] = [(i, i + 1) for i in range(len(text))]
        return result


def block(text, **locator):
    return SimpleNamespace(id=uuid.uuid4(), text=text, locator=locator)


def test_chunks_preserve_unicode_spans_pages_exclusions_and_overlap():
    blocks = [
        block("नेपाली e\u0301 text " * 80, page=1),
        block("Excluded", page=2),
        block("New page", page=3),
    ]
    chunks = chunk_blocks(blocks, CharacterTokenizer(), excluded_pages=[2])
    by_id = {str(b.id): b for b in blocks}
    covered = set()
    for chunk in chunks:
        assert 0 < chunk["token_count"] <= 384
        assert len(chunk["text"]) <= 384
        assert "Excluded" not in chunk["text"]
        assert len({by_id[s["block_id"]].locator["page"] for s in chunk["spans"]}) == 1
        for span in chunk["spans"]:
            source = by_id[span["block_id"]]
            assert (
                source.text[span["start"] : span["end"]]
                == chunk["text"][span["chunk_start"] : span["chunk_end"]]
            )
            if source is blocks[0]:
                covered.update(range(span["start"], span["end"]))
    assert covered == set(range(len(blocks[0].text)))
    assert chunks[0]["spans"][-1]["end"] > chunks[1]["spans"][0]["start"]
    assert chunks == chunk_blocks(blocks, CharacterTokenizer(), excluded_pages=[2])


def test_sections_keep_headings_and_table_rows_separate():
    blocks = [
        block("First", headingPath=["A"]),
        block("Second", headingPath=["B"]),
        block("Header", table=1, row=1, cell=1),
        block("Value", table=1, row=2, cell=1),
    ]
    chunks = chunk_blocks(blocks, CharacterTokenizer())
    assert chunks[0]["text"] == "First"
    assert chunks[1]["text"] == "Second"
    assert chunks[-1]["text"] == "Header\nValue"
    assert chunks[-1]["spans"][0]["block_id"] == str(blocks[2].id)


def test_vectors_reject_invalid_count_dimension_nonfinite_and_unnormalized():
    good = [1 / math.sqrt(384)] * 384
    validate_vectors([good], 1)
    for vectors in [[], [[1.0]], [[float("nan")] * 384], [[float("inf")] * 384], [[0.0] * 384]]:
        with pytest.raises(ValueError):
            validate_vectors(vectors, 1)


def test_model_setup_is_explicit_and_wide_table_never_loses_context(tmp_path):
    with pytest.raises(ValueError, match="models:prepare"):
        model_directory(tmp_path)
    with pytest.raises(ValueError, match="table row"):
        chunk_blocks(
            [block("H" * 100, table=1, row=1), block("V" * 300, table=1, row=2)],
            CharacterTokenizer(),
        )


def test_index_lease_loss_stops_before_publication():
    from unittest.mock import patch

    from modules.documents import indexing

    with patch.object(indexing.IndexVersion.objects, "filter") as query:
        query.return_value.update.return_value = 0
        with pytest.raises(indexing.IndexStopped):
            indexing.renew("index", "attempt")
        assert "updated_at__gt" in query.call_args.kwargs
        assert query.call_args.kwargs["attempt"] == "attempt"


def test_markdown_heading_and_text_paragraph_boundaries_do_not_share_overlap():
    blocks = [
        block("# A", line=1),
        block("First", line=2),
        block("## B", line=3),
        block("Second", line=4),
    ]
    assert [c["text"] for c in chunk_blocks(blocks, CharacterTokenizer(), kind="MD")] == [
        "# A\nFirst",
        "## B\nSecond",
    ]
    blocks = [block("First", line=1), block("Second", line=3)]
    assert [c["text"] for c in chunk_blocks(blocks, CharacterTokenizer())] == ["First", "Second"]
