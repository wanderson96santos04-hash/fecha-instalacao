from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

from app.core.deps import get_user_id_from_request, pop_flashes
from app.db.session import SessionLocal
from app.models.user import User

from app.modules.onboarding.services import (
    get_onboarding_state,
    record_onboarding_event,
)

router = APIRouter(prefix="/app/onboarding")

templates = Jinja2Templates(directory="app/templates")
templates.env.loader = ChoiceLoader([  # type: ignore[attr-defined]
    templates.env.loader,
    FileSystemLoader("app/modules/onboarding/templates"),
])


def _require_user_id(request: Request) -> int:
    uid_raw = get_user_id_from_request(request)
    if not uid_raw:
        raise HTTPException(status_code=401)
    try:
        return int(uid_raw)
    except Exception:
        raise HTTPException(status_code=401)


def _get_user(uid: int) -> User | None:
    with SessionLocal() as db:
        return db.get(User, uid)


@router.get("", response_class=HTMLResponse)
def onboarding_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user_id(request)

    user = _get_user(uid)
    if not user:
        raise HTTPException(status_code=401)

    state = get_onboarding_state(uid)

    # ✅ Se já concluiu, manda direto pro dashboard
    if state.completed:
        return RedirectResponse(url="/app", status_code=302)

    return templates.TemplateResponse(
        "onboarding/onboarding.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "state": state,
        },
    )


# ✅ Step 2 – aceita GET e POST (funciona com <a href> e com <form>)
@router.api_route("/whatsapp/{budget_id}", methods=["GET", "POST"])
def onboarding_whatsapp_redirect(request: Request, budget_id: int):
    """
    Step 2:
    - registra evento do onboarding
    - redireciona para endpoint existente do core
    """
    uid = _require_user_id(request)

    record_onboarding_event(uid, "onboarding_whatsapp_clicked")

    return RedirectResponse(
        url=f"/app/budgets/{budget_id}/whatsapp",
        status_code=302,
    )