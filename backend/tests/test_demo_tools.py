import json
import uuid
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from modules.workspaces import demo


@pytest.fixture
def demo_environment(settings, tmp_path, monkeypatch):
    settings.REPO_ROOT = tmp_path
    settings.DEMO_MODE = True
    settings.STORAGE_ROOT = tmp_path / ".data/demo-storage"
    settings.PARSER_SPOOL_ROOT = tmp_path / ".data/demo-parser"
    monkeypatch.setattr(demo, "database_name", lambda: "lattice_demo")
    return settings.STORAGE_ROOT


def test_disabled_demo_commands_never_connect(settings, monkeypatch):
    settings.DEMO_MODE = False
    monkeypatch.setattr(demo, "database_name", lambda: pytest.fail("Database accessed"))
    for command in ["seed_demo", "reset_demo"]:
        with pytest.raises(CommandError, match="DEMO_MODE"):
            call_command(command)


@pytest.mark.parametrize("field", ["STORAGE_ROOT", "PARSER_SPOOL_ROOT"])
def test_demo_rejects_other_storage_before_database(demo_environment, settings, monkeypatch, field):
    setattr(settings, field, settings.REPO_ROOT / ".data/storage")
    monkeypatch.setattr(demo, "database_name", lambda: pytest.fail("Database accessed"))
    with pytest.raises(CommandError, match="dedicated demo"):
        demo.environment()


def test_demo_rejects_other_database(demo_environment, monkeypatch):
    monkeypatch.setattr(demo, "database_name", lambda: "lattice")
    with pytest.raises(CommandError, match="lattice_demo"):
        demo.environment()


@pytest.mark.parametrize("key,value", [("HOST", "remote.example"), ("NAME", "lattice")])
def test_database_configuration_refused_before_connection(monkeypatch, key, value):
    from types import SimpleNamespace

    config = {
        "HOST": "127.0.0.1",
        "NAME": "lattice_demo",
        "ENGINE": "django.db.backends.postgresql",
    }
    config[key] = value
    monkeypatch.setattr(demo, "connection", SimpleNamespace(settings_dict=config))
    with pytest.raises(CommandError):
        demo.database_name()


def test_parser_spool_must_be_empty(demo_environment, settings, monkeypatch):
    settings.PARSER_SPOOL_ROOT.mkdir(parents=True)
    (settings.PARSER_SPOOL_ROOT / "request").write_text("pending")
    monkeypatch.setattr(demo, "database_name", lambda: pytest.fail("Database accessed"))
    with pytest.raises(CommandError, match="pending"):
        demo.environment()


def test_marker_refuses_another_root(demo_environment):
    from types import SimpleNamespace

    with pytest.raises(CommandError, match="another storage"):
        demo.check_marker(
            demo_environment, SimpleNamespace(database="lattice_demo", storage_root="elsewhere")
        )


def test_cleanup_refuses_another_root(demo_environment, tmp_path):
    outside = tmp_path / "unrelated"
    outside.mkdir()
    (outside / "original").write_text("keep")
    with pytest.raises(CommandError, match="dedicated demo"):
        demo.clear_storage(outside)
    assert (outside / "original").read_text() == "keep"


def test_reset_requires_explicit_target_without_database(demo_environment, monkeypatch):
    monkeypatch.setattr(demo, "database_name", lambda: pytest.fail("Database accessed"))
    with pytest.raises(CommandError, match="confirm"):
        call_command("reset_demo")


def test_marker_matches_database_and_storage(demo_environment):
    root = demo_environment
    root.mkdir(parents=True)
    installation = type(
        "Marker", (), {"token": uuid.uuid4(), "database": "lattice_demo", "storage_root": str(root)}
    )()
    demo.write_marker(root, installation)
    demo.check_marker(root, installation)
    (root / demo.MARKER).write_text(json.dumps({"token": str(uuid.uuid4())}))
    with pytest.raises(CommandError, match="marker"):
        demo.check_marker(root, installation)


