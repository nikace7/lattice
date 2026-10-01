import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from smtplib import SMTPException
from threading import Barrier
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.utils import timezone
from rest_framework.test import APIClient

from modules.identity.models import ActionToken
from modules.workspaces.models import Membership, Workspace

pytestmark = pytest.mark.django_db
PASSWORD = "reading-room-739!"


@pytest.fixture(autouse=True)
def email_delivery(settings):
    cache.clear()
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


def account(name, email):
    user = get_user_model().objects.create_user(name, email=email, password=PASSWORD)
    client = APIClient()
    client.force_login(user)
    return user, client


def secret():
    return mail.outbox[-1].body.split("#token=")[1].split()[0]


def request_reset(email):
    return APIClient().post("/api/v1/auth/recovery", {"email": email}, format="json")


def reset(token, password="new-reading-room-942!"):
    return APIClient().post(
        "/api/v1/auth/reset", {"token": token, "password": password}, format="json"
    )


def invite(client, workspace, email, **values):
    return client.post(
        f"/api/v1/workspaces/{workspace.pk}/invitations",
        {"email": email, "role": "VIEWER", **values},
        format="json",
    )


@pytest.fixture
def team():
    owner, client = account("owner", "owner@example.test")
    workspace = Workspace.objects.create(name="Reading room")
    Membership.objects.create(user=owner, workspace=workspace, role="OWNER")
    return owner, client, workspace


def test_recovery_queues_every_valid_address_without_account_disclosure():
    account("reader", "reader@example.test")
    with patch("modules.identity.actions.send_recovery.apply_async") as queued:
        known = request_reset("reader@example.test")
        unknown = request_reset("unknown@example.test")
    assert known.status_code == unknown.status_code == 202
    assert known.data == unknown.data
    assert queued.call_count == 2
    assert request_reset("not-an-email").status_code == 400


def test_password_reset_is_hashed_one_use_and_invalidates_all_sessions():
    user, logged_in = account("reader", "reader@example.test")
    assert request_reset(user.email).status_code == 202
    token = secret()
    action = ActionToken.objects.get(user=user)
    assert action.digest == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(action.__dict__)
    assert reset(token, "123").status_code == 400
    assert reset(token).status_code == 200
    assert reset(token).status_code == 400
    assert logged_in.get("/api/v1/workspaces").status_code == 401
    user.refresh_from_db()
    assert user.check_password("new-reading-room-942!")


def test_expired_wrong_purpose_and_inactive_reset_links_fail(team):
    owner, client, workspace = team
    request_reset(owner.email)
    token = secret()
    ActionToken.objects.filter(user=owner).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert reset(token).status_code == 400
    forged = reset("forged")
    assert forged.status_code == 400
    assert "invalid or expired" in forged.data["error"]["message"]
    invite(client, workspace, "guest@example.test")
    assert reset(secret()).status_code == 400
    owner.is_active = False
    owner.save()
    count = len(mail.outbox)
    assert request_reset(owner.email).status_code == 202
    assert len(mail.outbox) == count


