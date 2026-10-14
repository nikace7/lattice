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

from modules.identity.actions import issue_link
from modules.identity.api import UserData
from modules.identity.models import ActionToken


def test_verification_mail_uses_a_distinct_fragment_link_and_only_stores_digest(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    with patch("modules.identity.actions.ActionToken.objects.create") as create:
        issue_link(purpose="VERIFY", email="reader@example.test", lifetime=timedelta(hours=1))
    body = mail.outbox[-1].body
    assert "/account/verify#token=" in body
    token = body.split("#token=")[1].split()[0]
    assert create.call_args.kwargs["digest"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(create.call_args)
    assert "1 hour" in body


def test_session_exposes_verification_without_exposing_email():
    user = get_user_model()(username="reader")
    assert UserData(user).data["emailVerified"] is False
    assert "email" not in UserData(user).data


@pytest.fixture
def account(db, settings):
    cache.clear()
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = get_user_model().objects.create_user(
        "reader", email="reader@example.test", password="reading-room-739!"
    )
    client = APIClient()
    client.force_login(user)
    return user, client


def request_verification(client):
    return client.post("/api/v1/auth/verification", {}, format="json")


def secret():
    return mail.outbox[-1].body.split("#token=")[1].split()[0]


def verify(client, token):
    return client.post("/api/v1/auth/verify", {"token": token}, format="json")


@pytest.mark.django_db
def test_verification_is_authenticated_one_use_and_does_not_gate_existing_login(account):
    user, client = account
    assert client.get("/api/v1/auth/session").data["user"]["emailVerified"] is False
    assert request_verification(APIClient()).status_code == 401
    assert request_verification(client).status_code == 202
    token = secret()
    assert verify(APIClient(), token).status_code == 401
    result = verify(client, token)
    assert result.status_code == 200
    assert result.data["user"]["emailVerified"] is True
    user.refresh_from_db()
    assert user.email_verified is True
    assert verify(client, token).status_code == 400
    count = len(mail.outbox)
    assert request_verification(client).status_code == 200
    assert len(mail.outbox) == count


@pytest.mark.django_db
def test_verification_binds_user_current_email_purpose_and_expiry(account):
    user, client = account
    request_verification(client)
    token = secret()
    other = get_user_model().objects.create_user("other", email="other@example.test")
    outsider = APIClient()
    outsider.force_login(other)
    assert verify(outsider, token).status_code == 400
    assert verify(client, "forged").status_code == 400
    action = ActionToken.objects.get(user=user)
    action.purpose = "RESET"
    action.save(update_fields=["purpose"])
    assert verify(client, token).status_code == 400
    action.purpose = "VERIFY"
    action.expires_at = timezone.now() - timedelta(seconds=1)
    action.save(update_fields=["purpose", "expires_at"])
    assert verify(client, token).status_code == 400
    action.expires_at = timezone.now() + timedelta(hours=1)
    action.save(update_fields=["expires_at"])
    user.email = "changed@example.test"
    user.save(update_fields=["email"])
    assert verify(client, token).status_code == 400
    action.refresh_from_db()
    assert action.consumed_at is None
    user.refresh_from_db()
    assert not user.email_verified


@pytest.mark.django_db
def test_resend_cooldown_reissue_and_delivery_failure_are_atomic(account):
    user, client = account
    assert request_verification(client).status_code == 202
    first = secret()
    assert request_verification(client).status_code == 429
    assert len(mail.outbox) == 1
    ActionToken.objects.filter(user=user).update(created_at=timezone.now() - timedelta(minutes=2))
    with patch("modules.identity.actions.send_mail", side_effect=SMTPException("unavailable")):
        assert request_verification(client).status_code == 503
    assert ActionToken.objects.filter(user=user).count() == 1
    assert ActionToken.objects.get(user=user).consumed_at is None
    assert request_verification(client).status_code == 202
    second = secret()
    assert verify(client, first).status_code == 400
    assert verify(client, second).status_code == 200


@pytest.mark.django_db
def test_verification_requires_csrf_and_registration_does_not_send_mail(account):
    user, _ = account
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert request_verification(client).status_code == 403
    assert verify(client, "forged").status_code == 403
    with patch("modules.identity.actions.send_mail") as send:
        response = APIClient().post(
            "/api/v1/auth/register",
            {"username": "new", "email": "new@example.test", "password": "reading-room-739!"},
            format="json",
        )
    assert response.status_code == 201
    assert response.data["user"]["emailVerified"] is False
    send.assert_not_called()


@pytest.mark.django_db
def test_cleanup_keeps_live_and_recent_actions_and_deletes_only_old_unusable_actions(account):
    from modules.identity.tasks import cleanup_action_tokens

    user, _ = account
    now = timezone.now()
    tokens = []
    for index, (expired_days, consumed_days) in enumerate(
        [(31, None), (None, 31), (1, None), (None, 1), (None, None)]
    ):
        tokens.append(
            ActionToken.objects.create(
                purpose="VERIFY",
                user=user,
                email=user.email,
                digest=str(index) * 64,
                expires_at=now - timedelta(days=expired_days)
                if expired_days
                else now + timedelta(days=1),
                consumed_at=now - timedelta(days=consumed_days) if consumed_days else None,
            )
        )
    assert cleanup_action_tokens() == 2
    assert set(ActionToken.objects.values_list("id", flat=True)) == {t.pk for t in tokens[2:]}
    assert cleanup_action_tokens() == 0


@pytest.mark.django_db
def test_missing_email_is_rejected_without_delivery(account):
    user, client = account
    user.email = ""
    user.save(update_fields=["email"])
    assert request_verification(client).status_code == 400
    assert not mail.outbox


@pytest.mark.django_db(transaction=True)
def test_concurrent_verification_consumes_one_link_once(account):
    user, client = account
    assert request_verification(client).status_code == 202
    token = secret()
    barrier = Barrier(2)

    def attempt(_):
        close_old_connections()
        try:
            signed_in = APIClient()
            signed_in.force_login(user)
            barrier.wait(timeout=10)
            return verify(signed_in, token).status_code
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [200, 400]
