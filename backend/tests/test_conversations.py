import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import close_old_connections
from django.utils import timezone

from modules.collections.models import Collection, CollectionGrant
from modules.conversations.api import event_batch
from modules.conversations.models import Conversation, Turn
from modules.conversations.serializers import QuestionInput
from modules.conversations.service import cancel_turn, create_turn
from modules.conversations.tasks import generate_answer, recover_answers
from modules.workspaces.models import Membership
from tests import test_document_sources as sources
from tests.test_grounding import Generator, draft, verdict
from tests.test_retrieval import indexed

pytestmark = pytest.mark.django_db(transaction=True)
library = sources.library


def ask(client, collection, **extra):
    data = {
        "conversationId": str(uuid.uuid4()),
        "idempotencyKey": str(uuid.uuid4()),
        "question": "How early should I request leave?",
        "collectionIds": [str(collection.pk)],
    }
    data.update(extra)
    with patch("modules.conversations.tasks.generate_answer.delay"):
        response = client.post(
            f"/api/v1/workspaces/{collection.workspace_id}/questions", data, format="json"
        )
    return response, data


def run(turn, *, during=None):
    class Model(Generator):
        digest = "a" * 64

        def __init__(self, *_, record_usage, **kwargs):
            super().__init__([draft(), verdict()])
            self.record_usage, self.usage = record_usage, []

        def complete(self, prompt, schema, limit, check):
            self.usage.append({"reserved": 100, "input": None, "output": None, "uncertain": True})
            self.record_usage(self.usage, starting=True)
            if during:
                during()
            value = super().complete(prompt, schema, limit, check)
            self.usage[-1].update(input=20, output=10, uncertain=False)
            self.record_usage(self.usage)
            return value

    with (
        patch("modules.retrieval.service.embed_query", return_value=[1.0] + [0.0] * 383),
        patch("modules.conversations.tasks.LocalGenerator", Model),
    ):
        generate_answer(str(turn.pk), str(turn.attempt))
    turn.refresh_from_db()