def test_reset_files_keeps_marker_and_other_roots(demo_environment, settings):
    root = demo_environment
    (root / "sources/nested").mkdir(parents=True)
    (root / "sources/nested/original").write_text("fictional")
    (root / demo.MARKER).write_text("marker")
    other = settings.REPO_ROOT / ".data/storage/original"
    other.parent.mkdir(parents=True)
    other.write_text("keep")
    demo.clear_storage(root)
    assert list(root.iterdir()) == [root / demo.MARKER]
    assert other.read_text() == "keep"


def test_reset_files_refuses_links(demo_environment, tmp_path):
    root = demo_environment
    root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not permit symlinks")
    with pytest.raises(CommandError, match="link"):
        demo.clear_storage(root)
    assert outside.exists()


def test_unconfirmed_reset_and_weak_seed_password_leave_no_files(demo_environment, monkeypatch):
    monkeypatch.setenv("LATTICE_DEMO_PASSWORD", "short")
    with pytest.raises(CommandError, match="password"):
        call_command("seed_demo")
    assert not demo_environment.exists()


@pytest.mark.django_db(transaction=True)
def test_seed_reset_round_trip(demo_environment, settings, monkeypatch):
    from modules.collections.models import CollectionGrant
    from modules.documents.models import Document, ExtractionJob, SourceVersion
    from modules.identity.models import User
    from modules.workspaces.access import readable_collections
    from modules.workspaces.models import DemoInstallation, Workspace

    # Only the environment guard's current_database query is replaced; ORM uses real PostgreSQL.
    monkeypatch.setenv("LATTICE_DEMO_PASSWORD", "Synthetic-Demo-Long-Passphrase-2026")
    monkeypatch.setattr(demo, "corpus_root", lambda: Path(__file__).resolve().parents[2])
    call_command("seed_demo")
    assert (User.objects.count(), Workspace.objects.count(), Document.objects.count()) == (4, 2, 24)
    assert SourceVersion.objects.count() == 25
    assert ExtractionJob.objects.filter(state="CANCELLED").count() == 25
    assert CollectionGrant.objects.count() == 1
    viewer = User.objects.get(username="demo-a-member")
    curator = User.objects.get(username="demo-a-curator")
    assert readable_collections(viewer).count() == 1
    assert readable_collections(curator).count() == 2
    before = list(SourceVersion.objects.values_list("id", flat=True))
    call_command("seed_demo")
    assert list(SourceVersion.objects.values_list("id", flat=True)) == before
    call_command("reset_demo", confirm="lattice_demo")
    assert not User.objects.exists() and not Workspace.objects.exists()
    assert DemoInstallation.objects.get(pk=1).state == "EMPTY"
    assert list(demo_environment.iterdir()) == [demo_environment / demo.MARKER]
    call_command("seed_demo")
    assert SourceVersion.objects.count() == 25
    assert not set(before).intersection(SourceVersion.objects.values_list("id", flat=True))


@pytest.mark.django_db(transaction=True)
def test_seed_refuses_nonempty_database(demo_environment, monkeypatch):
    from modules.identity.models import User

    monkeypatch.setenv("LATTICE_DEMO_PASSWORD", "Synthetic-Demo-Long-Passphrase-2026")
    monkeypatch.setattr(demo, "corpus_root", lambda: Path(__file__).resolve().parents[2])
    User.objects.create_user(username="unrelated")
    with pytest.raises(CommandError, match="empty"):
        call_command("seed_demo")
    assert User.objects.filter(username="unrelated").exists()
    assert not demo_environment.exists()


@pytest.fixture
def seeded_demo(demo_environment, monkeypatch):
    monkeypatch.setenv("LATTICE_DEMO_PASSWORD", "Synthetic-Demo-Long-Passphrase-2026")
    monkeypatch.setattr(demo, "corpus_root", lambda: Path(__file__).resolve().parents[2])
    call_command("seed_demo")
    return demo_environment


