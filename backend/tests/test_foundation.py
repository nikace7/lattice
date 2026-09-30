import uuid
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection


def test_liveness_has_no_dependency_on_database(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_hides_internal_errors(client, tmp_path, settings):
    settings.STORAGE_ROOT = tmp_path
    with (
        patch("config.health.connection.cursor", side_effect=OSError("private database URL")),
        patch("config.health.Redis.from_url", side_effect=OSError("private Redis URL")),
    ):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": False, "redis": False, "storage": True}
    assert b"private" not in response.content


@pytest.mark.django_db
def test_postgresql_vector_extension_and_uuid_user():
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT '[1,2,3]'::vector <-> '[1,2,3]'::vector")
        assert cursor.fetchone()[0] == 0
    user = get_user_model().objects.create_user(
        username="foundation", password="test-only-password"
    )
    assert isinstance(user.pk, uuid.UUID)
    assert user.check_password("test-only-password")


@pytest.mark.django_db
def test_sessions_use_database_and_httponly_cookie(client):
    user = get_user_model().objects.create_user(username="session", password="test-only-password")
    client.force_login(user)
    assert client.session["_auth_user_id"] == str(user.pk)
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.db"
    assert settings.SESSION_COOKIE_HTTPONLY
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"


@pytest.mark.django_db
def test_readiness_checks_live_dependencies_and_storage(client, tmp_path, settings):
    settings.STORAGE_ROOT = tmp_path
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": True, "redis": True, "storage": True}
    assert response["Cache-Control"] == "no-store"
    settings.STORAGE_ROOT = tmp_path / "missing"
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["storage"] is False
