from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from modules.collections.models import Collection

from .models import Membership, Workspace


def membership_for(user, workspace_id):
    return get_object_or_404(
        Membership.objects.select_related("workspace"),
        workspace_id=workspace_id,
        user=user,
        active=True,
        user__is_active=True,
    )


def locked_membership(user, workspace_id):
    # Serialize access changes per workspace; caller must be inside transaction.atomic.
    get_object_or_404(Workspace.objects.select_for_update(), pk=workspace_id)
    return membership_for(user, workspace_id)


def require_owner(membership):
    if membership.role != Membership.Role.OWNER:
        raise PermissionDenied("Only workspace owners can manage access.")


def readable_collections(user):
    if not user.is_authenticated or not user.is_active:
        return Collection.objects.none()
    return Collection.objects.filter(
        Q(workspace__memberships__user=user, workspace__memberships__active=True),
        Q(workspace__memberships__role=Membership.Role.OWNER)
        | Q(access=Collection.Access.WORKSPACE)
        | Q(
            grants__membership__user=user,
            grants__membership__active=True,
            grants__membership__workspace_id=F("workspace_id"),
            grants__can_read=True,
        ),
    ).distinct()


def can_write(collection, membership):
    if not membership.active or collection.workspace_id != membership.workspace_id:
        return False
    if membership.role == Membership.Role.OWNER:
        return True
    return membership.role == Membership.Role.CURATOR and (
        collection.access == Collection.Access.WORKSPACE
        or collection.grants.filter(membership=membership, can_read=True, can_write=True).exists()
    )


def locked_collection(user, collection_id):
    workspace_id = get_object_or_404(Collection, pk=collection_id).workspace_id
    member = locked_membership(user, workspace_id)
    return member, get_object_or_404(readable_collections(user), pk=collection_id)
