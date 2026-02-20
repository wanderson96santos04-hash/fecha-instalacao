from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional, TypedDict

from fastapi import Request
from fastapi.responses import RedirectResponse, Response

from app.core.config import settings

try:
    from itsdangerous import URLSafeSerializer, BadSignature  # type: ignore
except Exception:
    URLSafeSerializer = None  # type: ignore
    BadSignature = Exception  # type: ignore


SESSION_COOKIE = "session"
FLASH_COOKIE = "flashes"

# Cookies precisam ser ASCII-safe. Por isso usamos base64 (evita erro latin-1 com emoji).
def _b64e(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64d(s: str) -> Any:
    raw = base64.urlsafe_b64decode(s.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _serializer() -> Optional["URLSafeSerializer"]:
    secret = getattr(settings, "SESSION_SECRET", None) or getattr(settings, "SECRET_KEY", None)
    if not secret or URLSafeSerializer is None:
        return None
    return URLSafeSerializer(secret, salt="fecha-instalacao")


def set_session(response: Response, user_id: str) -> None:
    ser = _serializer()
    payload = {"uid": str(user_id)}
    token = ser.dumps(payload) if ser else _b64e(payload)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def get_user_id_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    ser = _serializer()
    try:
        data = ser.loads(token) if ser else _b64d(token)
        uid = data.get("uid")
        return str(uid) if uid is not None else None
    except BadSignature:
        return None
    except Exception:
        return None


class Flash(TypedDict):
    kind: str
    message: str


def add_flash(response: Response, kind: str, message: str) -> None:
    # Armazena flashes no cookie em base64 (ASCII-safe)
    # Não tenta ler do request aqui (pra não depender de middleware)
    payload = {"items": [{"kind": kind, "message": message}]}
    response.set_cookie(
        FLASH_COOKIE,
        _b64e(payload),
        httponly=True,
        samesite="lax",
        max_age=60,
        path="/",
    )


def pop_flashes(request: Request) -> List[Flash]:
    token = request.cookies.get(FLASH_COOKIE)
    if not token:
        return []
    try:
        data = _b64d(token)
        items = data.get("items", [])
        if isinstance(items, list):
            return [{"kind": str(x.get("kind", "")), "message": str(x.get("message", ""))} for x in items]
        return []
    except Exception:
        return []


def redirect(url: str, *, kind: Optional[str] = None, message: Optional[str] = None, request: Optional[Request] = None) -> RedirectResponse:
    resp = RedirectResponse(url=url, status_code=303)
    if kind and message:
        # SEM emoji aqui pra não dar problema (mas mesmo se tiver, base64 aguenta).
        add_flash(resp, kind, message)
    return resp
