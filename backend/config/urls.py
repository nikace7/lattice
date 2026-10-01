from django.urls import path

from config import schema  # noqa: F401 -- registers our session authentication schema
from modules.identity.api import LoginView, LogoutView, RegisterView, SessionView
from modules.workspaces.api import (
    CollectionsView,
    CollectionView,
    GrantsView,
    MembershipsView,
    MembershipView,
    WorkspacesView,
    WorkspaceView,
)

from .health import live, ready

urlpatterns = [
    path("health/live", live),
    path("health/ready", ready),
    path("api/v1/auth/session", SessionView.as_view()),
    path("api/v1/auth/register", RegisterView.as_view()),
    path("api/v1/auth/login", LoginView.as_view()),
    path("api/v1/auth/logout", LogoutView.as_view()),
    path("api/v1/workspaces", WorkspacesView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>", WorkspaceView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/memberships", MembershipsView.as_view()),
    path("api/v1/memberships/<uuid:membership_id>", MembershipView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/collections", CollectionsView.as_view()),
    path("api/v1/collections/<uuid:collection_id>", CollectionView.as_view()),
    path("api/v1/collections/<uuid:collection_id>/grants", GrantsView.as_view()),
]
