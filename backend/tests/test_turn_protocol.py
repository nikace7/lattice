import uuid

import pytest

from modules.conversations.service import event_cursor, usage_charge, verify_hit


def test_event_cursor_is_turn_bound_and_bounded():
    turn = uuid.uuid4()
    assert event_cursor("", turn) == 0
    assert event_cursor(f"{turn}:7", turn) == 7
    for value in ["-1", f"{uuid.uuid4()}:7", f"{turn}:-1", f"{turn}:999999999999", "oops"]:
        with pytest.raises(ValueError):
            event_cursor(value, turn)


def test_uncertain_usage_keeps_reservation_and_known_usage_survives_cancellation():
    assert usage_charge([]) == 0
    assert (
        usage_charge([{"reserved": 100, "input": None, "output": None, "uncertain": True}]) == 100
    )
    assert usage_charge([{"reserved": 100, "input": 5, "output": 7, "uncertain": False}]) == 12


def test_retrieved_span_must_match_actual_source_before_dispatch():
    from types import SimpleNamespace

    block = SimpleNamespace(text="😀 café नेपाली", locator={"line": 1})
    hit = {
        "text": "café",
        "spans": [{"block_id": "b", "start": 2, "end": 6, "chunk_start": 0, "chunk_end": 4}],
        "locations": [{"line": 1}],
    }
    verify_hit(hit, {"b": block})
    for blocks in [{}, {"b": SimpleNamespace(text="wrong", locator={"line": 1})}]:
        with pytest.raises(ValueError):
            verify_hit(hit, blocks)
