"""Optional Mongo-backed private accounts and encrypted user notes."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
import jwt

router = APIRouter()
_hasher = PasswordHasher()
_client = None
_client_uri = None
_db_lock = threading.Lock()
_indexes_ready = False
_rate_lock = threading.Lock()
_rate_events: dict[tuple[str, str], list[float]] = {}
_login_failures: dict[tuple[str, str], tuple[int, float]] = {}
_user_events: dict[tuple[str, str], list[float]] = {}


def _unavailable(status: str, message: str):
    return JSONResponse(status_code=503, content={"status": status, "note": message})


def _origin_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limit(request: Request, name: str, count: int = 30, window: int = 60):
    now = time.time(); key = (_origin_ip(request), name)
    with _rate_lock:
        if len(_rate_events) > 2048:
            for old_key, old_hits in list(_rate_events.items()):
                if not old_hits or now - old_hits[-1] >= window:
                    _rate_events.pop(old_key, None)
        hits = [stamp for stamp in _rate_events.get(key, []) if now - stamp < window]
        if len(hits) >= count:
            raise HTTPException(429, "Too many requests. Please wait before trying again.")
        hits.append(now); _rate_events[key] = hits


def _user_limit(user_id: str, name: str, count: int = 60, window: int = 60):
    now = time.time(); key = (user_id, name)
    with _rate_lock:
        if len(_user_events) > 2048:
            for old_key, old_hits in list(_user_events.items()):
                if not old_hits or now - old_hits[-1] >= window:
                    _user_events.pop(old_key, None)
        hits = [stamp for stamp in _user_events.get(key, []) if now - stamp < window]
        if len(hits) >= count:
            raise HTTPException(429, "Too many requests for this account. Please wait before trying again.")
        hits.append(now); _user_events[key] = hits


def _ready_db():
    global _client, _client_uri, _indexes_ready
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        return None, "NEEDS_CONFIGURATION"
    try:
        with _db_lock:
            if _client is None or _client_uri != uri:
                try:
                    from pymongo import MongoClient
                except ImportError:
                    return None, "NEEDS_CONFIGURATION"
                _client = MongoClient(uri, serverSelectionTimeoutMS=1800, connectTimeoutMS=1800)
                _client_uri = uri; _indexes_ready = False
            _client.admin.command("ping")
            db = _client[os.environ.get("MONGODB_DB_NAME", "kavach").strip() or "kavach"]
            if not _indexes_ready:
                db.users.create_index("email", unique=True)
                db.notes.create_index([("user_id", 1), ("created_at", -1)])
                db.notes.create_index([("user_id", 1), ("id", 1)], unique=True)
                db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
                db.refresh_tokens.create_index("token_hash", unique=True)
                _indexes_ready = True
            return db, "READY"
    except Exception:
        return None, "UNAVAILABLE"


def _crypto():
    value = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not value:
        return None
    try:
        return Fernet(value.encode("ascii"))
    except (ValueError, UnicodeError):
        return None


def _auth_configured():
    secret = os.environ.get("JWT_SECRET", "").strip()
    return len(secret.encode("utf-8")) >= 32


def _requirements(db_needed=True, crypto_needed=False, auth_needed=False):
    if auth_needed and not _auth_configured():
        return None, _unavailable("NEEDS_CONFIGURATION", "Set JWT_SECRET to at least 32 characters to enable private accounts.")
    if crypto_needed and not _crypto():
        return None, _unavailable("NEEDS_CONFIGURATION", "Set a valid Fernet ENCRYPTION_KEY to enable encrypted notes.")
    db, state = _ready_db() if db_needed else (True, "READY")
    if not db:
        note = "Configure MONGODB_URI and MONGODB_DB_NAME to enable accounts and notes." if state == "NEEDS_CONFIGURATION" else "The private database is unavailable. Live data remains available; retry notes later."
        return None, _unavailable(state, note)
    return db, None


def _access_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user["_id"]), "ver": int(user.get("token_version", 0)), "jti": secrets.token_urlsafe(12),
                       "iat": now, "exp": now + timedelta(minutes=15)},
                      os.environ["JWT_SECRET"], algorithm="HS256")


def _user_from_header(authorization: str | None, db):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in to access this private data.")
    try:
        payload = jwt.decode(authorization[7:].strip(), os.environ["JWT_SECRET"], algorithms=["HS256"])
        user = db.users.find_one({"_id": payload.get("sub")})
        if not user or int(user.get("token_version", 0)) != int(payload.get("ver", -1)):
            raise HTTPException(401, "Your session has expired. Sign in again.")
        return user
    except HTTPException:
        raise
    except jwt.PyJWTError:
        raise HTTPException(401, "Your session has expired. Sign in again.")


def _private_user(request: Request, authorization: str | None, *, notes=True):
    _limit(request, "private:" + request.url.path.split("/")[1], 60)
    db, error = _requirements(auth_needed=True, crypto_needed=notes)
    if error: return None, None, error
    user = _user_from_header(authorization, db)
    _user_limit(str(user["_id"]), request.url.path.split("/")[1])
    return db, user, None


class RegisterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    consent: bool

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("consent")
    @classmethod
    def requires_consent(cls, value):
        if not value: raise ValueError("Registration consent is required.")
        return value


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["observation", "price", "crop", "water", "transcript", "ai_answer", "general"] = "general"
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    fields: dict[str, object] = Field(default_factory=dict)
    source: Literal["user_entered", "ai_generated"] = "user_entered"

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, tags):
        if any(not isinstance(tag, str) or len(tag) > 40 for tag in tags): raise ValueError("Tags must be text of at most 40 characters.")
        return tags


class NotePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["observation", "price", "crop", "water", "transcript", "ai_answer", "general"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    tags: list[str] | None = Field(default=None, max_length=10)
    fields: dict[str, object] | None = None


def _reject_operators(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or key.startswith("$") or "." in key:
                raise HTTPException(422, "MongoDB operator keys are not allowed.")
            _reject_operators(item)
    elif isinstance(value, list):
        for item in value: _reject_operators(item)


def _stored_note(note: dict):
    try:
        body = _crypto().decrypt(note["body_cipher"].encode()).decode("utf-8")
    except (InvalidToken, KeyError, AttributeError, UnicodeError):
        raise HTTPException(500, "This note cannot be decrypted with the configured key.")
    result = {k: note[k] for k in ("id", "type", "title", "tags", "fields", "source", "created_at", "updated_at") if k in note}
    result["body"] = body
    result["created_at"] = result["created_at"].isoformat()
    result["updated_at"] = result["updated_at"].isoformat()
    return result


def _cookie(response: Response, token: str | None):
    response.set_cookie("kavach_refresh", token or "", max_age=30 * 24 * 3600 if token else 0,
                        httponly=True, secure=True, samesite="strict", path="/auth")


@router.post("/auth/register")
def register(body: RegisterBody, request: Request):
    _limit(request, "auth-register", 5)
    db, error = _requirements(auth_needed=True, crypto_needed=True)
    if error: return error
    if db.users.find_one({"email": body.email}):
        raise HTTPException(409, "An account with this email already exists.")
    now = datetime.now(timezone.utc); uid = uuid.uuid4().hex
    try:
        db.users.insert_one({"_id": uid, "email": body.email, "password_hash": _hasher.hash(body.password),
                             "created_at": now, "token_version": 0})
    except Exception:
        raise HTTPException(409, "An account with this email already exists.")
    user = {"_id": uid, "email": body.email, "token_version": 0}
    refresh = secrets.token_urlsafe(48)
    db.refresh_tokens.insert_one({"token_hash": hashlib.sha256(refresh.encode()).hexdigest(), "user_id": uid,
                                  "expires_at": now + timedelta(days=30), "created_at": now})
    response = JSONResponse({"access_token": _access_token(user), "token_type": "bearer", "user": {"email": body.email}})
    _cookie(response, refresh)
    return response


@router.post("/auth/login")
def login(body: LoginBody, request: Request):
    _limit(request, "auth-login", 10)
    db, error = _requirements(auth_needed=True, crypto_needed=True)
    if error: return error
    email = body.email.strip().lower(); ip = _origin_ip(request); now = time.time()
    account_key = (email, "account"); ip_key = (email, ip)
    with _rate_lock:
        for key in (account_key, ip_key):
            attempts, until = _login_failures.get(key, (0, 0))
            if until > now: raise HTTPException(429, "Sign in is temporarily paused. Please try again later.")
    user = db.users.find_one({"email": email})
    valid = False
    if user:
        try: valid = _hasher.verify(user["password_hash"], body.password)
        except (VerifyMismatchError, VerificationError, KeyError): valid = False
    if not user or not valid:
        with _rate_lock:
            for key in (account_key, ip_key):
                attempts, _ = _login_failures.get(key, (0, 0)); attempts += 1
                _login_failures[key] = (attempts, now + 900 if attempts >= 5 else 0)
        raise HTTPException(401, "Email or password is incorrect.")
    with _rate_lock:
        _login_failures.pop(account_key, None); _login_failures.pop(ip_key, None)
    refresh = secrets.token_urlsafe(48); expires = datetime.now(timezone.utc) + timedelta(days=30)
    db.refresh_tokens.insert_one({"token_hash": hashlib.sha256(refresh.encode()).hexdigest(), "user_id": user["_id"],
                                  "expires_at": expires, "created_at": datetime.now(timezone.utc)})
    response = JSONResponse({"access_token": _access_token(user), "token_type": "bearer", "user": {"email": email}})
    _cookie(response, refresh)
    return response


@router.post("/auth/refresh")
def refresh_access(request: Request, refresh_cookie: str | None = Cookie(default=None, alias="kavach_refresh")):
    _limit(request, "auth-refresh", 20)
    db, error = _requirements(auth_needed=True, crypto_needed=True)
    if error: return error
    if not refresh_cookie: raise HTTPException(401, "Sign in again to continue.")
    digest = hashlib.sha256(refresh_cookie.encode()).hexdigest()
    record = db.refresh_tokens.find_one({"token_hash": digest, "expires_at": {"$gt": datetime.now(timezone.utc)}})
    if not record: raise HTTPException(401, "Your session has expired. Sign in again.")
    user = db.users.find_one({"_id": record["user_id"]})
    if not user: raise HTTPException(401, "Your session has expired. Sign in again.")
    db.refresh_tokens.delete_many({"user_id": user["_id"]})
    replacement = secrets.token_urlsafe(48); now = datetime.now(timezone.utc)
    db.refresh_tokens.insert_one({"token_hash": hashlib.sha256(replacement.encode()).hexdigest(), "user_id": user["_id"],
                                  "expires_at": now + timedelta(days=30), "created_at": now})
    response = JSONResponse({"access_token": _access_token(user), "token_type": "bearer"})
    _cookie(response, replacement)
    return response


@router.post("/auth/logout")
def logout(request: Request, authorization: str | None = Header(default=None), refresh_cookie: str | None = Cookie(default=None, alias="kavach_refresh")):
    _limit(request, "auth-logout", 20)
    db, error = _requirements(auth_needed=True, crypto_needed=True)
    if error: return error
    user = _user_from_header(authorization, db); _user_limit(user["_id"], "auth")
    db.users.update_one({"_id": user["_id"]}, {"$inc": {"token_version": 1}})
    db.refresh_tokens.delete_many({"user_id": user["_id"]})
    response = JSONResponse({"status": "SIGNED_OUT"}); _cookie(response, None); return response


@router.get("/me")
def me(request: Request, authorization: str | None = Header(default=None)):
    db, user, error = _private_user(request, authorization, notes=False)
    if error: return error
    return {"id": user["_id"], "email": user["email"]}


@router.delete("/me")
def delete_account(request: Request, authorization: str | None = Header(default=None)):
    db, user, error = _private_user(request, authorization, notes=True)
    if error: return error
    db.notes.delete_many({"user_id": user["_id"]})
    db.refresh_tokens.delete_many({"user_id": user["_id"]})
    db.users.delete_one({"_id": user["_id"]})
    response = JSONResponse({"status": "DELETED"}); _cookie(response, None); return response


@router.post("/notes")
def create_note(body: NoteCreate, request: Request, authorization: str | None = Header(default=None)):
    db, user, error = _private_user(request, authorization)
    if error: return error
    _user_limit(user["_id"], "notes-write", 20)
    values = body.model_dump(); _reject_operators(values)
    if db.notes.count_documents({"user_id": user["_id"]}) >= int(os.environ.get("KAVACH_NOTE_QUOTA", "500")):
        raise HTTPException(413, "Your account has reached its 500-note storage limit. Delete notes before saving more.")
    now = datetime.now(timezone.utc)
    item = {"id": uuid.uuid4().hex, "user_id": user["_id"], "type": values["type"], "title": values["title"].strip(),
            "body_cipher": _crypto().encrypt(values["body"].encode()).decode(), "tags": values["tags"], "fields": values["fields"],
            "source": values["source"], "created_at": now, "updated_at": now}
    db.notes.insert_one(item)
    return _stored_note(item)


def _cursor_encode(record):
    created_at = record["created_at"]
    if not isinstance(created_at, str): created_at = created_at.isoformat()
    return base64.urlsafe_b64encode(json.dumps({"created_at": created_at, "id": record["id"]}).encode()).decode().rstrip("=")


def _cursor_decode(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        parsed = json.loads(raw)
        return datetime.fromisoformat(parsed["created_at"]), str(parsed["id"])
    except Exception: raise HTTPException(422, "The notes cursor is invalid.")


@router.get("/notes")
def list_notes(request: Request, authorization: str | None = Header(default=None), limit: int = 50, cursor: str | None = None,
              type: str | None = None, tag: str | None = None, start: datetime | None = None, end: datetime | None = None, q: str | None = None):
    db, user, error = _private_user(request, authorization)
    if error: return error
    _user_limit(user["_id"], "notes-read")
    limit = min(max(limit, 1), 100)
    query: dict = {"user_id": user["_id"]}
    if type: query["type"] = type
    if tag: query["tags"] = tag
    if start or end:
        query["created_at"] = {}
        if start: query["created_at"]["$gte"] = start
        if end: query["created_at"]["$lte"] = end
    records = list(db.notes.find(query).sort([("created_at", -1), ("id", -1)]).limit(501))
    decoded = [_stored_note(row) for row in records]
    if cursor:
        cursor_at, cursor_id = _cursor_decode(cursor)
        decoded = [n for n in decoded if (datetime.fromisoformat(n["created_at"]), n["id"]) < (cursor_at, cursor_id)]
    if q:
        needle = q.casefold()
        decoded = [n for n in decoded if needle in n["title"].casefold() or needle in n["body"].casefold() or any(needle in t.casefold() for t in n["tags"])]
    page = decoded[:limit]
    return {"notes": page, "next_cursor": _cursor_encode(page[-1]) if len(decoded) > limit and page else None,
            "status": "READY", "note_label": "Your note: not verified by Kavach"}


@router.get("/notes/export")
def export_notes(request: Request, authorization: str | None = Header(default=None)):
    db, user, error = _private_user(request, authorization)
    if error: return error
    _user_limit(user["_id"], "notes-read")
    notes = [_stored_note(row) for row in db.notes.find({"user_id": user["_id"]}).sort("created_at", -1)]
    return {"status": "READY", "notes": notes, "warning": "Your notes are not verified by Kavach."}


@router.get("/notes/{note_id}")
def get_note(note_id: str, request: Request, authorization: str | None = Header(default=None)):
    db, user, error = _private_user(request, authorization)
    if error: return error
    _user_limit(user["_id"], "notes-read")
    record = db.notes.find_one({"id": note_id, "user_id": user["_id"]})
    if not record: raise HTTPException(404, "Note not found.")
    return _stored_note(record)


@router.patch("/notes/{note_id}")
def update_note(note_id: str, body: NotePatch, request: Request, authorization: str | None = Header(default=None)):
    db, user, error = _private_user(request, authorization)
    if error: return error
    _user_limit(user["_id"], "notes-write", 20)
    values = body.model_dump(exclude_unset=True); _reject_operators(values)
    updates = {k: v for k, v in values.items() if k != "body"}
    if "title" in updates: updates["title"] = updates["title"].strip()
    if "body" in values: updates["body_cipher"] = _crypto().encrypt(values["body"].encode()).decode()
    updates["updated_at"] = datetime.now(timezone.utc)
    result = db.notes.update_one({"id": note_id, "user_id": user["_id"]}, {"$set": updates})
    if not result.matched_count: raise HTTPException(404, "Note not found.")
    return _stored_note(db.notes.find_one({"id": note_id, "user_id": user["_id"]}))


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, request: Request, authorization: str | None = Header(default=None)):
    db, user, error = _private_user(request, authorization)
    if error: return error
    _user_limit(user["_id"], "notes-write", 20)
    result = db.notes.delete_one({"id": note_id, "user_id": user["_id"]})
    if not result.deleted_count: raise HTTPException(404, "Note not found.")
    return {"status": "DELETED"}
