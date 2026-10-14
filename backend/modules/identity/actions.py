import hashlib
import secrets
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from kombu.exceptions import OperationalError
from rest_framework import generics, serializers
from rest_framework.exceptions import APIException, PermissionDenied, Throttled, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from config.api import Conflict, validated
from modules.audit.service import audit
from modules.workspaces.access import locked_membership, membership_for, require_owner
from modules.workspaces.models import Membership, Workspace
from modules.workspaces.serializers import WorkspaceData

from .api import SessionData, session_data
from .models import ActionToken
from .tasks import send_recovery

INVALID_LINK = "This link is invalid or expired. Request a new one."


class EmailUnavailable(APIException):
    status_code = 503
    default_detail = "Email is temporarily unavailable. Please try again."


class MessageData(serializers.Serializer):
    message = serializers.CharField()


class EmailInput(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        return value.lower()


class TokenInput(serializers.Serializer):
    token = serializers.CharField(max_length=128, write_only=True)


class ResetInput(TokenInput):
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class InviteInput(EmailInput):
    role = serializers.ChoiceField(choices=Membership.Role.choices, default="MEMBER")


class InvitationData(serializers.ModelSerializer):
    expiresAt = serializers.DateTimeField(source="expires_at")

    class Meta:
        model = ActionToken
        fields = ["id", "email", "role", "expiresAt"]
        read_only_fields = fields


def token_digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_link(*, purpose, email, lifetime, **scope):
    raw = secrets.token_urlsafe(32)
    action = ActionToken.objects.create(
        purpose=purpose,
        digest=token_digest(raw),
        email=email,
        expires_at=timezone.now() + lifetime,
        **scope,
    )
    if purpose == "RESET":
        route = "reset"
        subject = "Reset your Lattice password"
        body = "Use this one-use link to reset your password. It expires in 30 minutes."
    elif purpose == "VERIFY":
        route = "verify"
        subject = "Verify your Lattice email address"
        body = (
            "Sign in to your Lattice account, then use this one-use link to verify your "
            "email address. It expires in 1 hour."
        )
    else:
        route = "invite"
        subject = "Join a Lattice workspace"
        body = (
            "You have been invited to a workspace on Lattice. Sign in or create an account "
            "with this email address, then accept the invitation. This link expires in 2 days."
        )
    link = f"{settings.APP_ORIGIN.rstrip('/')}/account/{route}#token={raw}"
    # ponytail: SMTP holds the transaction during bounded network calls; use an
    # outbox if invitation volume needs delivery outside the workspace lock.
    try:
        send_mail(
            subject,
            f"{body}\n\n{link}\n\nIf unexpected, ignore this email.",
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
    except (SMTPException, OSError) as error:
        raise EmailUnavailable() from error
    return action


def valid_token(raw, purpose):
    token = ActionToken.objects.filter(
        digest=token_digest(raw),
        purpose=purpose,
        consumed_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()
    if token is None:
        raise ValidationError(INVALID_LINK)
    return token


class VerificationRequestView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=None, responses={200: MessageData, 202: MessageData})
    @transaction.atomic
    def post(self, request):
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        if not user.is_active or not user.email:
            raise ValidationError("This account has no active email address to verify.")
        if user.email_verified:
            return Response({"message": "Your email address is already verified."})
        now = timezone.now()
        latest = (
            ActionToken.objects.filter(
                user=user, purpose="VERIFY", created_at__gt=now - timedelta(minutes=1)
            )
            .order_by("-created_at")
            .first()
        )
        if latest is not None:
            raise Throttled(wait=60 - (now - latest.created_at).total_seconds())
        ActionToken.objects.filter(user=user, purpose="VERIFY", consumed_at__isnull=True).update(
            consumed_at=now
        )
        issue_link(
            purpose="VERIFY", email=user.email.lower(), user=user, lifetime=timedelta(hours=1)
        )
        return Response({"message": "A verification link has been sent to your email."}, status=202)


class VerifyEmailView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=TokenInput, responses=SessionData)
    @transaction.atomic
    def post(self, request):
        data = validated(TokenInput, request)
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        token = valid_token(data["token"], "VERIFY")
        if not user.is_active or token.user_id != user.pk or user.email.lower() != token.email:
            raise ValidationError(INVALID_LINK)
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        ActionToken.objects.filter(user=user, purpose="VERIFY", consumed_at__isnull=True).update(
            consumed_at=timezone.now()
        )
        request.user.email_verified = True
        return Response(session_data(request))


class RecoveryView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "recovery"

    @extend_schema(request=EmailInput, responses={202: MessageData})
    def post(self, request):
        data = validated(EmailInput, request)
        # Queue for every valid address: account lookup and SMTP run off the request path.
        try:
            send_recovery.apply_async(args=[data["email"]], argsrepr="(<redacted>,)")
        except OperationalError as error:
            raise EmailUnavailable() from error
        return Response(
            {"message": "If an active account uses this email, a recovery link will arrive soon."},
            status=202,
        )


class ResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=ResetInput, responses=MessageData)
    @transaction.atomic
    def post(self, request):
        data = validated(ResetInput, request)
        candidate = valid_token(data["token"], "RESET")
        user = get_user_model().objects.select_for_update().get(pk=candidate.user_id)
        token = valid_token(data["token"], "RESET")
        if not user.is_active or user.email.lower() != token.email:
            raise ValidationError(INVALID_LINK)
        try:
            validate_password(data["password"], user)
        except DjangoValidationError as error:
            raise ValidationError({"password": error.messages}) from error
        user.set_password(data["password"])
        user.save(update_fields=["password"])
        ActionToken.objects.filter(user=user, purpose="RESET", consumed_at__isnull=True).update(
            consumed_at=timezone.now()
        )
        # Django invalidates every old session via its stored authentication hash.
        logout(request)
        return Response({"message": "Password changed. Sign in with your new password."})


