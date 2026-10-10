"""Short workspace locks serialize turn mutations and current-access delivery."""

import re
from contextlib import contextmanager
from datetime import timedelta
from functools import partial

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, Throttled, ValidationError

from config.api import Conflict
from modules.documents.models import Chunk, SourceBlock
from modules.retrieval.service import corpus, digest
from modules.workspaces.access import locked_membership, membership_for, readable_collections
from modules.workspaces.models import Workspace
from pipeline.grounding import MAX_RESERVED_TOKENS

from .models import ACTIVE, Conversation, Turn, TurnEvent

LEASE = timedelta(seconds=90)


class AnswerUnavailable(APIException):
    status_code = 503
    default_detail = (
        "Answer generation is unavailable. Ask an operator to prepare the local models."
    )


class TurnStopped(Exception):
    pass


class AccessChanged(TurnStopped):
    pass


def event_cursor(value, turn_id):
    if not value:
        return 0
    prefix, separator, sequence = value.partition(":")
    if (
        prefix != str(turn_id)
        or separator != ":"
        or not sequence.isascii()
        or not sequence.isdigit()
    ):
        raise ValueError("Invalid event cursor.")
    if len(sequence) > 7 or int(sequence) > 1000000:
        raise ValueError("Invalid event cursor.")
    return int(sequence)


def usage_charge(records):
    return sum(
        row["reserved"] if row["uncertain"] else row["input"] + row["output"] for row in records
    )


def verify_hit(hit, blocks):
    covered = set()
    for span, locator in zip(hit["spans"], hit["locations"], strict=True):
        block = blocks.get(span["block_id"])
        if (
            block is None
            or block.locator != locator
            or not 0 <= span["start"] < span["end"] <= len(block.text)
            or not 0 <= span["chunk_start"] < span["chunk_end"] <= len(hit["text"])
            or block.text[span["start"] : span["end"]]
            != hit["text"][span["chunk_start"] : span["chunk_end"]]
        ):
            raise ValueError("Retrieved evidence no longer matches its source.")
        covered.update(range(span["chunk_start"], span["chunk_end"]))
    if not covered or any(i not in covered and c != "\n" for i, c in enumerate(hit["text"])):
        raise ValueError("Retrieved evidence has incomplete source mappings.")


def emit(turn, kind):
    # Caller holds workspace and turn locks; events never contain answer or source text.
    turn.sequence += 1
    TurnEvent.objects.create(turn=turn, sequence=turn.sequence, kind=kind)


@contextmanager
def locked_turn(turn_id):
    workspace_id = get_object_or_404(
        Turn.objects.select_related("conversation"), pk=turn_id
    ).conversation.workspace_id
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '10s'")
        Workspace.objects.select_for_update().get(pk=workspace_id)
        turn = (
            Turn.objects.select_for_update(of=("self",))
            .select_related("conversation__owner")
            .get(pk=turn_id)
        )
        yield turn


def owner_access(turn, user):
    if turn.conversation.owner_id != user.pk:
        raise Http404
    return membership_for(user, turn.conversation.workspace_id)


def current_snapshot(turn):
    try:
        member, scope, indexes = corpus(
            turn.conversation.owner,
            turn.conversation.workspace_id,
            {
                "mode": "HYBRID",
                "details": False,
                "collectionIds": turn.collection_ids,
            },
        )
        if member.role == "VIEWER" or settings.RAG_MODE != "LOCAL":
            raise AccessChanged
        return digest([member.workspace.access_epoch, scope, indexes])
    except (APIException, Http404) as error:
        raise AccessChanged from error


def check_attempt(turn, attempt):
    now = timezone.now()
    if str(turn.attempt) != str(attempt) or turn.state not in ACTIVE or turn.lease_until <= now:
        raise TurnStopped
    if turn.started_at and now - turn.started_at > timedelta(seconds=240):
        raise TurnStopped
    if current_snapshot(turn) != turn.snapshot:
        raise AccessChanged


