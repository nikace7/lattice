import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"), condition=~models.Q(email=""), name="unique_account_email"
            )
        ]


class ActionToken(models.Model):
    class Purpose(models.TextChoices):
        RESET = "RESET", "Password reset"
        INVITE = "INVITE", "Workspace invitation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purpose = models.CharField(max_length=6, choices=Purpose.choices)
    digest = models.CharField(max_length=64, unique=True)
    email = models.EmailField()
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE, related_name="actions")
    workspace = models.ForeignKey("workspaces.Workspace", null=True, on_delete=models.CASCADE)
    invited_by = models.ForeignKey(
        User, null=True, on_delete=models.CASCADE, related_name="invites"
    )
    role = models.CharField(max_length=10, blank=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        purpose="RESET",
                        user__isnull=False,
                        workspace__isnull=True,
                        invited_by__isnull=True,
                        role="",
                    )
                    | models.Q(
                        purpose="INVITE",
                        user__isnull=True,
                        workspace__isnull=False,
                        invited_by__isnull=False,
                        role__in=["OWNER", "CURATOR", "MEMBER", "VIEWER"],
                    )
                ),
                name="valid_action_token_scope",
            )
        ]

    def __str__(self):
        return f"{self.purpose}: {self.pk}"
