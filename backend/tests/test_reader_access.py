import uuid

import pytest

from modules.collections.models import Collection
from modules.documents.models import (
    Document,
    ExtractionJob,
    ExtractionVersion,
    IndexVersion,
    SourceVersion,
)
from tests import test_document_sources as sources

pytestmark = pytest.mark.django_db
library = sources.library


def test_recorded_diagnostics_require_current_owner_membership(library):
    client, reader, collection = library
    path = f"/api/v1/workspaces/{collection.workspace_id}/evaluations"
    assert client.get(path).status_code == 200
    assert client.get(path + "/r4-embedding-development").status_code == 200
    assert client.get(path + "/unknown").status_code == 404
    client.force_login(reader)
    assert client.get(path).status_code == 403
    assert client.get(f"/api/v1/workspaces/{uuid.uuid4()}/evaluations").status_code == 404
    owner = collection.workspace.memberships.get(role="OWNER")
    owner.active = False
    owner.save(update_fields=["active"])
    client.force_login(owner.user)
    assert client.get(path).status_code == 404


def test_status_counts_scope_and_preserves_searchable_replacement(library):
    client, reader, collection = library
    owner = collection.workspace.memberships.get(role="OWNER").user
    document = Document.objects.create(collection=collection, title="Visible", created_by=owner)
    source = SourceVersion.objects.create(document=document, kind="TXT", byte_size=9)
    extraction = ExtractionVersion.objects.create(source=source, parser_version="test")
    IndexVersion.objects.create(
        extraction=extraction,
        requested_by=owner,
        profile={},
        chunker="test",
        state="READY",
        active=True,
    )
    replacement = SourceVersion.objects.create(document=document, number=2, kind="TXT", byte_size=9)
    ExtractionJob.objects.create(source=replacement)
    restricted = Collection.objects.create(
        workspace=collection.workspace, title="Hidden", access="RESTRICTED"
    )
    hidden = Document.objects.create(collection=restricted, title="Secret", created_by=owner)
    ExtractionJob.objects.create(
        source=SourceVersion.objects.create(document=hidden, kind="TXT", byte_size=9)
    )
    path = f"/api/v1/workspaces/{collection.workspace_id}/document-status"
    assert client.get(path).data == {"total": 2, "ready": 1, "processing": 2}
    client.force_login(reader)
    assert client.get(path).data == {"total": 1, "ready": 1, "processing": 1}
    assert client.get(f"/api/v1/workspaces/{uuid.uuid4()}/document-status").status_code == 404