@transaction.atomic
def create_turn(user, workspace_id, data):
    from .tasks import enqueue

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout = '10s'")
    get_user_model().objects.select_for_update().get(pk=user.pk)
    member = locked_membership(user, workspace_id)
    conversation = Conversation.objects.filter(pk=data["conversationId"]).first()
    if conversation and (
        conversation.owner_id != user.pk or conversation.workspace_id != workspace_id
    ):
        raise Http404
    payload = digest(data)
    if conversation:
        existing = conversation.turns.filter(idempotency_key=data["idempotencyKey"]).first()
        if existing:
            if existing.payload_hash != payload:
                raise Conflict(
                    "This submission key already belongs to a different question or scope."
                )
            return turn_data(existing, user)
    if member.role == "VIEWER":
        raise PermissionDenied("Viewers can read their conversations but cannot generate answers.")
    if settings.RAG_MODE != "LOCAL":
        raise AnswerUnavailable(
            "Answer generation requires LOCAL mode and prepared models. Search remains available."
        )
    now = timezone.now()
    owned = Turn.objects.filter(
        conversation__owner=user, created_at__gte=now - timedelta(minutes=1)
    )
    workspace_turns = Turn.objects.filter(conversation__workspace_id=workspace_id)
    today = workspace_turns.filter(
        created_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    if (
        owned.count() >= 10
        or today.count() >= member.workspace.daily_answers
        or workspace_turns.filter(state__in=ACTIVE).count() >= 2
    ):
        raise Throttled(
            detail="The question limit is reached. Wait for active work to finish or try later."
        )
    charged = today.aggregate(total=Sum("charged_tokens"))["total"] or 0
    if charged + MAX_RESERVED_TOKENS > settings.MAX_DAILY_ANSWER_TOKENS:
        raise Throttled(
            detail="The workspace's daily answer token budget is reserved or exhausted."
        )
    if conversation and conversation.turns.filter(state__in=ACTIVE).exists():
        raise Conflict("This conversation already has an active question.")
    replaces = None
    if data.get("replacesTurnId"):
        replaces = get_object_or_404(Turn, pk=data["replacesTurnId"], conversation=conversation)
    query = {"mode": "HYBRID", "details": False}
    if "collectionIds" in data:
        query["collectionIds"] = data["collectionIds"]
    member, scope, indexes = corpus(user, workspace_id, query)
    if conversation is None:
        conversation = Conversation.objects.create(
            id=data["conversationId"],
            workspace_id=workspace_id,
            owner=user,
            title=data["question"][:80],
        )
    turn = Turn.objects.create(
        conversation=conversation,
        idempotency_key=data["idempotencyKey"],
        payload_hash=payload,
        question=data["question"],
        collection_ids=scope,
        snapshot=digest([member.workspace.access_epoch, scope, indexes]),
        replaces=replaces,
        lease_until=now + LEASE,
        charged_tokens=MAX_RESERVED_TOKENS,
    )
    emit(turn, "accepted")
    turn.save(update_fields=["sequence"])
    transaction.on_commit(partial(enqueue, str(turn.pk), str(turn.attempt)))
    return turn_data(turn, user)


def answer_available(turn, user):
    if turn.answer_purged:
        return False
    if turn.answer is None:
        return True
    citations = [c for b in turn.answer["blocks"] for c in b["citations"]]
    ids = {c["chunkId"] for c in citations}
    if citations:
        if turn.search_run_id is None:
            return False
        # Conservative dependency set: a verifier cannot prove no uncited passage influenced text.
        ids.update(row["chunkId"] for row in turn.search_run.metadata["selected"])
    chunks = {
        str(c.pk): c
        for c in Chunk.objects.filter(
            pk__in=ids,
            index__state="READY",
            index__extraction__source__document__deleted_at__isnull=True,
            index__extraction__source__purge_requested_at__isnull=True,
            index__extraction__source__document__collection__in=readable_collections(user).filter(
                workspace_id=turn.conversation.workspace_id
            ),
        ).select_related("index__extraction__source")
    }
    if set(chunks) != ids:
        return False
    return all(
        str(chunks[c["chunkId"]].index.extraction.source_id) == c["sourceId"]
        and chunks[c["chunkId"]].text[c["chunkStart"] : c["chunkEnd"]] == c["quote"]
        for c in citations
    )


def turn_data(turn, user):
    owner_access(turn, user)
    available = answer_available(turn, user)
    return {
        "id": turn.pk,
        "conversationId": turn.conversation_id,
        "question": turn.question,
        "state": turn.state,
        "sequence": turn.sequence,
        "createdAt": turn.created_at,
        "answer": turn.answer if available else None,
        "unavailable": not available,
        "helpful": turn.helpful if available else None,
        "error": turn.error,
        "collectionIds": turn.collection_ids,
    }


def read_turn(user, turn_id):
    with locked_turn(turn_id) as turn:
        return turn_data(turn, user)


def cancel_turn(user, turn_id):
    with locked_turn(turn_id) as turn:
        owner_access(turn, user)
        if turn.state in ACTIVE:
            if turn.state == "QUEUED":
                turn.charged_tokens = 0
            turn.state = "CANCELLED"
            emit(turn, "cancelled")
            turn.save()
        return turn_data(turn, user)


def record_feedback(user, turn_id, helpful):
    with locked_turn(turn_id) as turn:
        owner_access(turn, user)
        if not answer_available(turn, user):
            raise Http404
        if turn.state != "COMPLETED" or turn.answer is None:
            raise Conflict("Feedback is available after an answer completes.")
        turn.helpful = helpful
        turn.save(update_fields=["helpful"])
        return turn_data(turn, user)


def markdown_literal(text):
    # Source/user text stays literal even when it contains HTML or closing fences.
    fence = "`" * max(3, max((len(run) + 1 for run in re.findall(r"`+", text)), default=0))
    return f"{fence}text\n{text}\n{fence}"


@transaction.atomic
def export_conversation(user, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id, owner=user)
    locked_membership(user, conversation.workspace_id)
    turns = list(
        conversation.turns.select_related("conversation__owner").order_by("created_at", "id")[:101]
    )
    if len(turns) > 100:
        raise ValidationError("Markdown export is limited to conversations with 100 questions.")
    if any(turn.state in ACTIVE for turn in turns):
        raise Conflict("Wait for the active answer to finish before exporting.")
    sections = ["# Lattice conversation", markdown_literal(conversation.title)]
    for number, turn in enumerate(turns, 1):
        data = turn_data(turn, user)
        sections.extend([f"## Question {number}", markdown_literal(turn.question)])
        if data["unavailable"]:
            sections.append("This answer uses sources that are no longer available.")
        elif data["answer"] is None:
            sections.append("No answer was published.")
        else:
            sections.append("Answer status: " + data["answer"]["status"])
            for block_index, block in enumerate(data["answer"]["blocks"]):
                sections.append(markdown_literal(block["text"]))
                for cite_index, _ in enumerate(block["citations"]):
                    cite = citation_data(user, turn.pk, block_index, cite_index)
                    sections.extend(
                        [
                            "### Cited source",
                            markdown_literal(cite["title"]),
                            f"Source version {cite['sourceNumber']} · Source {cite['sourceId']}",
                            markdown_literal(cite["quote"]),
                            "[Open conversation to inspect citation]("
                            f"{settings.APP_ORIGIN.rstrip('/')}/w/{conversation.workspace_id}"
                            f"/c/{conversation.pk})",
                            "Partial extraction." if cite["partial"] else "",
                        ]
                    )
    markdown = "\n\n".join(sections) + "\n"
    if len(markdown.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValidationError("This conversation exceeds the 2 MiB Markdown export limit.")
    return {"filename": f"lattice-{conversation.pk}.md", "markdown": markdown}


def citation_data(user, turn_id, block_index, citation_index):
    with locked_turn(turn_id) as turn:
        owner_access(turn, user)
        if turn.state != "COMPLETED" or not turn.answer or not answer_available(turn, user):
            raise Http404
        try:
            cite = turn.answer["blocks"][block_index]["citations"][citation_index]
        except IndexError as error:
            raise Http404 from error
        chunk = Chunk.objects.select_related("index__extraction__source").get(pk=cite["chunkId"])
        blocks = {
            str(b.pk): b
            for b in SourceBlock.objects.filter(
                extraction_id=chunk.index.extraction_id,
                pk__in=[s["blockId"] for s in cite["spans"]],
            )
        }
        spans = []
        for span in cite["spans"]:
            block = blocks.get(span["blockId"])
            if block is None or not 0 <= span["start"] < span["end"] <= len(block.text):
                raise Http404
            begin, end = max(0, span["start"] - 160), min(len(block.text), span["end"] + 160)
            spans.append(
                {
                    "blockId": block.pk,
                    "text": block.text[begin:end],
                    "start": span["start"] - begin,
                    "end": span["end"] - begin,
                    "location": block.locator,
                }
            )
        source = chunk.index.extraction.source
        return {
            **cite,
            "kind": source.kind,
            "sourceNumber": source.number,
            "olderVersion": source.document.versions.filter(number__gt=source.number).exists(),
            "spans": spans,
        }
