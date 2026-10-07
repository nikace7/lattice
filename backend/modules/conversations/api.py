import asyncio
import json
import time

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user
from django.contrib.sessions.backends.db import SessionStore
from django.db import IntegrityError, OperationalError, close_old_connections, transaction
from django.http import Http404, HttpRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import generics
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from config.api import Conflict, Pages
from modules.workspaces.access import locked_membership, membership_for
from modules.workspaces.api import validated

from .models import ACTIVE, Conversation
from .serializers import (
    AnswerCapabilityData,
    ConversationData,
    QuestionInput,
    SourceQuoteData,
    TurnData,
)
from .service import (
    AnswerUnavailable,
    answer_available,
    cancel_turn,
    citation_data,
    create_turn,
    event_cursor,
    locked_turn,
    owner_access,
    read_turn,
    turn_data,
)


class RecentPages(Pages):
    ordering = ("-created_at", "-id")


class SafeErrors:
    def handle_exception(self, error):
        if isinstance(error, OperationalError):
            error = AnswerUnavailable("Conversation storage is busy or unavailable. Please retry.")
        elif isinstance(error, IntegrityError):
            error = Conflict("This conversation changed. Refresh and retry your submission.")
        return super().handle_exception(error)


class CapabilitiesView(SafeErrors, APIView):
    @extend_schema(responses=AnswerCapabilityData)
    def get(self, request, workspace_id):
        member = membership_for(request.user, workspace_id)
        enabled = settings.RAG_MODE == "LOCAL" and member.role != "VIEWER"
        return Response(
            {
                "enabled": enabled,
                "message": "Each question retrieves fresh sources. Review the cited evidence."
                if enabled
                else (
                    "Answer generation is unavailable in this mode or role. "
                    "You can still search sources and read your own conversations."
                ),
            }
        )


class ConversationsView(SafeErrors, generics.ListAPIView):
    serializer_class = ConversationData
    pagination_class = RecentPages

    def get_queryset(self):
        membership_for(self.request.user, self.kwargs["workspace_id"])
        return Conversation.objects.filter(
            workspace_id=self.kwargs["workspace_id"], owner=self.request.user
        )


class ConversationTurnsView(SafeErrors, generics.ListAPIView):
    serializer_class = TurnData
    pagination_class = RecentPages

    @transaction.atomic
    def get(self, request, conversation_id):
        conversation = get_object_or_404(Conversation, pk=conversation_id, owner=request.user)
        locked_membership(request.user, conversation.workspace_id)
        page = self.paginate_queryset(
            conversation.turns.select_related("conversation__owner").all()
        )
        return self.get_paginated_response(
            TurnData([turn_data(t, request.user) for t in page], many=True).data
        )


class QuestionsView(SafeErrors, APIView):
    @extend_schema(request=QuestionInput, responses={202: TurnData})
    def post(self, request, workspace_id):
        return Response(
            TurnData(
                create_turn(request.user, workspace_id, validated(QuestionInput, request))
            ).data,
            status=202,
        )


class TurnView(SafeErrors, APIView):
    @extend_schema(responses=TurnData)
    def get(self, request, turn_id):
        return Response(TurnData(read_turn(request.user, turn_id)).data)


class CancelTurnView(SafeErrors, APIView):
    @extend_schema(request=None, responses=TurnData)
    def post(self, request, turn_id):
        return Response(TurnData(cancel_turn(request.user, turn_id)).data)


class CitationView(SafeErrors, APIView):
    @extend_schema(responses=SourceQuoteData)
    def get(self, request, turn_id, block_index, citation_index):
        return Response(
            SourceQuoteData(citation_data(request.user, turn_id, block_index, citation_index)).data
        )


def event_batch(session_key, turn_id, after):
    try:
        request = HttpRequest()
        request.session = SessionStore(session_key=session_key)
        user = get_user(request)
        if not user.is_authenticated:
            raise Http404
        with locked_turn(turn_id) as turn:
            owner_access(turn, user)
            if not answer_available(turn, user):
                return [], True, True
            rows = list(
                turn.events.filter(sequence__gt=after)
                .order_by("sequence")
                .values("sequence", "kind", "created_at")[:100]
            )
            return rows, turn.state not in ACTIVE, False
    finally:
        close_old_connections()


async def stream_events(session_key, turn_id, after):
    deadline, heartbeat = time.monotonic() + 55, time.monotonic()
    yield "retry: 2000\n\n"
    while time.monotonic() < deadline:
        try:
            rows, done, unavailable = await sync_to_async(event_batch, thread_sensitive=False)(
                session_key, turn_id, after
            )
        except (Http404, APIException):
            yield "event: access_changed\ndata: {}\n\n"
            return
        if unavailable:
            yield "event: access_changed\ndata: {}\n\n"
            return
        for row in rows:
            after = row["sequence"]
            payload = json.dumps(
                {
                    "turnId": str(turn_id),
                    "sequence": after,
                    "phase": row["kind"],
                    "createdAt": row["created_at"].isoformat(),
                }
            )
            yield f"id: {turn_id}:{after}\nevent: progress\ndata: {payload}\n\n"
        if done:
            yield "event: settled\ndata: {}\n\n"
            return
        if time.monotonic() - heartbeat >= 15:
            yield ": heartbeat\n\n"
            heartbeat = time.monotonic()
        await asyncio.sleep(1)


class TurnEventsView(SafeErrors, APIView):
    @extend_schema(
        parameters=[OpenApiParameter("Last-Event-ID", str, OpenApiParameter.HEADER)],
        responses={(200, "text/event-stream"): OpenApiTypes.STR},
    )
    def get(self, request, turn_id):
        read_turn(request.user, turn_id)
        try:
            after = event_cursor(request.headers.get("Last-Event-ID", ""), turn_id)
        except ValueError as error:
            raise ValidationError(str(error)) from error
        response = StreamingHttpResponse(
            stream_events(request.session.session_key, turn_id, after),
            content_type="text/event-stream",
        )
        response["X-Accel-Buffering"] = "no"
        response["Cache-Control"] = "no-store"
        return response
