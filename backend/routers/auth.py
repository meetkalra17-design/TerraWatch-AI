import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.lib.auth import current_user, end_session, hash_password, start_session, verify_password
from backend.lib.db import db
from backend.models.auth import LoginIn, RegisterIn, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=User)
async def register(body: RegisterIn, response: Response):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(id=str(uuid.uuid4()), name=body.name.strip(), email=email, role=body.role)
    await db.users.insert_one({
        **user.model_dump(),
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(timezone.utc),
    })
    await start_session(response, user.id)
    return user


@router.post("/login", response_model=User)
async def login(body: LoginIn, response: Response):
    doc = await db.users.find_one({"email": body.email.lower()})
    if not doc or not verify_password(body.password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await start_session(response, doc["id"])
    return User(id=doc["id"], name=doc["name"], email=doc["email"], role=doc.get("role", "analyst"))


@router.post("/logout")
async def logout(request: Request, response: Response):
    await end_session(request, response)
    return {"ok": True}


@router.get("/me", response_model=User)
async def me(user: User = Depends(current_user)):
    return user