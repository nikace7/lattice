import json
import uuid
from types import SimpleNamespace

import pytest

from modules.documents.lifecycle import remove_source_files, write_tombstone


def test_tombstone_journal_replays_and_rejects_conflicts(settings, tmp_path):
    settings.STORAGE_ROOT = tmp_path
    document = SimpleNamespace(
        pk=uuid.uuid4(), collection=SimpleNamespace(workspace_id=uuid.uuid4())
    )
    write_tombstone(document)
    write_tombstone(document)
    path = tmp_path / "tombstones" / f"document-{document.pk}.json"
    assert json.loads(path.read_text())["document"] == str(document.pk)
    assert not list(path.parent.glob("*.tmp"))
    path.write_text("{}")
    with pytest.raises(RuntimeError, match="Conflicting"):
        write_tombstone(document)


def test_purge_removes_only_the_resolved_source_directory(settings, tmp_path):
    settings.STORAGE_ROOT = tmp_path
    source = SimpleNamespace(pk=uuid.uuid4())
    directory = tmp_path / "sources" / str(source.pk)
    directory.mkdir(parents=True)
    (directory / "original").write_text("private")
    untouched = tmp_path / "keep.txt"
    untouched.write_text("keep")
    remove_source_files(source)
    remove_source_files(source)
    assert not directory.exists() and untouched.read_text() == "keep"
    with pytest.raises(RuntimeError, match="outside"):
        remove_source_files(SimpleNamespace(pk="../.."))
