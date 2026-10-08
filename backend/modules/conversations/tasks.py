import logging
import uuid
from contextlib import contextmanager
from functools import partial
from threading import Event, Thread

from celery import shared_task
from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from kombu.exceptions import OperationalError

from modules.documents.models import SourceBlock
from modules.retrieval.models import SearchRun
from modules.retrieval.service import search
from pipeline.generation import GenerationUnavailable, LocalGenerator
from pipeline.grounding import (
    MAX_RESERVED_TOKENS,
    AnswerBudgetExceeded,
    InvalidAnswer,
    grounded_answer,
)

from .models import ACTIVE, Turn
from .service import (
    LEASE,
    AccessChanged,
    TurnStopped,
    check_attempt,
    emit,
    locked_turn,
    usage_charge,
    verify_hit,
)

logger = logging.getLogger(__name__)


def enqueue(turn_id, attempt):
    try:
        generate_answer.delay(turn_id, attempt)
    except OperationalError:
        # The durable queued record remains recoverable; don't risk duplicate provider work.
        logger.warning("Answer queue unavailable turn=%s", turn_id)


def checkpoint(turn_id, attempt, phase=None):
    try:
        with locked_turn(turn_id) as turn:
            check_attempt(turn, attempt)
            turn.lease_until = timezone.now() + LEASE
            if phase and turn.state != phase:
                turn.state = phase
                emit(turn, phase.lower())
            turn.save(update_fields=["state", "sequence", "lease_until"])
    finally:
        if not connection.in_atomic_block:
            close_old_connections()


@contextmanager
def heartbeat(turn_id, attempt):
    stop, lost = Event(), []

    def renew():
        try:
            while not stop.wait(15):
                checkpoint(turn_id, attempt)
        except Exception as error:
            lost.append(error)
        finally:
            close_old_connections()

    thread = Thread(target=renew, daemon=True)
    thread.start()
    try:

        def check():
            if lost:
                raise lost[0]
            checkpoint(turn_id, attempt)

        yield check
    finally:
        stop.set()
        thread.join(timeout=12)


def record_usage(turn_id, attempt, usage, starting=False):
    with locked_turn(turn_id) as turn:
        if str(turn.attempt) != str(attempt):
            raise TurnStopped
        if starting:
            check_attempt(turn, attempt)
        turn.usage = usage
        turn.save(update_fields=["usage"])


def finish(turn_id, attempt, state, error="", answer=None):
    with locked_turn(turn_id) as turn:
        if str(turn.attempt) != str(attempt):
            return
        if state == "COMPLETED":
            check_attempt(turn, attempt)
        # Actual usage is retained even when cancel/recovery already fenced publication.
        turn.charged_tokens = usage_charge(turn.usage)
        if turn.state in ACTIVE:
            turn.state, turn.error, turn.answer = state, error, answer
            if state == "COMPLETED":
                emit(turn, "answer")
            emit(turn, state.lower())
        turn.save()


@shared_task(time_limit=300, soft_time_limit=270)
def generate_answer(turn_id, attempt):
    try:
        with locked_turn(turn_id) as turn:
            if turn.state != "QUEUED" or str(turn.attempt) != str(attempt):
                return
            check_attempt(turn, attempt)
            turn.started_at = timezone.now()
            turn.state = "RETRIEVING"
            emit(turn, "retrieving")
            turn.save()
        with heartbeat(turn_id, attempt) as check:
            result = search(
                turn.conversation.owner,
                turn.conversation.workspace_id,
                {
                    "query": turn.question,
                    "mode": "HYBRID",
                    "details": False,
                    "collectionIds": turn.collection_ids,
                },
            )
            check()
            with locked_turn(turn_id) as turn:
                check_attempt(turn, attempt)
                run = SearchRun.objects.get(
                    pk=result["runId"],
                    actor=turn.conversation.owner,
                    workspace_id=turn.conversation.workspace_id,
                )
                if run.metadata["corpusHash"] != turn.snapshot:
                    raise AccessChanged
                turn.search_run = run
                turn.save(update_fields=["search_run"])
                for hit in result["results"]:
                    blocks = {
                        str(b.pk): b
                        for b in SourceBlock.objects.filter(
                            extraction__indexes__id=hit["indexId"],
                            pk__in=[s["block_id"] for s in hit["spans"]],
                        )
                    }
                    verify_hit(hit, blocks)
            if not result["results"]:
                answer = {
                    "status": "INSUFFICIENT_EVIDENCE",
                    "blocks": [],
                    "repaired": False,
                    "omittedPassages": 0,
                }
            else:
                model = LocalGenerator(
                    settings.MODEL_CACHE_ROOT,
                    settings.OLLAMA_BASE_URL,
                    settings.OLLAMA_MODEL_DIGEST,
                    record_usage=partial(record_usage, turn_id, attempt),
                )
                with locked_turn(turn_id) as turn:
                    check_attempt(turn, attempt)
                    turn.model_digest = model.digest
                    turn.save(update_fields=["model_digest"])
                checkpoint(turn_id, attempt, "GENERATING")
                answer = grounded_answer(
                    turn.question,
                    result["results"],
                    model,
                    check=check,
                    on_validating=lambda: checkpoint(turn_id, attempt, "VALIDATING"),
                )
            check()
            finish(turn_id, attempt, "COMPLETED", answer=answer)
    except AccessChanged:
        finish(
            turn_id,
            attempt,
            "ACCESS_CHANGED",
            "Source access or index state changed. Ask again using the current scope.",
        )
    except TurnStopped:
        finish(
            turn_id, attempt, "FAILED", "The answer job expired. Submit a new question to retry."
        )
    except (GenerationUnavailable, AnswerBudgetExceeded, InvalidAnswer) as error:
        finish(turn_id, attempt, "FAILED", str(error)[:240])
    except Http404:
        return
    except Exception as error:
        logger.error("Answer failed turn=%s error_type=%s", turn_id, type(error).__name__)
        finish(
            turn_id,
            attempt,
            "FAILED",
            "Answer generation failed. Check local models and workers before retrying.",
        )


@shared_task
def recover_answers():
    expired = list(
        Turn.objects.filter(
            Q(state__in=ACTIVE) | Q(state="CANCELLED", charged_tokens=MAX_RESERVED_TOKENS),
            lease_until__lte=timezone.now(),
        )
        .order_by("lease_until")
        .values_list("pk", flat=True)[:100]
    )
    for turn_id in expired:
        with locked_turn(turn_id) as turn:
            if turn.state == "CANCELLED" and turn.lease_until <= timezone.now():
                turn.charged_tokens = usage_charge(turn.usage)
                turn.save(update_fields=["charged_tokens"])
                continue
            if turn.state not in ACTIVE or turn.lease_until > timezone.now():
                continue
            if turn.state == "QUEUED" and turn.recoveries < 3:
                turn.attempt, turn.recoveries = uuid.uuid4(), turn.recoveries + 1
                turn.lease_until = timezone.now() + LEASE
                transaction.on_commit(partial(enqueue, str(turn.pk), str(turn.attempt)))
            else:
                # Never rerun an interrupted model call automatically; its outcome is ambiguous.
                turn.state = "FAILED"
                turn.error = "The answer worker stopped. Submit a new question to retry."
                turn.charged_tokens = usage_charge(turn.usage)
                emit(turn, "failed")
            turn.save()
