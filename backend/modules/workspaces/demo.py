"""Offline fixture import and reset for one explicitly marked disposable database."""

import hashlib
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.base import CommandError
from django.db import connection, transaction

from modules.collections.models import Collection, CollectionGrant
from modules.conversations.models import ACTIVE, Turn
from modules.documents.models import Document, ExtractionJob, IndexVersion, Reindex, SourceVersion
from modules.documents.storage import source_path
from modules.identity.models import User
from modules.retrieval.frozen import load_suite
from modules.retrieval.service import digest
from pipeline.source_parser import validate_bytes

from .models import DemoInstallation, Membership, Workspace

MARKER = ".lattice-demo.json"
TEMP_MARKER = ".lattice-demo.tmp"
PERSONAS = ["a-member", "a-curator", "a-owner", "b-owner"]


def corpus_root():
    return Path(settings.REPO_ROOT)


def database_name():
    config = connection.settings_dict
    if config["ENGINE"] != "django.db.backends.postgresql" or config["HOST"] not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise CommandError("Demo commands require local PostgreSQL.")
    if config["NAME"] != "lattice_demo":
        raise CommandError("Demo commands require the dedicated lattice_demo database.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        return cursor.fetchone()[0]


def dedicated_root(root, name):
    expected = Path(settings.REPO_ROOT) / ".data" / name
    if root != expected.resolve() or any(
        path.is_symlink() or path.is_junction() for path in [expected.parent, expected]
    ):
        raise CommandError("Use the dedicated demo storage and parser paths without links.")


def environment():
    if not settings.DEMO_MODE:
        raise CommandError("Set DEMO_MODE=true for a disposable demo installation only.")
    root = Path(settings.STORAGE_ROOT)
    dedicated_root(root, "demo-storage")
    spool = Path(settings.PARSER_SPOOL_ROOT)
    dedicated_root(spool, "demo-parser")
    if spool.exists() and any(spool.iterdir()):
        raise CommandError("Stop the parser and finish its pending demo spool requests first.")
    if database_name() != "lattice_demo":
        raise CommandError("Demo commands require the dedicated lattice_demo database.")
    return root


@contextmanager
def operator_lock():
    # Covers filesystem work too; released by PostgreSQL if the operator process dies.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(782034801)")
        if not cursor.fetchone()[0]:
            raise CommandError("Another demo command is running.")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(782034801)")


def marker_data(installation):
    return {
        "token": str(installation.token),
        "database": installation.database,
        "storageRoot": installation.storage_root,
        "version": 1,
    }


def write_marker(root, installation):
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / TEMP_MARKER
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(marker_data(installation), stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(root / MARKER)
    finally:
        temporary.unlink(missing_ok=True)


def check_marker(root, installation):
    if installation.database != "lattice_demo" or installation.storage_root != str(root):
        raise CommandError("The database demo marker belongs to another storage root.")
    try:
        path = root / MARKER
        if path.is_symlink() or path.is_junction() or path.stat().st_size > 4096:
            raise ValueError
        if json.loads(path.read_text(encoding="utf-8")) != marker_data(installation):
            raise ValueError
    except (OSError, ValueError) as error:
        raise CommandError("The database and storage demo markers must match.") from error


def checked_tree(root):
    dedicated_root(root, "demo-storage")
    for directory, folders, files in os.walk(root, followlinks=False):
        for path in [Path(directory), *(Path(directory) / name for name in folders + files)]:
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):
                raise CommandError("Demo storage contains a link; reset refused.")


def clear_storage(root):
    checked_tree(root)
    for path in root.iterdir():
        if path.name != MARKER:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def fixture_id(installation, key):
    return uuid.uuid5(installation.seed_token, key)


def assert_empty():
    if User.objects.exists() or Workspace.objects.exists() or Session.objects.exists():
        raise CommandError("Initial seeding requires an empty application database.")


def seed(root, password):
    suite = load_suite(corpus_root(), "r8-v1")
    with operator_lock():
        installation = DemoInstallation.objects.filter(pk=1).first()
        if not installation:
            assert_empty()
            if root.exists() and any(root.iterdir()):
                raise CommandError("Initial seeding requires empty demo storage.")
            installation = DemoInstallation.objects.create(
                database="lattice_demo",
                storage_root=str(root),
                suite_hash=digest(suite),
            )
        # Repair only an empty initialization, including a partially written temporary marker.
        contents = {path.name for path in root.iterdir()} if root.exists() else set()
        if installation.state == "EMPTY" and contents <= {TEMP_MARKER}:
            assert_empty()
            if installation.storage_root != str(root) or installation.database != "lattice_demo":
                raise CommandError("The database demo marker belongs to another storage root.")
            temporary = root / TEMP_MARKER
            if temporary.exists() or temporary.is_symlink():
                if temporary.is_symlink() or temporary.is_junction() or not temporary.is_file():
                    raise CommandError("The temporary demo marker must be a regular file.")
                temporary.unlink()
            write_marker(root, installation)
        check_marker(root, installation)
        if installation.suite_hash != digest(suite):
            raise CommandError("The marked demo corpus differs from the frozen suite.")
        if installation.state == "READY":
            return False
        if installation.state != "EMPTY":
            raise CommandError("An interrupted demo operation requires a guarded reset first.")
        assert_empty()
        if any(path.name != MARKER for path in root.iterdir()):
            raise CommandError("Demo storage is not empty; use the guarded reset first.")
        installation.state = "SEEDING"
        installation.seed_token = uuid.uuid4()
        installation.save(update_fields=["state", "seed_token"])
        # Files cannot join the SQL transaction; SEEDING survives failure for guarded reset.
        with transaction.atomic():
            workspaces = {
                key: Workspace.objects.create(
                    id=fixture_id(installation, f"workspace:{key}"),
                    name=name,
                )
                for key, name in [("a", "Cedar Studio"), ("b", "Birch Studio")]
            }
            members = {}
            for key, persona in suite["personas"].items():
                user = User.objects.create_user(
                    id=fixture_id(installation, f"user:{key}"),
                    username=f"demo-{key}",
                    email=f"demo-{key}@lattice.invalid",
                    password=password,
                )
                members[key] = Membership.objects.create(
                    workspace=workspaces[persona["workspace"]],
                    user=user,
                    role=persona["role"],
                )
            collections = {}
            for item in suite["collections"]:
                collection = Collection.objects.create(
                    id=fixture_id(installation, f"collection:{item['id']}"),
                    workspace=workspaces[item["workspace"]],
                    title={
                        "handbook": "Handbook",
                        "b-handbook": "Handbook",
                        "projects": "Projects",
                        "finance": "Finance",
                    }[item["id"]],
                    access="WORKSPACE" if item["minimumRole"] == "MEMBER" else "RESTRICTED",
                )
                collections[item["id"]] = collection
                if item["minimumRole"] == "CURATOR":
                    CollectionGrant.objects.create(
                        collection=collection,
                        membership=members["a-curator"],
                        can_write=True,
                    )
            for item in suite["documents"]:
                owner = members[f"{item['workspace']}-owner"].user
                document = Document.objects.create(
                    id=fixture_id(installation, f"document:{item['id']}"),
                    title=item["title"],
                    collection=collections[item["collection"]],
                    created_by=owner,
                )
                for version in item["sources"]:
                    content = (
                        corpus_root() / "fixtures/corpus/r8-v1" / version["file"]
                    ).read_bytes()
                    if hashlib.sha256(content).hexdigest() != version["sha256"]:
                        raise CommandError(
                            "A frozen source changed while seeding; reset and retry."
                        )
                    validate_bytes(content, version["kind"])
                    source = SourceVersion.objects.create(
                        id=fixture_id(installation, f"source:{version['id']}"),
                        document=document,
                        number=version["number"],
                        created_by=owner,
                        filename=version["file"],
                        kind=version["kind"],
                        byte_size=len(content),
                        sha256=version["sha256"],
                        ocr_language="nep" if item["id"].startswith("nep-") else "eng",
                    )
                    path = source_path(source)
                    path.parent.mkdir(parents=True)
                    with path.open("xb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    ExtractionJob.objects.create(
                        source=source,
                        state="CANCELLED",
                        error="Demo source imported; retry extraction when workers are ready.",
                    )
            installation.state = "READY"
            installation.save(update_fields=["state"])
        return True


def reset(root):
    with operator_lock():
        installation = DemoInstallation.objects.filter(pk=1).first()
        if not installation:
            raise CommandError("An unmarked database cannot be reset.")
        check_marker(root, installation)
        checked_tree(root)
        with transaction.atomic():
            installation = DemoInstallation.objects.select_for_update().get(pk=1)
            workspace_ids = [fixture_id(installation, f"workspace:{key}") for key in ["a", "b"]]
            user_ids = [fixture_id(installation, f"user:{key}") for key in PERSONAS]
            if (
                Workspace.objects.exclude(pk__in=workspace_ids).exists()
                or User.objects.exclude(
                    pk__in=user_ids,
                ).exists()
            ):
                raise CommandError("Unrelated accounts or workspaces exist; reset refused.")
            list(Workspace.objects.select_for_update().filter(pk__in=workspace_ids))
            if (
                ExtractionJob.objects.filter(state__in=["QUEUED", "EXTRACTING"]).exists()
                or IndexVersion.objects.filter(
                    state__in=["QUEUED", "CHUNKING", "EMBEDDING"]
                ).exists()
                or Reindex.objects.filter(state="BUILDING").exists()
                or Turn.objects.filter(state__in=ACTIVE).exists()
            ):
                raise CommandError("Cancel or finish active demo jobs before resetting.")
            installation.state = "RESETTING"
            installation.save(update_fields=["state"])
            Document.objects.filter(collection__workspace_id__in=workspace_ids).delete()
            Workspace.objects.filter(pk__in=workspace_ids).delete()
            User.objects.filter(pk__in=user_ids).delete()
            Session.objects.all().delete()
        clear_storage(root)
        installation.state = "EMPTY"
        installation.save(update_fields=["state"])
