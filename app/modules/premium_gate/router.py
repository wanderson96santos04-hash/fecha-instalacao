from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

from app.core.deps import get_user_id_from_request, pop_flashes
from app.db.session import SessionLocal
from app.models.user import User

from app.modules.premium_gate.services import get_gate_info

router = APIRouter(prefix="/app/premium")

templates = Jinja2Templates(directory="app/templates")
templates.env.loader = ChoiceLoader([  # type: ignore[attr-defined]
    templates.env.loader,
    FileSystemLoader("app/modules/premium_gate/templates"),
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


@router.get("/limit", response_class=HTMLResponse)
def limit_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user_id(request)
    user = _get_user(uid)
    if not user:
        raise HTTPException(status_code=401)

    info = get_gate_info(uid)

    return templates.TemplateResponse(
        "premium_gate/limit.html",
        {"request": request, "flashes": flashes, "user": user, "info": info},
    )