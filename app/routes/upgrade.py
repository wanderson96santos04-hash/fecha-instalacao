from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.deps import get_user_id_from_request, redirect, pop_flashes
from app.db.session import SessionLocal
from app.models.user import User

router = APIRouter(prefix="/app")
templates = Jinja2Templates(directory="app/templates")


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

    checkout_url = (settings.KIWIFY_CHECKOUT_URL or "").strip()

    return templates.TemplateResponse(
        "upgrade.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "checkout_url": checkout_url,
        },
    )
