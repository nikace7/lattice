import uuid

import pytest
from django.utils import timezone

from modules.collections.models import CollectionGrant
from modules.conversations.models import Turn
from modules.workspaces.models import Membership
from tests import test_document_sources as sources
from tests.test_conversations import ask, run
from tests.test_retrieval import indexed

pytestmark = pytest.mark.django_db(transaction=True)
library = sources.library


def test_feedback_is_private_idempotent_and_requires_available_answer(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, reader, collection = library
    chunk = indexed(collection, "Request leave five working days ahead.")
    response, _ = ask(client, collection)
    turn = Turn.objects.get(pk=response.data["id"])
    endpoint = f"/api/v1/turns/{turn.pk}/feedback"
    assert client.post(endpoint, {"helpful": True}, format="json").status_code == 409
    run(turn)
    assert client.post(endpoint, {}, format="json").status_code == 400
    for helpful in [True, True, False]:
        response = client.post(endpoint, {"helpful": helpful}, format="json")
        assert response.status_code == 200 and response.data["helpful"] is helpful
        turn.refresh_from_db()
        assert turn.helpful is helpful
    client.force_login(reader)
    assert client.post(endpoint, {"helpful": True}, format="json").status_code == 404
    client.force_login(turn.conversation.owner)
    chunk.index.extraction.source.document.deleted_at = turn.created_at
    chunk.index.extraction.source.document.save(update_fields=["deleted_at"])
    assert client.post(endpoint, {"helpful": True}, format="json").status_code == 404
    assert client.get(f"/api/v1/turns/{turn.pk}").data["helpful"] is None


def test_export_rechecks_private_history_and_preserves_retained_citation(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, reader, collection = library
    membership = Membership.objects.get(user=reader, workspace=collection.workspace)
    membership.role = "MEMBER"
    membership.save()
    collection.access = "RESTRICTED"
    collection.save()
    grant = CollectionGrant.objects.create(collection=collection, membership=membership)
    chunk = indexed(
        collection, "Request leave five working days ahead.", title="Policy ``` <script>"
    )
    client.force_login(reader)
    response, _ = ask(client, collection)
    turn = Turn.objects.get(pk=response.data["id"])
    endpoint = f"/api/v1/conversations/{turn.conversation_id}/export"
    assert client.post(endpoint).status_code == 409
    run(turn)
    chunk.index.active = False
    chunk.index.save(update_fields=["active"])
    response = client.post(endpoint)
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    assert response.data["filename"] == f"lattice-{turn.conversation_id}.md"
    markdown = response.data["markdown"]
    assert "five working days" in markdown and "Source version 1" in markdown
    assert "````text\nPolicy ``` <script>\n````" in markdown
    assert str(chunk.index.extraction.source_id) in markdown
    assert f"/w/{collection.workspace_id}/c/{turn.conversation_id}" in markdown
    history = client.get(f"/api/v1/conversations/{turn.conversation_id}/turns")
    assert history.status_code == 200 and history.data["results"][0]["answer"]
    retained = client.get(f"/api/v1/turns/{turn.pk}/citations/0/0")
    assert retained.status_code == 200 and retained.data["sourceNumber"] == 1
    client.force_login(turn.conversation.workspace.memberships.get(role="OWNER").user)
    assert client.post(endpoint).status_code == 404
    client.force_login(reader)
    grant.delete()
    response = client.post(endpoint)
    assert response.status_code == 200
    assert "sources that are no longer available" in response.data["markdown"]
    assert "five working days" not in response.data["markdown"]
    assert str(chunk.index.extraction.source_id) not in response.data["markdown"]
    membership.active = False
    membership.save()
    assert client.post(endpoint).status_code == 404


def test_export_refuses_to_silently_truncate_a_large_conversation(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, _, collection = library
    indexed(collection, "Request leave five working days ahead.")
    response, _ = ask(client, collection)
    turn = Turn.objects.get(pk=response.data["id"])
    run(turn)
    Turn.objects.bulk_create(
        [
            Turn(
                conversation=turn.conversation,
                idempotency_key=uuid.uuid4(),
                state="FAILED",
                lease_until=timezone.now(),
                charged_tokens=0,
            )
            for _ in range(100)
        ]
    )
    response = client.post(f"/api/v1/conversations/{turn.conversation_id}/export")
    assert response.status_code == 400
    assert "100 questions" in response.data["error"]["message"]
