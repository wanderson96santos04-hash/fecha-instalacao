from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

from app.core.deps import get_user_id_from_request, pop_flashes
from app.db.session import SessionLocal
from app.models.user import User

from app.modules.invite.services import get_or_create_invite, increment_copy, increment_click_by_code

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")
templates.env.loader = ChoiceLoader([  # type: ignore[attr-defined]
    templates.env.loader,
    FileSystemLoader("app/modules/invite/templates"),
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


@router.get("/app/invite", response_class=HTMLResponse)
def invite_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user_id(request)
    user = _get_user(uid)
    if not user:
        raise HTTPException(status_code=401)

    info = get_or_create_invite(uid)

    base_url = str(request.base_url).rstrip("/")
    link = f"{base_url}/i/{info.code}"

    share_text = (
        "🚀 Estou usando o FECHA INSTALAÇÃO para enviar orçamentos e fechar mais rápido.\n"
        f"Quer testar? Entra por aqui: {link}"
    )

    return templates.TemplateResponse(
        "invite/invite.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "invite_link": link,
            "share_text": share_text,
            "copy_count": info.copy_count,
            "click_count": info.click_count,
        },
    )


@router.post("/app/invite/copy")
def invite_copy(request: Request):
    uid = _require_user_id(request)
    increment_copy(uid)
    return {"ok": True}


@router.get("/i/{code}")
def invite_public_redirect(code: str):
    code = (code or "").strip().lower()
    if not code:
        return RedirectResponse(url="/", status_code=302)

    increment_click_by_code(code)
    return RedirectResponse(url=f"/?ref={code}", status_code=302)