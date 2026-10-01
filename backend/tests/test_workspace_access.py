import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import close_old_connections, connections
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def users():
    cache.clear()
    return {
        name: get_user_model().objects.create_user(name, password="test-only-secret-839!")
        for name in ["owner", "curator", "member", "viewer", "outsider"]
    }


def as_user(user):
    client = APIClient()
    client.force_login(user)
    return client


def create_workspace(client, name="Library"):
    response = client.post("/api/v1/workspaces", {"name": name}, format="json")
    assert response.status_code == 201, response.data
    return response.data


def add_member(client, workspace, username, role):
    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/memberships",
        {"username": username, "role": role},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def create_collection(client, workspace, access="WORKSPACE"):
    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/collections",
        {"title": "Same title", "access": access},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def test_bootstrap_and_tenant_isolation(users):
    owner, outsider = as_user(users["owner"]), as_user(users["outsider"])
    first, second = create_workspace(owner), create_workspace(outsider)
    collection = create_collection(owner, first)
    create_collection(outsider, second)
    assert first["role"] == "OWNER"
    assert [w["id"] for w in outsider.get("/api/v1/workspaces").data["results"]] == [second["id"]]
    assert outsider.get(f"/api/v1/workspaces/{first['id']}").status_code == 404
    assert outsider.get(f"/api/v1/workspaces/{first['id']}/collections").status_code == 404
    assert outsider.get(f"/api/v1/collections/{collection['id']}").status_code == 404
    assert APIClient().get("/api/v1/workspaces").status_code == 401


