from django.urls import path

from config import schema  # noqa: F401 -- registers our session authentication schema
from modules.conversations.api import (
    CancelTurnView,
    CapabilitiesView,
    CitationView,
    ConversationsView,
    ConversationTurnsView,
    QuestionsView,
    TurnEventsView,
    TurnView,
)
from modules.documents.api import (
    AcceptReviewView,
    BlocksView,
    CancelIndexView,
    CancelView,
    DocumentsView,
    DocumentView,
    IndexView,
    OriginalView,
    PreviewView,
    RetryView,
    UploadView,
)
from modules.documents.lifecycle_api import (
    DeleteView,
    PurgeVersionView,
    QuotasView,
    ReindexView,
    ReplaceView,
    VersionsView,
)
from modules.identity.actions import (
    AcceptInvitationView,
    InvitationsView,
    InvitationView,
    RecoveryView,
    ResetView,
)
from modules.identity.api import LoginView, LogoutView, RegisterView, SessionView
from modules.retrieval.api import SearchView
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
    path("api/v1/documents/<uuid:document_id>/replace", ReplaceView.as_view()),
    path("api/v1/documents/<uuid:document_id>/delete", DeleteView.as_view()),
    path("api/v1/documents/<uuid:document_id>/versions", VersionsView.as_view()),
    path(
        "api/v1/documents/<uuid:document_id>/versions/<uuid:source_id>/purge",
        PurgeVersionView.as_view(),
    ),
    path("api/v1/workspaces/<uuid:workspace_id>/reindex", ReindexView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/quotas", QuotasView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/answer-capabilities", CapabilitiesView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/conversations", ConversationsView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/questions", QuestionsView.as_view()),
    path("api/v1/conversations/<uuid:conversation_id>/turns", ConversationTurnsView.as_view()),
    path("api/v1/turns/<uuid:turn_id>", TurnView.as_view()),
    path("api/v1/turns/<uuid:turn_id>/cancel", CancelTurnView.as_view()),
    path("api/v1/turns/<uuid:turn_id>/events", TurnEventsView.as_view()),
    path(
        "api/v1/turns/<uuid:turn_id>/citations/<int:block_index>/<int:citation_index>",
        CitationView.as_view(),
    ),
    path("api/v1/workspaces/<uuid:workspace_id>/search", SearchView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/documents", DocumentsView.as_view()),
    path("api/v1/collections/<uuid:collection_id>/documents", UploadView.as_view()),
    path("api/v1/documents/<uuid:document_id>", DocumentView.as_view()),
    path("api/v1/documents/<uuid:document_id>/retry", RetryView.as_view()),
    path("api/v1/documents/<uuid:document_id>/cancel", CancelView.as_view()),
    path("api/v1/documents/<uuid:document_id>/accept-review", AcceptReviewView.as_view()),
    path("api/v1/documents/<uuid:document_id>/index", IndexView.as_view()),
    path("api/v1/documents/<uuid:document_id>/cancel-index", CancelIndexView.as_view()),
    path("api/v1/sources/<uuid:source_id>/blocks", BlocksView.as_view()),
    path("api/v1/sources/<uuid:source_id>/original", OriginalView.as_view()),
    path("api/v1/sources/<uuid:source_id>/pages/<int:page>", PreviewView.as_view()),
    path("health/live", live),
    path("health/ready", ready),
    path("api/v1/auth/session", SessionView.as_view()),
    path("api/v1/auth/register", RegisterView.as_view()),
    path("api/v1/auth/login", LoginView.as_view()),
    path("api/v1/auth/logout", LogoutView.as_view()),
    path("api/v1/auth/recovery", RecoveryView.as_view()),
    path("api/v1/auth/reset", ResetView.as_view()),
    path("api/v1/auth/invitations/accept", AcceptInvitationView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/invitations", InvitationsView.as_view()),
    path("api/v1/invitations/<uuid:invitation_id>", InvitationView.as_view()),
    path("api/v1/workspaces", WorkspacesView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>", WorkspaceView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/memberships", MembershipsView.as_view()),
    path("api/v1/memberships/<uuid:membership_id>", MembershipView.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/collections", CollectionsView.as_view()),
    path("api/v1/collections/<uuid:collection_id>", CollectionView.as_view()),
    path("api/v1/collections/<uuid:collection_id>/grants", GrantsView.as_view()),
]