def test_invitation_acceptance_requires_matching_account_and_preserves_role(team):
    owner, client, workspace = team
    guest, recipient = account("guest", "guest@example.test")
    outsider, wrong = account("wrong", "wrong@example.test")
    result = invite(client, workspace, "GUEST@example.test")
    assert result.status_code == 201, result.data
    token = secret()
    endpoint = "/api/v1/auth/invitations/accept"
    assert APIClient().post(endpoint, {"token": token}, format="json").status_code == 401
    assert wrong.post(endpoint, {"token": token}, format="json").status_code == 403
    response = recipient.post(endpoint, {"token": token, "role": "OWNER"}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["id"] == str(workspace.pk)
    assert Membership.objects.get(user=guest, workspace=workspace).role == "VIEWER"
    assert recipient.post(endpoint, {"token": token}, format="json").status_code == 400
    assert client.delete(f"/api/v1/invitations/{result.data['id']}").status_code == 409
    workspace.refresh_from_db()
    assert workspace.access_epoch == 2
    assert not Membership.objects.filter(user=outsider, workspace=workspace).exists()


def test_reissue_revoke_and_owner_revocation_invalidate_invitations(team):
    owner, client, workspace = team
    guest, recipient = account("guest", "guest@example.test")
    invite(client, workspace, guest.email)
    first = secret()
    second = invite(client, workspace, guest.email)
    current = secret()
    endpoint = "/api/v1/auth/invitations/accept"
    assert recipient.post(endpoint, {"token": first}, format="json").status_code == 400
    assert client.delete(f"/api/v1/invitations/{second.data['id']}").status_code == 200
    assert recipient.post(endpoint, {"token": current}, format="json").status_code == 400
    invite(client, workspace, guest.email)
    token = secret()
    Membership.objects.filter(user=owner, workspace=workspace).update(role="MEMBER")
    assert recipient.post(endpoint, {"token": token}, format="json").status_code == 400
    assert invite(client, workspace, "other@example.test").status_code == 403


def test_invitation_cannot_reactivate_membership_or_leak_other_workspace(team):
    owner, client, workspace = team
    guest, recipient = account("guest", "guest@example.test")
    invitation = invite(client, workspace, guest.email)
    token = secret()
    Membership.objects.create(user=guest, workspace=workspace, role="MEMBER", active=False)
    assert (
        recipient.post(
            "/api/v1/auth/invitations/accept", {"token": token}, format="json"
        ).status_code
        == 409
    )
    assert recipient.get(f"/api/v1/workspaces/{workspace.pk}/invitations").status_code == 404
    assert recipient.delete(f"/api/v1/invitations/{invitation.data['id']}").status_code == 404
    assert not Membership.objects.get(user=guest, workspace=workspace).active


def test_action_endpoints_enforce_csrf_and_recovery_throttle():
    client = APIClient(enforce_csrf_checks=True)
    assert client.post("/api/v1/auth/recovery", {"email": "a@example.test"}).status_code == 403
    assert client.post("/api/v1/auth/reset", {"token": "forged"}).status_code == 403
    with patch("modules.identity.actions.send_recovery.apply_async"):
        for _ in range(5):
            assert request_reset("a@example.test").status_code == 202
        assert request_reset("a@example.test").status_code == 429


def test_registration_email_is_normalized_and_unique():
    client = APIClient()
    values = {"username": "reader", "email": "Reader@EXAMPLE.test", "password": PASSWORD}
    response = client.post("/api/v1/auth/register", values, format="json")
    assert response.status_code == 201
    assert get_user_model().objects.get(username="reader").email == "reader@example.test"
    values["username"] = "another"
    assert client.post("/api/v1/auth/register", values, format="json").status_code == 400


def test_email_failure_rolls_back_invitation_replacement_and_queue_failure_is_generic(team):
    from kombu.exceptions import OperationalError

    owner, client, workspace = team
    result = invite(client, workspace, "guest@example.test")
    with patch("modules.identity.actions.send_mail", side_effect=SMTPException("unavailable")):
        failed = invite(client, workspace, "guest@example.test")
    assert failed.status_code == 503
    assert ActionToken.objects.get(pk=result.data["id"]).consumed_at is None
    assert ActionToken.objects.filter(purpose="INVITE").count() == 1
    with patch("modules.identity.actions.send_recovery.apply_async", side_effect=OperationalError):
        assert request_reset(owner.email).status_code == 503
        assert request_reset("unknown@example.test").status_code == 503


@pytest.mark.django_db(transaction=True)
def test_concurrent_reset_attempts_consume_a_link_once():
    user, _ = account("reader", "reader@example.test")
    request_reset(user.email)
    token = secret()
    barrier = Barrier(2)

    def attempt(_):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return reset(token).status_code
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [200, 400]
