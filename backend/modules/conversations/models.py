import uuid

from django.conf import settings
from django.db import models

ACTIVE = ["QUEUED", "RETRIEVING", "GENERATING", "VALIDATING"]
STATES = ACTIVE + ["COMPLETED", "FAILED", "CANCELLED", "ACCESS_CHANGED"]


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.pk)


class Turn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, related_name="turns", on_delete=models.CASCADE)
    idempotency_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    question = models.CharField(max_length=4000)
    collection_ids = models.JSONField(default=list)
    snapshot = models.CharField(max_length=64)
    search_run = models.ForeignKey("retrieval.SearchRun", null=True, on_delete=models.SET_NULL)
    replaces = models.ForeignKey("self", null=True, on_delete=models.SET_NULL)
    state = models.CharField(
        max_length=16, choices=[(s, s.title()) for s in STATES], default="QUEUED"
    )
    attempt = models.UUIDField(default=uuid.uuid4)
    sequence = models.PositiveIntegerField(default=0)
    recoveries = models.PositiveSmallIntegerField(default=0)
    lease_until = models.DateTimeField()
    started_at = models.DateTimeField(null=True)
    model_digest = models.CharField(max_length=64, blank=True)
    answer = models.JSONField(null=True)
    answer_purged = models.BooleanField(default=False)
    error = models.CharField(max_length=240, blank=True)
    usage = models.JSONField(default=list)
    charged_tokens = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "idempotency_key"], name="unique_turn_intent"
            ),
            models.UniqueConstraint(
                fields=["conversation"],
                condition=models.Q(state__in=ACTIVE),
                name="one_active_conversation_turn",
            ),
            models.CheckConstraint(condition=models.Q(state__in=STATES), name="valid_turn_state"),
        ]

    def __str__(self):
        return str(self.pk)


class TurnEvent(models.Model):
    turn = models.ForeignKey(Turn, related_name="events", on_delete=models.CASCADE)
    sequence = models.PositiveIntegerField()
    kind = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["turn", "sequence"], name="unique_turn_event")
        ]

    def __str__(self):
        return f"{self.turn_id}:{self.sequence}"
