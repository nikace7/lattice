import uuid

from django.conf import settings
from django.db import models


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    access_epoch = models.PositiveIntegerField(default=1)
    revision = models.PositiveIntegerField(default=1)
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
