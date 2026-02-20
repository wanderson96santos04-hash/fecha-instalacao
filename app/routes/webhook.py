from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User

router = APIRouter(prefix="/webhook")


def _get_secret_from_request(request: Request) -> str:
    # 1) Query string: /webhook/kiwify?secret=XXXX
    q = (request.query_params.get("secret") or "").strip()
    if q:
        return q

    # 2) Header: x-kiwify-secret: XXXX
    h = (request.headers.get("x-kiwify-secret") or "").strip()
    if h:
        return h

    return ""


@router.post("/kiwify")
async def kiwify_webhook(request: Request):
    # Segurança: valida secret
    received = _get_secret_from_request(request)
    expected = (settings.KIWIFY_WEBHOOK_SECRET or "").strip()

    if not expected:
        return JSONResponse(
            {"ok": False, "error": "KIWIFY_WEBHOOK_SECRET não configurado no .env"},
            status_code=500,
        )

    if not received or received != expected:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    payload = await request.json()

    # Kiwify costuma mandar buyer email em algum campo.
    # A gente tenta achar o email em vários lugares comuns:
    email = (
        (payload.get("customer", {}) or {}).get("email")
        or (payload.get("buyer", {}) or {}).get("email")
        or payload.get("email")
        or ""
    )
    email = (email or "").strip().lower()

    # Também tentamos achar status do pagamento
    status = (
        payload.get("status")
        or payload.get("payment_status")
        or (payload.get("order", {}) or {}).get("status")
        or ""
    )
    status = (status or "").strip().lower()

    # Se não tiver email, não tem como ativar
    if not email:
        return JSONResponse({"ok": True, "ignored": True, "reason": "missing_email"}, status_code=200)

    # Critério: ativar Pro quando status indica aprovado/pago
    paid_keywords = {"paid", "approved", "aprovado", "pago", "completed", "success"}
    is_paid = any(k in status for k in paid_keywords) if status else True  # se não vier status, assume true

    if not is_paid:
        return JSONResponse({"ok": True, "ignored": True, "reason": f"not_paid:{status}"}, status_code=200)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            return JSONResponse({"ok": True, "ignored": True, "reason": "user_not_found"}, status_code=200)

        user.is_pro = True
        db.commit()

    return JSONResponse({"ok": True, "pro_activated_for": email}, status_code=200)
