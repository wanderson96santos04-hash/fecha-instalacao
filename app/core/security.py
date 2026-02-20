from __future__ import annotations

import os
from itsdangerous import URLSafeSerializer, BadSignature
from passlib.context import CryptContext


# ==========================
# CONFIG HASH (SEM BCRYPT)
# ==========================

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    password = (password or "").strip()
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    password = (password or "").strip()
    return pwd_context.verify(password, password_hash)


# ==========================
# SESSÃO (TOKEN)
# ==========================

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

_serializer = URLSafeSerializer(SECRET_KEY, salt="session")


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer.loads(token)
        uid = data.get("uid")
        return int(uid) if uid is not None else None
    except (BadSignature, ValueError, TypeError):
        return None