def test_private_idempotent_turn_quota_and_exact_citation(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, reader, collection = library
    indexed(collection, "Request leave five working days ahead.")
    response, data = ask(client, collection)
    assert response.status_code == 202, response.data
    turn = Turn.objects.get(pk=response.data["id"])
    repeated, _ = ask(client, collection, **data)
    assert repeated.data["id"] == response.data["id"] and Turn.objects.count() == 1
    changed, _ = ask(client, collection, **{**data, "question": "Different"})
    assert changed.status_code == 409
    active, _ = ask(client, collection, conversationId=data["conversationId"])
    assert active.status_code == 409
    run(turn)
    assert turn.state == "COMPLETED" and turn.charged_tokens == 60
    assert list(turn.events.values_list("kind", flat=True)) == [
        "accepted",
        "retrieving",
        "generating",
        "validating",
        "answer",
        "completed",
    ]
    source = client.get(f"/api/v1/turns/{turn.pk}/citations/0/0")
    assert source.status_code == 200
    span = source.data["spans"][0]
    assert span["text"][span["start"] : span["end"]] == "five working days"
    count = turn.events.count()
    generate_answer(str(turn.pk), str(turn.attempt))
    assert turn.events.count() == count
    rows, done, unavailable = event_batch(client.session.session_key, turn.pk, turn.sequence)
    assert rows == [] and done and not unavailable
    assert (
        client.get(
            f"/api/v1/turns/{turn.pk}/events", HTTP_LAST_EVENT_ID=f"{uuid.uuid4()}:1"
        ).status_code
        == 400
    )
    client.force_login(reader)
    assert client.get(f"/api/v1/turns/{turn.pk}").status_code == 404
    assert client.get(f"/api/v1/conversations/{turn.conversation_id}/turns").status_code == 404
    assert ask(client, collection)[0].status_code == 403


def test_permission_change_withholds_whole_history_and_replay(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, reader, collection = library
    indexed(collection, "Request leave five working days ahead.")
    membership = Membership.objects.get(user=reader, workspace=collection.workspace)
    membership.role = "MEMBER"
    membership.save()
    collection.access = "RESTRICTED"
    collection.save()
    grant = CollectionGrant.objects.create(
        collection=collection, membership=membership, can_read=True
    )
    client.force_login(reader)
    response, _ = ask(client, collection)
    turn = Turn.objects.get(pk=response.data["id"])
    run(turn)
    assert turn.state == "COMPLETED"
    grant.delete()
    data = client.get(f"/api/v1/turns/{turn.pk}").data
    assert data["unavailable"] and data["answer"] is None and data["question"]
    assert client.get(f"/api/v1/turns/{turn.pk}/citations/0/0").status_code == 404
    assert event_batch(client.session.session_key, turn.pk, 0) == ([], True, True)


def test_cancel_and_revocation_during_generation_never_publish(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, _, collection = library
    indexed(collection, "Request leave five working days ahead.")
    response, _ = ask(client, collection)
    turn = Turn.objects.get(pk=response.data["id"])
    run(turn, during=lambda: cancel_turn(turn.conversation.owner, turn.pk))
    assert turn.state == "CANCELLED" and turn.answer is None and turn.charged_tokens == 100
    response, _ = ask(client, collection)
    turn = Turn.objects.get(pk=response.data["id"])

    def revoke():
        workspace = collection.workspace
        workspace.access_epoch += 1
        workspace.save()

    run(turn, during=revoke)
    assert turn.state == "ACCESS_CHANGED" and turn.answer is None and turn.usage[0]["uncertain"]


def test_recovery_fences_late_worker_and_does_not_repeat_model_calls(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, _, collection = library
    response, _ = ask(client, collection)
    turn = Turn.objects.get(pk=response.data["id"])
    old_attempt = turn.attempt
    Turn.objects.filter(pk=turn.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
    with patch("modules.conversations.tasks.generate_answer.delay") as send:
        recover_answers()
        assert send.call_count == 1
    turn.refresh_from_db()
    assert turn.attempt != old_attempt
    generate_answer(str(turn.pk), str(old_attempt))
    turn.refresh_from_db()
    assert turn.state == "QUEUED"
    Turn.objects.filter(pk=turn.pk).update(
        state="GENERATING",
        lease_until=timezone.now() - timedelta(seconds=1),
        usage=[{"reserved": 100, "input": None, "output": None, "uncertain": True}],
    )
    with patch("modules.conversations.tasks.generate_answer.delay") as send:
        recover_answers()
        send.assert_not_called()
    turn.refresh_from_db()
    assert turn.state == "FAILED" and turn.charged_tokens == 100
    Turn.objects.filter(pk=turn.pk).update(state="CANCELLED", charged_tokens=37000)
    recover_answers()
    turn.refresh_from_db()
    assert turn.state == "CANCELLED" and turn.charged_tokens == 100


def test_empty_scope_no_model_and_mode_and_token_limits(library, settings):
    client, _, collection = library
    assert ask(client, collection)[0].status_code == 503
    settings.RAG_MODE = "LOCAL"
    settings.MAX_DAILY_ANSWER_TOKENS = 1
    assert ask(client, collection)[0].status_code == 429
    assert not Conversation.objects.exists()
    settings.MAX_DAILY_ANSWER_TOKENS = 100000
    response, _ = ask(client, collection, collectionIds=[])
    turn = Turn.objects.get(pk=response.data["id"])
    with patch("modules.conversations.tasks.LocalGenerator") as model:
        generate_answer(str(turn.pk), str(turn.attempt))
        model.assert_not_called()
    turn.refresh_from_db()
    assert turn.state == "COMPLETED" and turn.answer["status"] == "INSUFFICIENT_EVIDENCE"
    assert turn.charged_tokens == 0


def test_concurrent_quota_reservation_accepts_only_one_question(library, settings):
    from rest_framework.exceptions import Throttled

    from pipeline.grounding import MAX_RESERVED_TOKENS

    settings.RAG_MODE = "LOCAL"
    settings.MAX_DAILY_ANSWER_TOKENS = MAX_RESERVED_TOKENS
    _, _, collection = library
    owner = collection.workspace.memberships.get(role="OWNER").user

    def submit(_):
        try:
            data = QuestionInput(
                data={
                    "conversationId": str(uuid.uuid4()),
                    "idempotencyKey": str(uuid.uuid4()),
                    "question": "Library hours?",
                }
            )
            data.is_valid(raise_exception=True)
            create_turn(owner, collection.workspace_id, data.validated_data)
            return "accepted"
        except Throttled:
            return "quota"
        finally:
            close_old_connections()

    with (
        patch("modules.conversations.tasks.generate_answer.delay"),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        assert sorted(pool.map(submit, range(2))) == ["accepted", "quota"]
    assert Turn.objects.count() == 1


def test_uncited_retrieved_dependency_revocation_also_withholds_answer(library, settings):
    settings.RAG_MODE = "LOCAL"
    client, reader, collection = library
    indexed(collection, "Request leave five working days ahead.")
    other = Collection.objects.create(
        workspace=collection.workspace, title="Private notes", access="RESTRICTED"
    )
    indexed(other, "Another source about the building.")
    member = Membership.objects.get(user=reader, workspace=collection.workspace)
    member.role = "MEMBER"
    member.save()
    grant = CollectionGrant.objects.create(collection=other, membership=member, can_read=True)
    client.force_login(reader)
    response, _ = ask(client, collection, collectionIds=[str(collection.pk), str(other.pk)])
    turn = Turn.objects.get(pk=response.data["id"])
    run(turn)
    assert turn.state == "COMPLETED" and len(turn.search_run.metadata["selected"]) == 2
    grant.delete()
    assert client.get(f"/api/v1/turns/{turn.pk}").data["unavailable"]
