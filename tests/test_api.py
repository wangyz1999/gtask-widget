import time
from datetime import date

import pytest

from gtask_widget import auth as auth_mod
from gtask_widget.api import OfflineError, TasksClient
from gtask_widget.auth import Auth, ClientConfig, Credentials, ReauthRequired, TokenStore

from .fake_google import FakeGoogle


@pytest.fixture
def google(monkeypatch, tmp_path):
    g = FakeGoogle()
    monkeypatch.setattr(auth_mod, "TOKEN_URI", g.url + "/token")
    monkeypatch.setattr(auth_mod, "REVOKE_URI", g.url + "/revoke")
    monkeypatch.setattr(TasksClient, "base_url", g.url)
    yield g
    g.close()


def make_client(tmp_path, access="access-1", expiry=None):
    store = TokenStore(tmp_path / "token.bin")
    store.save(Credentials(access, "refresh-1", expiry or time.time() + 3600))
    auth = Auth(ClientConfig("cid", "secret"), store)
    return TasksClient(auth), auth


def test_lists_and_paginated_tasks(google, tmp_path):
    client, _ = make_client(tmp_path)
    lists = client.list_tasklists()
    assert [l.title for l in lists] == ["My Tasks"]
    tasks = client.list_tasks("L1")
    assert len(tasks) == 151  # 150 open across two pages + 1 completed, no duplicates
    assert sum(t.done for t in tasks) == 1
    gets = [r for r in google.requests if r[0] == "GET" and r[1].endswith("/tasks")]
    assert any(r[2].get("pageToken") == "100" for r in gets)
    assert any(r[2].get("showHidden") == "true" and "completedMin" in r[2] for r in gets)


def test_crud(google, tmp_path):
    client, _ = make_client(tmp_path)
    t = client.insert_task("L1", {"title": "Hello", "due": "2026-10-03T00:00:00.000Z"})
    assert t.title == "Hello" and t.due == date(2026, 10, 3)
    sub = client.insert_task("L1", {"title": "Child"}, parent=t.id)
    assert sub.parent == t.id
    done = client.patch_task("L1", t.id, {"status": "completed"})
    assert done.done
    undone = client.patch_task("L1", t.id, {"status": "needsAction", "completed": None})
    assert not undone.done and undone.completed == ""
    client.delete_task("L1", t.id)
    assert ("DELETE", f"/lists/L1/tasks/{t.id}") in [(m, p) for m, p, _, _ in google.requests]


def test_expired_token_is_refreshed_and_saved(google, tmp_path):
    client, auth = make_client(tmp_path, access="stale", expiry=time.time() - 10)
    google.valid_token = "access-2"
    assert client.list_tasklists()
    assert google.token_requests[-1]["grant_type"] == "refresh_token"
    assert google.token_requests[-1]["client_secret"] == "secret"
    assert TokenStore(tmp_path / "token.bin").load().access_token == "access-2"


def test_401_triggers_one_refresh_and_retry(google, tmp_path):
    client, _ = make_client(tmp_path)
    google.reject_next_with_401 = True
    assert client.list_tasklists()
    assert len(google.token_requests) == 1


def test_revoked_refresh_token_requires_sign_in(google, tmp_path):
    store = TokenStore(tmp_path / "token.bin")
    store.save(Credentials("x", "revoked", time.time() - 10))
    auth = Auth(ClientConfig("cid", "secret"), store)
    with pytest.raises(ReauthRequired):
        TasksClient(auth).list_tasklists()
    assert not auth.signed_in and store.load() is None


def test_offline_error(monkeypatch, tmp_path):
    monkeypatch.setattr(TasksClient, "base_url", "http://127.0.0.1:9")  # nothing listens here
    client, _ = make_client(tmp_path)
    with pytest.raises(OfflineError):
        client.list_tasklists()