class InvitationsView(generics.ListCreateAPIView):
    serializer_class = InvitationData
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitations"

    def get_queryset(self):
        require_owner(membership_for(self.request.user, self.kwargs["workspace_id"]))
        return ActionToken.objects.filter(
            workspace_id=self.kwargs["workspace_id"],
            purpose="INVITE",
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        )

    @extend_schema(request=InviteInput, responses={201: InvitationData})
    @transaction.atomic
    def post(self, request, workspace_id):
        actor = locked_membership(request.user, workspace_id)
        require_owner(actor)
        data = validated(InviteInput, request)
        if actor.workspace.memberships.filter(user__email__iexact=data["email"]).exists():
            raise Conflict("This account already has a membership. Edit it instead.")
        ActionToken.objects.filter(
            workspace=actor.workspace,
            email=data["email"],
            purpose="INVITE",
            consumed_at__isnull=True,
        ).update(consumed_at=timezone.now())
        invitation = issue_link(
            purpose="INVITE",
            email=data["email"],
            lifetime=timedelta(days=2),
            workspace=actor.workspace,
            invited_by=request.user,
            role=data["role"],
        )
        audit(actor.workspace, request.user, "invitation.sent", invitation)
        return Response(InvitationData(invitation).data, status=201)


class InvitationView(APIView):
    @extend_schema(responses=MessageData)
    @transaction.atomic
    def delete(self, request, invitation_id):
        invitation = get_object_or_404(ActionToken, pk=invitation_id, purpose="INVITE")
        actor = locked_membership(request.user, invitation.workspace_id)
        require_owner(actor)
        invitation.refresh_from_db()
        if invitation.consumed_at is not None:
            raise Conflict(
                "This invitation was already used or revoked. Check the membership list."
            )
        invitation.consumed_at = timezone.now()
        invitation.save(update_fields=["consumed_at"])
        audit(actor.workspace, request.user, "invitation.revoked", invitation)
        return Response({"message": "Invitation revoked."})


class AcceptInvitationView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=TokenInput, responses=WorkspaceData)
    @transaction.atomic
    def post(self, request):
        data = validated(TokenInput, request)
        candidate = valid_token(data["token"], "INVITE")
        workspace = Workspace.objects.select_for_update().get(pk=candidate.workspace_id)
        token = valid_token(data["token"], "INVITE")
        if not workspace.memberships.filter(
            user=token.invited_by, active=True, user__is_active=True, role="OWNER"
        ).exists():
            raise ValidationError(INVALID_LINK)
        if request.user.email.lower() != token.email:
            raise PermissionDenied("Sign in with the account that uses the invited email address.")
        if workspace.memberships.filter(user=request.user).exists():
            raise Conflict("You already have a membership. Ask an owner to manage it.")
        member = Membership.objects.create(workspace=workspace, user=request.user, role=token.role)
        token.consumed_at = timezone.now()
        token.save(update_fields=["consumed_at"])
        audit(workspace, request.user, "invitation.accepted", member, access_change=True)
        return Response(WorkspaceData(workspace, context={"request": request}).data)
