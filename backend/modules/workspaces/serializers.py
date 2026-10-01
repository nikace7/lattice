from rest_framework import serializers

from modules.collections.models import Collection, CollectionGrant

from .access import can_write, membership_for
from .models import Membership, Workspace


class WorkspaceData(serializers.ModelSerializer):
    accessEpoch = serializers.IntegerField(source="access_epoch", read_only=True)
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "revision", "accessEpoch", "role"]
        read_only_fields = ["id", "revision"]

    def get_role(self, obj) -> str:
        return membership_for(self.context["request"].user, obj.pk).role


class RevisionInput(serializers.Serializer):
    expectedRevision = serializers.IntegerField(min_value=1)


class WorkspaceEdit(RevisionInput):
    name = serializers.CharField(max_length=120)


class WorkspaceCreate(serializers.Serializer):
    name = serializers.CharField(max_length=120)


class MembershipData(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "username", "role", "active", "revision"]
        read_only_fields = fields


class MembershipCreate(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=Membership.Role.choices)


class MembershipEdit(RevisionInput):
    role = serializers.ChoiceField(choices=Membership.Role.choices, required=False)
    active = serializers.BooleanField(required=False)


class CollectionData(serializers.ModelSerializer):
    canWrite = serializers.SerializerMethodField()

    class Meta:
        model = Collection
        fields = ["id", "title", "access", "revision", "canWrite"]
        read_only_fields = fields

    def get_canWrite(self, obj) -> bool:
        return can_write(obj, membership_for(self.context["request"].user, obj.workspace_id))


class CollectionCreate(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    access = serializers.ChoiceField(choices=Collection.Access.choices, default="WORKSPACE")


class CollectionEdit(RevisionInput):
    title = serializers.CharField(max_length=160, required=False)
    access = serializers.ChoiceField(choices=Collection.Access.choices, required=False)


class GrantData(serializers.ModelSerializer):
    membershipId = serializers.UUIDField(source="membership_id")
    canRead = serializers.BooleanField(source="can_read")
    canWrite = serializers.BooleanField(source="can_write")

    class Meta:
        model = CollectionGrant
        fields = ["membershipId", "canRead", "canWrite"]


class GrantInput(serializers.Serializer):
    membershipId = serializers.UUIDField()
    canRead = serializers.BooleanField()
    canWrite = serializers.BooleanField()

    def validate(self, attrs):
        if attrs["canWrite"] and not attrs["canRead"]:
            raise serializers.ValidationError("Write access requires read access.")
        return attrs


class GrantsEdit(RevisionInput):
    grants = GrantInput(many=True, max_length=100)
