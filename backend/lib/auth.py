"""Cookie-session auth helpers."""

import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from passlib.context import CryptContext

from backend.lib.db import db
from backend.models.auth import User

COOKIE = "tw_session"
SESSION_DAYS = 7
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(p: str) -> str:
    return pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    try:
        return pwd.verify(p, h)
    except Exception:
        return False


async def start_session(response: Response, user_id: str) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    await db.sessions.insert_one({"token": token, "user_id": user_id, "expires_at": expires})
    response.set_cookie(
        COOKIE, token, httponly=True,
        secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        max_age=SESSION_DAYS * 86400, path="/",
    )


async def end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        await db.sessions.delete_one({"token": token})
    response.delete_cookie(COOKIE, path="/")


async def current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    sess = await db.sessions.find_one({"token": token})
    if not sess:
        raise HTTPException(status_code=401, detail="Session expired")
    exp = sess["expires_at"].replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        await db.sessions.delete_one({"token": token})
        raise HTTPException(status_code=401, detail="Session expired")
    doc = await db.users.find_one({"id": sess["user_id"]})
    if not doc:
        raise HTTPException(status_code=401, detail="User not found")
    return User(id=doc["id"], name=doc["name"], email=doc["email"], role=doc.get("role", "analyst"))