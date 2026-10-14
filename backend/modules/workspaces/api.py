from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from config.api import Conflict, check_revision, validated
from modules.audit.service import audit
from modules.collections.models import Collection, CollectionGrant

from .access import (
    can_write,
    locked_collection,
    locked_membership,
    membership_for,
    readable_collections,
    require_owner,
)
from .models import Membership, Workspace
from .serializers import (
    CollectionCreate,
    CollectionData,
    CollectionEdit,
    GrantData,
    GrantsEdit,
    MembershipCreate,
    MembershipData,
    MembershipEdit,
    WorkspaceCreate,
    WorkspaceData,
    WorkspaceEdit,
)


class WorkspacesView(generics.ListCreateAPIView):
    serializer_class = WorkspaceData

    def get_queryset(self):
        return Workspace.objects.filter(
            memberships__user=self.request.user, memberships__active=True
        )

    @extend_schema(request=WorkspaceCreate, responses={201: WorkspaceData})
    @transaction.atomic
    def post(self, request):
        data = validated(WorkspaceCreate, request)
        workspace = Workspace.objects.create(**data)
        Membership.objects.create(
            workspace=workspace, user=request.user, role=Membership.Role.OWNER
        )
        audit(workspace, request.user, "workspace.created", workspace)
        return Response(self.get_serializer(workspace).data, status=201)


class WorkspaceView(APIView):
    @extend_schema(responses=WorkspaceData)
    def get(self, request, workspace_id):
        member = membership_for(request.user, workspace_id)
        return Response(WorkspaceData(member.workspace, context={"request": request}).data)

    @extend_schema(request=WorkspaceEdit, responses=WorkspaceData)
    @transaction.atomic
    def patch(self, request, workspace_id):
        member = locked_membership(request.user, workspace_id)
        require_owner(member)
        data = validated(WorkspaceEdit, request)
        workspace = member.workspace
        check_revision(workspace, data)
        workspace.name = data["name"]
        workspace.revision += 1
        workspace.save(update_fields=["name", "revision", "updated_at"])
        audit(workspace, request.user, "workspace.renamed", workspace)
        return Response(WorkspaceData(workspace, context={"request": request}).data)


class MembershipsView(generics.ListCreateAPIView):
    serializer_class = MembershipData

    def get_queryset(self):
        member = membership_for(self.request.user, self.kwargs["workspace_id"])
        require_owner(member)
        return member.workspace.memberships.select_related("user").all()

    @extend_schema(request=MembershipCreate, responses={201: MembershipData})
    @transaction.atomic
    def post(self, request, workspace_id):
        actor = locked_membership(request.user, workspace_id)
        require_owner(actor)
        data = validated(MembershipCreate, request)
        user = get_user_model().objects.filter(username=data["username"], is_active=True).first()
        if user is None:
            raise ValidationError({"username": "An active account with this username is required."})
        try:
            with transaction.atomic():
                member = Membership.objects.create(
                    workspace=actor.workspace, user=user, role=data["role"]
                )
        except IntegrityError as error:
            raise Conflict("This account already has a membership. Edit it instead.") from error
        audit(actor.workspace, request.user, "membership.added", member, access_change=True)
        return Response(MembershipData(member).data, status=201)


class MembershipView(APIView):
    @extend_schema(request=MembershipEdit, responses=MembershipData)
    @transaction.atomic
    def patch(self, request, membership_id):
        target = get_object_or_404(Membership, pk=membership_id)
        actor = locked_membership(request.user, target.workspace_id)
        require_owner(actor)
        target.refresh_from_db()
        data = validated(MembershipEdit, request)
        check_revision(target, data)
        role, active = data.get("role", target.role), data.get("active", target.active)
        if (
            target.active
            and target.role == Membership.Role.OWNER
            and (role != "OWNER" or not active)
        ):
            if (
                not Membership.objects.filter(
                    workspace=actor.workspace, active=True, user__is_active=True, role="OWNER"
                )
                .exclude(pk=target.pk)
                .exists()
            ):
                raise Conflict("Add another active owner before removing the last owner.")
        target.role, target.active = role, active
        target.revision += 1
        target.save(update_fields=["role", "active", "revision", "updated_at"])
        audit(actor.workspace, request.user, "membership.changed", target, access_change=True)
        return Response(MembershipData(target).data)


