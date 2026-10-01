import uuid

from django.core.exceptions import ValidationError
from django.db import models

from modules.workspaces.models import Membership, Workspace


class Collection(models.Model):
    class Access(models.TextChoices):
        WORKSPACE = "WORKSPACE", "Everyone in this workspace"
        RESTRICTED = "RESTRICTED", "Selected people"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="collections")
    title = models.CharField(max_length=160)
    access = models.CharField(max_length=10, choices=Access.choices, default=Access.WORKSPACE)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(access__in=["WORKSPACE", "RESTRICTED"]),
                name="valid_collection_access",
            )
        ]

    def __str__(self):
        return self.title


class CollectionGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="grants")
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="grants")
    can_read = models.BooleanField(default=True)
    can_write = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "membership"], name="unique_collection_grant"
            ),
            models.CheckConstraint(
                condition=models.Q(can_write=False) | models.Q(can_read=True),
                name="write_grant_requires_read",
            ),
        ]

    def __str__(self):
        return f"{self.collection_id}: {self.membership_id}"

    def clean(self):
        if self.collection.workspace_id != self.membership.workspace_id:
            raise ValidationError("Collection and membership must belong to the same workspace.")
