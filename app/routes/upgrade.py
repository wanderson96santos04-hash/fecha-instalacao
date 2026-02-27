from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.deps import get_user_id_from_request, redirect, pop_flashes
from app.db.session import SessionLocal
from app.models.user import User

router = APIRouter(prefix="/app")
templates = Jinja2Templates(directory="app/templates")


def _get_checkout_url() -> str:
    # ✅ Não quebra se o Settings não tiver o atributo
    url = (getattr(settings, "KIWIFY_CHECKOUT_URL", None) or "").strip()
    if not url:
        # ✅ fallback direto do ambiente (Render > Environment)
        url = (os.getenv("KIWIFY_CHECKOUT_URL") or "").strip()
    return url


@router.get("/upgrade", response_class=HTMLResponse)
def upgrade_page(request: Request):
    flashes = pop_flashes(request)
    uid = get_user_id_from_request(request)
    if not uid:
        return redirect("/login", kind="error", message="Faça login para virar Pro.")

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    checkout_url = _get_checkout_url()

    return templates.TemplateResponse(
        "upgrade.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "checkout_url": checkout_url,
        },
    )


@router.get("/checkout")
def checkout(request: Request):
    uid = get_user_id_from_request(request)
    if not uid:
        return redirect("/login", kind="error", message="Faça login para assinar o Premium.")

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    checkout_url = _get_checkout_url()
    if not checkout_url:
        return redirect(
            "/app/upgrade",
            kind="error",
            message="Checkout não configurado. Defina KIWIFY_CHECKOUT_URL nas variáveis de ambiente.",
        )

    return RedirectResponse(url=checkout_url, status_code=302)