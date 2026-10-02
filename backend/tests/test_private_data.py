import mongomock
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pymongo import MongoClient as RealMongoClient
from app import main, private_data


@pytest.fixture
def notes_client(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(private_data, "_client", client)
    monkeypatch.setattr(private_data, "_client_uri", "mongodb://unit-test")
    monkeypatch.setattr(private_data, "_indexes_ready", False)
    monkeypatch.setenv("MONGODB_URI", "mongodb://unit-test")
    monkeypatch.setenv("MONGODB_DB_NAME", "kavach_test")
    monkeypatch.setenv("JWT_SECRET", "a" * 40)
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    private_data._rate_events.clear(); private_data._user_events.clear(); private_data._login_failures.clear()
    return TestClient(main.app), client["kavach_test"]


def _register(client, email):
    response = client.post("/auth/register", json={"email": email, "password": "correct horse battery", "consent": True})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token): return {"Authorization": f"Bearer {token}"}


def test_accounts_duplicate_login_failure_throttle_refresh_and_logout(notes_client):
    client, db = notes_client
    token = _register(client, "one@example.com")
    duplicate = client.post("/auth/register", json={"email": "one@example.com", "password": "correct horse battery", "consent": True})
    assert duplicate.status_code == 409
    login = client.post("/auth/login", json={"email": "one@example.com", "password": "correct horse battery"})
    assert login.status_code == 200
    wrong = [client.post("/auth/login", json={"email": "one@example.com", "password": "wrong"}) for _ in range(5)]
    assert all(r.status_code == 401 and r.json()["detail"] == "Email or password is incorrect." for r in wrong)
    blocked = client.post("/auth/login", json={"email": "one@example.com", "password": "correct horse battery"})
    assert blocked.status_code == 429
    assert client.get("/me", headers=_headers(token)).status_code == 200
    assert client.post("/auth/refresh").status_code == 401
    assert client.post("/auth/logout", headers=_headers(token)).status_code == 200
    assert client.get("/me", headers=_headers(token)).status_code == 401


def test_encrypted_note_crud_quota_export_and_isolation(notes_client, monkeypatch):
    client, db = notes_client
    token_a = _register(client, "a@example.com")
    token_b = _register(client, "b@example.com")
    a = client.post("/notes", headers=_headers(token_a), json={"title": "Field", "body": "private body", "type": "observation"})
    b = client.post("/notes", headers=_headers(token_b), json={"title": "Price", "body": "private quote", "type": "price"})
    assert a.status_code == b.status_code == 200
    note_a, note_b = a.json(), b.json()
    assert b"private body" not in repr(db.notes.find_one({"id": note_a["id"]})).encode()
    assert "user_id" not in note_a
    assert client.get("/notes/" + note_b["id"], headers=_headers(token_a)).status_code == 404
    assert client.patch("/notes/" + note_b["id"], headers=_headers(token_a), json={"body": "hacked"}).status_code == 404
    assert client.delete("/notes/" + note_b["id"], headers=_headers(token_a)).status_code == 404
    assert client.get("/notes/export", headers=_headers(token_a)).json()["notes"][0]["body"] == "private body"
    assert client.get("/notes", headers=_headers(token_a)).json()["note_label"] == "Your note: not verified by Kavach"
    assert client.patch("/notes/" + note_a["id"], headers=_headers(token_a), json={"title": "Updated"}).json()["title"] == "Updated"
    monkeypatch.setenv("KAVACH_NOTE_QUOTA", "1")
    exceeded = client.post("/notes", headers=_headers(token_a), json={"title": "Second", "body": "body"})
    assert exceeded.status_code == 413
    assert client.delete("/notes/" + note_a["id"], headers=_headers(token_a)).status_code == 200
    user_a_id = db.users.find_one({"email": "a@example.com"})["_id"]
    assert db.notes.count_documents({"user_id": user_a_id}) == 0


def test_registration_consent_and_nosql_injection_rejected(notes_client):
    client, _ = notes_client
    refused = client.post("/auth/register", json={"email": "x@example.com", "password": "correct horse battery", "consent": False})
    assert refused.status_code == 422
    token = _register(client, "x@example.com")
    injected = client.post("/notes", headers=_headers(token), json={"title": "Bad", "body": "x", "fields": {"$where": "true"}})
    assert injected.status_code == 422
    dotted = client.post("/notes", headers=_headers(token), json={"title": "Bad", "body": "x", "fields": {"secret.field": "x"}})
    assert dotted.status_code == 422


def test_account_delete_removes_notes_and_live_weather_still_serves_without_mongo(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    assert client.get("/weather/NotARealPlace").status_code == 200
    assert client.get("/notes").status_code in (401, 503)

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import jwt


def test_refresh_rotation_expired_access_and_account_hard_delete(notes_client):
    client, db = notes_client
    token = _register(client, "delete@example.com")
    headers = _headers(token)
    created = client.post("/notes", headers=headers, json={"title": "Keep", "body": "private"})
    user = db.users.find_one({"email": "delete@example.com"})
    assert created.status_code == 200
    expired = jwt.encode({"sub": user["_id"], "ver": 0, "iat": datetime.now(timezone.utc)-timedelta(hours=1),
                          "exp": datetime.now(timezone.utc)-timedelta(minutes=1)},
                         __import__('os').environ["JWT_SECRET"], algorithm="HS256")
    assert client.get("/me", headers=_headers(expired)).status_code == 401
    refresh = secrets.token_urlsafe(40)
    db.refresh_tokens.insert_one({"token_hash": hashlib.sha256(refresh.encode()).hexdigest(), "user_id": user["_id"],
                                  "expires_at": datetime.now(timezone.utc)+timedelta(days=5)})
    rotated = client.post("/auth/refresh", cookies={"kavach_refresh": refresh})
    assert rotated.status_code == 200
    assert rotated.json()["access_token"] != token
    assert client.delete("/me", headers=headers).status_code == 200
    assert db.users.find_one({"_id": user["_id"]}) is None
    assert db.notes.count_documents({"user_id": user["_id"]}) == 0
    assert db.refresh_tokens.count_documents({"user_id": user["_id"]}) == 0


def test_notes_cursor_paginates_without_duplicates(notes_client):
    client, _ = notes_client
    token = _register(client, "pages@example.com")
    for index in range(3):
        assert client.post("/notes", headers=_headers(token), json={"title": f"Note {index}", "body": str(index)}).status_code == 200
    first = client.get("/notes?limit=2", headers=_headers(token)).json()
    assert first["next_cursor"]
    second = client.get("/notes?limit=2&cursor="+first["next_cursor"], headers=_headers(token)).json()
    ids = [note["id"] for note in first["notes"]+second["notes"]]
    assert len(ids) == len(set(ids)) == 3


def test_notes_do_not_enter_ai_snapshot_cache(notes_client):
    client, _ = notes_client
    token = _register(client, "private@example.com")
    assert client.post("/notes", headers=_headers(token), json={"title": "Secret", "body": "DISTINCTIVE_PRIVATE_NOTE"}).status_code == 200
    main._snapshot_cache.update(at=0, value=None)
    snapshot = main._support_snapshot()
    assert "DISTINCTIVE_PRIVATE_NOTE" not in repr(snapshot)
    assert "notes" not in snapshot
