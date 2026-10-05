"""Database-free checks for retry eligibility and cancellation at the parser boundary."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from modules.documents import tasks
from modules.documents.models import ExtractionJob


def test_retry_eligibility_tracks_terminal_states_and_expired_leases():
    now = timezone.now()
    for state, age, flag, expected in [
        ("QUEUED", 0, False, False),
        ("EXTRACTING", 91, False, True),
        ("QUEUED", 91, False, True),
        ("CANCELLED", 0, False, True),
        ("FAILED", 0, True, True),
        ("FAILED", 100, False, False),
        ("REVIEWED", 100, True, False),
    ]:
        job = ExtractionJob(state=state, retryable=flag, updated_at=now - timedelta(seconds=age))
        assert job.can_retry is expected


def test_cancelled_parser_wait_removes_only_its_own_spool(settings, tmp_path):
    settings.PARSER_SPOOL_ROOT = tmp_path / "spool"
    settings.PARSER_SPOOL_ROOT.mkdir()
    unrelated = settings.PARSER_SPOOL_ROOT / "other-job"
    unrelated.mkdir()
    original = tmp_path / "original"
    original.write_text("Text")
    source = SimpleNamespace(
        pk=uuid.uuid4(), kind="TXT", ocr_language="eng", job=SimpleNamespace(attempt=uuid.uuid4())
    )
    with (
        patch.object(tasks, "source_path", return_value=original),
        patch.object(tasks, "maintain_lease", side_effect=[None, tasks.ExtractionStopped]),
        patch.object(tasks.time, "sleep"),
        pytest.raises(tasks.ExtractionStopped),
    ):
        tasks.parse_source(source)
    assert list(settings.PARSER_SPOOL_ROOT.iterdir()) == [unrelated]
    assert original.read_text() == "Text"


def test_lost_lease_cannot_be_renewed():
    with patch.object(tasks.ExtractionJob.objects, "filter") as query:
        query.return_value.update.return_value = 0
        with pytest.raises(tasks.ExtractionStopped):
            tasks.maintain_lease("source", "attempt", renew=True)
        assert query.call_args.kwargs["state"] == "EXTRACTING"
        assert "updated_at__gt" in query.call_args.kwargs


def test_supervisor_kills_owned_group_when_worker_removes_spool(tmp_path):
    from pipeline import parser_service

    missing = tmp_path / "removed-job"
    with (
        patch.object(parser_service.subprocess, "Popen") as spawn,
        patch.object(parser_service.os, "killpg", create=True) as kill,
        patch.object(parser_service.signal, "SIGKILL", 9, create=True),
    ):
        spawn.return_value.poll.return_value = None
        spawn.return_value.pid = 12345
        parser_service.run(missing)
    assert spawn.call_args.kwargs["start_new_session"] is True
    kill.assert_called_once_with(12345, 9)
    spawn.return_value.wait.assert_called_once()
    assert not missing.exists()
