from __future__ import annotations

import os
import hmac
import hashlib
from typing import Any, Optional

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _get_signature_from_headers(headers: dict[str, str]) -> str:
    # Tenta vários nomes comuns (a Kiwify pode variar por produto/conta/config)
    candidates = [
        "x-kiwify-signature",
        "x-signature",
        "x-hub-signature-256",
        "kiwify-signature",
    ]
    for k in candidates:
        if k in headers and headers[k]:
            return headers[k].strip()
    return ""


def _normalize_sig(sig: str) -> str:
    # aceita "sha256=...."
    if sig.lower().startswith("sha256="):
        return sig.split("=", 1)[1].strip()
    return sig.strip()


def _verify_signature(raw_body: bytes, secret: str, header_sig: str) -> bool:
    if not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, _normalize_sig(header_sig))


def _extract_email(payload: dict[str, Any]) -> Optional[str]:
    # tenta formatos comuns
    paths = [
        ("customer", "email"),
        ("Customer", "email"),
        ("buyer", "email"),
        ("Buyer", "email"),
        ("email",),
    ]
    for path in paths:
        cur: Any = payload
        ok = True
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                ok = False
                break
        if ok and isinstance(cur, str) and "@" in cur:
            return cur.strip().lower()
    return None


def _extract_status(payload: dict[str, Any]) -> str:
    # tenta achar um status de pagamento/assinatura
    for key in ("status", "order_status", "payment_status", "subscription_status", "event", "type"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def _status_to_pro(status: str) -> Optional[bool]:
    """
    Mapeamento robusto:
    - retorna True => ativa pro
    - retorna False => desativa pro
    - retorna None => não faz nada (evento irrelevante/desconhecido)
    """
    s = (status or "").lower()

    # ATIVA
    if any(x in s for x in ["paid", "approved", "aprov", "active", "ativa", "completed", "success"]):
        return True

    # DESATIVA
    if any(x in s for x in ["refunded", "refund", "chargeback", "canceled", "cancelled", "expired", "inactive", "falha", "failed"]):
        return False

    return None


@router.post("/kiwify")
async def kiwify_webhook(request: Request):
    """
    Webhook da Kiwify.
    1) Valida assinatura (HMAC SHA256) usando KIWIFY_WEBHOOK_SECRET
    2) Pega email do comprador
    3) Atualiza user.is_pro = True/False conforme status do evento
    """
    secret = (os.getenv("KIWIFY_WEBHOOK_SECRET") or "").strip()
    allow_unsigned = (os.getenv("KIWIFY_ALLOW_UNSIGNED_WEBHOOKS") or "").strip() == "1"

    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    header_sig = _get_signature_from_headers(headers)

    if not allow_unsigned:
        if not header_sig:
            return JSONResponse({"ok": False, "error": "missing_signature"}, status_code=401)
        if not _verify_signature(raw, secret, header_sig):
            return JSONResponse({"ok": False, "error": "invalid_signature"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    email = _extract_email(payload)
    status = _extract_status(payload)
    decision = _status_to_pro(status)

    if not email:
        return JSONResponse({"ok": False, "error": "missing_email"}, status_code=400)

    # Se não reconheceu o status, só aceita e não altera nada
    if decision is None:
        return JSONResponse({"ok": True, "message": "event_ignored", "email": email, "status": status})

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            # comprador não tem conta no app (ou email diferente do cadastro)
            return JSONResponse({"ok": True, "message": "user_not_found", "email": email, "status": status})

        user.is_pro = bool(decision)
        db.commit()

    return JSONResponse({"ok": True, "email": email, "status": status, "is_pro": bool(decision)})
