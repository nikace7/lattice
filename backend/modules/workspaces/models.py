import uuid

from django.conf import settings
from django.db import models


class DemoInstallation(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    token = models.UUIDField(default=uuid.uuid4, editable=False)
    seed_token = models.UUIDField(default=uuid.uuid4, editable=False)
    database = models.CharField(max_length=63)
    storage_root = models.TextField()
    suite_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=10, default="EMPTY")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="one_demo_installation"),
            models.CheckConstraint(
                condition=models.Q(state__in=["EMPTY", "SEEDING", "READY", "RESETTING"]),
                name="valid_demo_installation_state",
            ),
        ]

    def __str__(self):
        return f"Demo installation: {self.state}"


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    access_epoch = models.PositiveIntegerField(default=1)
    revision = models.PositiveIntegerField(default=1)
    index_profile = models.JSONField(default=dict)
    daily_answers = models.PositiveIntegerField(default=100)
    daily_embedding_tokens = models.PositiveIntegerField(default=500000)
    storage_bytes = models.PositiveBigIntegerField(default=2147483648)
    document_limit = models.PositiveIntegerField(default=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        CURATOR = "CURATOR", "Curator"
        MEMBER = "MEMBER", "Member"
        VIEWER = "VIEWER", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="unique_workspace_member"),
            models.CheckConstraint(
                condition=models.Q(role__in=["OWNER", "CURATOR", "MEMBER", "VIEWER"]),
                name="valid_membership_role",
            ),
        ]

    def __str__(self):
        return f"{self.user_id}: {self.role}"