@pytest.mark.django_db(transaction=True)
def test_reset_refuses_unmarked_database(demo_environment):
    with pytest.raises(CommandError, match="unmarked"):
        call_command("reset_demo", confirm="lattice_demo")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "guard", ["unrelated-account", "unrelated-workspace", "active-job", "marker"]
)
def test_reset_refuses_unsafe_installation(seeded_demo, guard):
    from modules.documents.models import Document, ExtractionJob
    from modules.identity.models import User
    from modules.workspaces.models import Workspace

    if guard == "unrelated-account":
        User.objects.create_user(username="unrelated")
    elif guard == "unrelated-workspace":
        Workspace.objects.create(name="Unrelated")
    elif guard == "active-job":
        ExtractionJob.objects.filter(source__number=2).update(state="EXTRACTING")
    else:
        (seeded_demo / demo.MARKER).write_text("{}")
    with pytest.raises(CommandError):
        call_command("reset_demo", confirm="lattice_demo")
    assert Document.objects.count() == 24
    assert (seeded_demo / "sources").exists()


@pytest.mark.django_db(transaction=True)
def test_interrupted_seed_requires_reset(demo_environment, monkeypatch):
    from modules.documents.models import Document
    from modules.workspaces.models import DemoInstallation

    monkeypatch.setenv("LATTICE_DEMO_PASSWORD", "Synthetic-Demo-Long-Passphrase-2026")
    monkeypatch.setattr(demo, "corpus_root", lambda: Path(__file__).resolve().parents[2])
    validate = demo.validate_bytes
    calls = 0

    def fail_second_source(content, kind):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Simulated storage failure")
        return validate(content, kind)

    monkeypatch.setattr(demo, "validate_bytes", fail_second_source)
    with pytest.raises(OSError):
        call_command("seed_demo")
    assert DemoInstallation.objects.get(pk=1).state == "SEEDING"
    assert not Document.objects.exists()
    with pytest.raises(CommandError, match="interrupted"):
        call_command("seed_demo")
    call_command("reset_demo", confirm="lattice_demo")
    assert DemoInstallation.objects.get(pk=1).state == "EMPTY"


@pytest.mark.django_db(transaction=True)
def test_interrupted_storage_reset_can_resume(seeded_demo, monkeypatch):
    from modules.documents.models import Document
    from modules.workspaces.models import DemoInstallation

    cleanup = demo.clear_storage
    monkeypatch.setattr(
        demo, "clear_storage", lambda root: (_ for _ in ()).throw(OSError("Simulated failure"))
    )
    with pytest.raises(OSError):
        call_command("reset_demo", confirm="lattice_demo")
    assert not Document.objects.exists()
    assert DemoInstallation.objects.get(pk=1).state == "RESETTING"
    monkeypatch.setattr(demo, "clear_storage", cleanup)
    call_command("reset_demo", confirm="lattice_demo")
    assert DemoInstallation.objects.get(pk=1).state == "EMPTY"


@pytest.mark.django_db(transaction=True)
def test_interrupted_initial_marker_can_resume(demo_environment, monkeypatch):
    from modules.retrieval.frozen import load_suite
    from modules.retrieval.service import digest
    from modules.workspaces.models import DemoInstallation

    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("LATTICE_DEMO_PASSWORD", "Synthetic-Demo-Long-Passphrase-2026")
    monkeypatch.setattr(demo, "corpus_root", lambda: root)
    DemoInstallation.objects.create(
        database="lattice_demo",
        storage_root=str(demo_environment),
        suite_hash=digest(load_suite(root, "r8-v1")),
    )
    demo_environment.mkdir(parents=True)
    (demo_environment / demo.TEMP_MARKER).write_text('{"token":')
    call_command("seed_demo")
    assert DemoInstallation.objects.get(pk=1).state == "READY"
    assert not (demo_environment / demo.TEMP_MARKER).exists()