class CollectionsView(generics.ListCreateAPIView):
    serializer_class = CollectionData

    def get_queryset(self):
        membership_for(self.request.user, self.kwargs["workspace_id"])
        return readable_collections(self.request.user).filter(
            workspace_id=self.kwargs["workspace_id"]
        )

    @extend_schema(request=CollectionCreate, responses={201: CollectionData})
    @transaction.atomic
    def post(self, request, workspace_id):
        member = locked_membership(request.user, workspace_id)
        if member.role not in {Membership.Role.OWNER, Membership.Role.CURATOR}:
            raise PermissionDenied("Only owners and curators can create collections.")
        data = validated(CollectionCreate, request)
        if data["access"] == Collection.Access.RESTRICTED:
            require_owner(member)
        collection = Collection.objects.create(workspace=member.workspace, **data)
        audit(member.workspace, request.user, "collection.created", collection)
        return Response(self.get_serializer(collection).data, status=201)


class CollectionView(APIView):
    @extend_schema(responses=CollectionData)
    def get(self, request, collection_id):
        collection = get_object_or_404(readable_collections(request.user), pk=collection_id)
        return Response(CollectionData(collection, context={"request": request}).data)

    @extend_schema(request=CollectionEdit, responses=CollectionData)
    @transaction.atomic
    def patch(self, request, collection_id):
        member, collection = locked_collection(request.user, collection_id)
        if not can_write(collection, member):
            raise PermissionDenied("You do not have write access to this collection.")
        data = validated(CollectionEdit, request)
        if "access" in data:
            require_owner(member)
        check_revision(collection, data)
        changed_access = data.get("access", collection.access) != collection.access
        collection.title = data.get("title", collection.title)
        collection.access = data.get("access", collection.access)
        collection.revision += 1
        collection.save(update_fields=["title", "access", "revision", "updated_at"])
        audit(member.workspace, request.user, "collection.changed", collection, changed_access)
        return Response(CollectionData(collection, context={"request": request}).data)


class GrantsView(APIView):
    @extend_schema(responses=GrantData(many=True))
    def get(self, request, collection_id):
        collection = get_object_or_404(readable_collections(request.user), pk=collection_id)
        require_owner(membership_for(request.user, collection.workspace_id))
        grants = collection.grants.filter(membership__active=True, membership__user__is_active=True)
        return Response(GrantData(grants, many=True).data)

    @extend_schema(request=GrantsEdit, responses=CollectionData)
    @transaction.atomic
    def put(self, request, collection_id):
        actor, collection = locked_collection(request.user, collection_id)
        require_owner(actor)
        data = validated(GrantsEdit, request)
        check_revision(collection, data)
        ids = [grant["membershipId"] for grant in data["grants"]]
        valid = Membership.objects.filter(
            pk__in=ids, workspace=actor.workspace, active=True, user__is_active=True
        )
        if len(ids) != len(set(ids)) or valid.count() != len(ids):
            raise ValidationError({"grants": "Choose distinct active members of this workspace."})
        collection.grants.all().delete()
        CollectionGrant.objects.bulk_create(
            [
                CollectionGrant(
                    collection=collection,
                    membership_id=grant["membershipId"],
                    can_read=grant["canRead"],
                    can_write=grant["canWrite"],
                )
                for grant in data["grants"]
            ]
        )
        collection.revision += 1
        collection.save(update_fields=["revision", "updated_at"])
        audit(
            actor.workspace,
            request.user,
            "collection.grants_changed",
            collection,
            access_change=True,
        )
        return Response(CollectionData(collection, context={"request": request}).data)