def test_restricted_grants_role_ceiling_and_revocation(users):
    owner = as_user(users["owner"])
    workspace = create_workspace(owner)
    collection = create_collection(owner, workspace, "RESTRICTED")
    memberships = {
        role: add_member(owner, workspace, role.lower(), role)
        for role in ["CURATOR", "MEMBER", "VIEWER"]
    }
    path = f"/api/v1/collections/{collection['id']}"
    for role in memberships:
        reader = as_user(users[role.lower()])
        assert reader.get(path).status_code == 404
        assert reader.get(f"/api/v1/workspaces/{workspace['id']}/collections").data["results"] == []
    response = owner.put(
        path + "/grants",
        {
            "expectedRevision": 1,
            "grants": [
                {"membershipId": m["id"], "canRead": True, "canWrite": True}
                for m in memberships.values()
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    for role in memberships:
        reader = as_user(users[role.lower()])
        data = reader.get(path).data
        assert data["canWrite"] is (role == "CURATOR")
        if role != "CURATOR":
            assert (
                reader.patch(
                    path, {"title": "forged", "expectedRevision": 2}, format="json"
                ).status_code
                == 403
            )
    assert (
        as_user(users["curator"])
        .put(path + "/grants", {"expectedRevision": 2, "grants": []}, format="json")
        .status_code
        == 403
    )
    revoked = owner.put(path + "/grants", {"expectedRevision": 2, "grants": []}, format="json")
    assert revoked.status_code == 200
    assert as_user(users["member"]).get(path).status_code == 404
    assert owner.get(f"/api/v1/workspaces/{workspace['id']}").data["accessEpoch"] == 6


def test_cross_workspace_grants_are_rejected_atomically(users):
    owner = as_user(users["owner"])
    first, second = create_workspace(owner), create_workspace(owner)
    collection = create_collection(owner, first, "RESTRICTED")
    foreign = add_member(owner, second, "member", "MEMBER")
    path = f"/api/v1/collections/{collection['id']}/grants"
    response = owner.put(
        path,
        {
            "expectedRevision": 1,
            "grants": [{"membershipId": foreign["id"], "canRead": True, "canWrite": False}],
        },
        format="json",
    )
    assert response.status_code == 400
    assert owner.get(path).data == []
    assert owner.get(f"/api/v1/workspaces/{first['id']}").data["accessEpoch"] == 1


def test_membership_changes_protect_last_owner_and_detect_stale_writes(users):
    owner = as_user(users["owner"])
    workspace = create_workspace(owner)
    memberships_url = f"/api/v1/workspaces/{workspace['id']}/memberships"
    own = owner.get(memberships_url).data["results"][0]
    own_url = f"/api/v1/memberships/{own['id']}"
    assert (
        owner.patch(own_url, {"role": "MEMBER", "expectedRevision": 1}, format="json").status_code
        == 409
    )
    assert (
        owner.patch(own_url, {"active": False, "expectedRevision": 1}, format="json").status_code
        == 409
    )
    member = add_member(owner, workspace, "member", "OWNER")
    assert (
        owner.patch(own_url, {"role": "MEMBER", "expectedRevision": 99}, format="json").status_code
        == 409
    )
    assert (
        owner.patch(own_url, {"role": "MEMBER", "expectedRevision": 1}, format="json").status_code
        == 200
    )
    assert owner.get(memberships_url).status_code == 403
    other = as_user(users["member"])
    response = other.patch(own_url, {"active": False, "expectedRevision": 2}, format="json")
    assert response.status_code == 200
    assert owner.get(f"/api/v1/workspaces/{workspace['id']}").status_code == 404
    assert member["role"] == "OWNER"


def test_curator_can_create_shared_collection_but_not_change_access(users):
    owner = as_user(users["owner"])
    workspace = create_workspace(owner)
    add_member(owner, workspace, "curator", "CURATOR")
    curator = as_user(users["curator"])
    collection = create_collection(curator, workspace)
    path = f"/api/v1/collections/{collection['id']}"
    assert (
        curator.patch(path, {"title": "Renamed", "expectedRevision": 1}, format="json").status_code
        == 200
    )
    assert (
        curator.patch(
            path, {"access": "RESTRICTED", "expectedRevision": 2}, format="json"
        ).status_code
        == 403
    )
    assert (
        curator.patch(path, {"title": "stale", "expectedRevision": 1}, format="json").status_code
        == 409
    )
    assert curator.get(f"/api/v1/collections/{uuid.uuid4()}").status_code == 404


def test_login_registration_csrf_origin_and_session_rotation():
    cache.clear()
    client = APIClient(enforce_csrf_checks=True)
    credentials = {
        "username": "newreader",
        "email": "newreader@example.test",
        "password": "coffee-library-739!",
    }
    assert client.post("/api/v1/auth/register", credentials, format="json").status_code == 403
    csrf = client.get("/api/v1/auth/session").data["csrfToken"]
    assert (
        client.post(
            "/api/v1/auth/register",
            credentials,
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_ORIGIN="https://hostile.invalid",
        ).status_code
        == 403
    )
    response = client.post(
        "/api/v1/auth/register", credentials, format="json", HTTP_X_CSRFTOKEN=csrf
    )
    assert response.status_code == 201, response.data
    assert response.data["user"]["username"] == "newreader"
    assert response.data["csrfToken"] != csrf
    csrf = response.data["csrfToken"]
    session_key = client.cookies["sessionid"].value
    assert (
        client.post("/api/v1/auth/logout", {}, format="json", HTTP_X_CSRFTOKEN=csrf).status_code
        == 200
    )
    assert client.get("/api/v1/workspaces").status_code == 401
    response = client.post("/api/v1/auth/login", credentials, format="json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 200
    assert client.cookies["sessionid"].value != session_key
    assert client.cookies["sessionid"]["httponly"]
    assert client.get("/api/v1/auth/session")["Cache-Control"] == "no-store"


def test_auth_errors_are_generic_and_password_rules_apply(users):
    client = APIClient()
    first = client.post(
        "/api/v1/auth/login", {"username": "owner", "password": "wrong"}, format="json"
    )
    second = client.post(
        "/api/v1/auth/login", {"username": "unknown", "password": "wrong"}, format="json"
    )
    assert first.status_code == second.status_code == 401
    assert first.data["error"]["message"] == second.data["error"]["message"]
    assert "requestId" in first.data["error"]
    assert (
        client.post(
            "/api/v1/auth/register",
            {"username": "badpass", "email": "badpass@example.test", "password": "123"},
            format="json",
        ).status_code
        == 400
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_owner_demotions_leave_one_active_owner(users):
    from modules.workspaces.models import Membership

    owner, other = as_user(users["owner"]), as_user(users["member"])
    workspace = create_workspace(owner)
    add_member(owner, workspace, "member", "OWNER")
    entries = list(Membership.objects.filter(workspace_id=workspace["id"]).select_related("user"))
    clients = {users["owner"].pk: owner, users["member"].pk: other}
    barrier = Barrier(2)

    def demote(entry):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return (
                clients[entry.user_id]
                .patch(
                    f"/api/v1/memberships/{entry.pk}",
                    {"role": "MEMBER", "expectedRevision": 1},
                    format="json",
                )
                .status_code
            )
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(demote, entries)) == [200, 409]
    assert (
        Membership.objects.filter(workspace_id=workspace["id"], role="OWNER", active=True).count()
        == 1
    )


def test_rate_limit_and_scoped_cursor_pagination(users, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    owner = as_user(users["owner"])
    workspace = create_workspace(owner)
    add_member(owner, workspace, "member", "MEMBER")
    create_collection(owner, workspace, "RESTRICTED")
    readable = [create_collection(owner, workspace) for _ in range(2)]
    reader = as_user(users["member"])
    first = reader.get(f"/api/v1/workspaces/{workspace['id']}/collections?pageSize=1").data
    second = reader.get(first["next"]).data
    assert {first["results"][0]["id"], second["results"][0]["id"]} == {
        item["id"] for item in readable
    }
    assert second["next"] is None
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"auth": "2/minute"})
    anonymous = APIClient()
    assert anonymous.post("/api/v1/auth/login", {}, format="json").status_code == 400
    assert anonymous.post("/api/v1/auth/login", {}, format="json").status_code == 400
    assert anonymous.post("/api/v1/auth/login", {}, format="json").status_code == 429
