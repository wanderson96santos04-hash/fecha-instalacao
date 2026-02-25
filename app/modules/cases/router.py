from __future__ import annotations

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

from app.core.deps import get_user_id_from_request, pop_flashes, redirect
from app.db.session import SessionLocal
from app.models.user import User

from app.modules.cases.services import (
    is_cases_admin,
    list_testimonials,
    get_testimonial,
    create_testimonial,
    update_testimonial,
    delete_testimonial,
)

router = APIRouter(prefix="/app/cases")

templates = Jinja2Templates(directory="app/templates")
templates.env.loader = ChoiceLoader([  # type: ignore[attr-defined]
    templates.env.loader,
    FileSystemLoader("app/modules/cases/templates"),
])


def _require_user_id(request: Request) -> int:
    uid_raw = get_user_id_from_request(request)
    if not uid_raw:
        raise HTTPException(status_code=401)
    try:
        return int(uid_raw)
    except Exception:
        raise HTTPException(status_code=401)


def _require_user(request: Request) -> User:
    uid = _require_user_id(request)
    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            raise HTTPException(status_code=401)
        return user


@router.get("", response_class=HTMLResponse)
def cases_page(request: Request):
    flashes = pop_flashes(request)
    user = _require_user(request)
    items = list_testimonials()

    return templates.TemplateResponse(
        "cases/cases.html",
        {"request": request, "flashes": flashes, "user": user, "items": items},
    )


@router.get("/admin", response_class=HTMLResponse)
def admin_list(request: Request):
    flashes = pop_flashes(request)
    user = _require_user(request)

    if not is_cases_admin(user.id, bool(user.is_pro)):
        return redirect("/app", kind="error", message="Sem permissão para administrar depoimentos.")

    items = list_testimonials()
    return templates.TemplateResponse(
        "cases/admin_list.html",
        {"request": request, "flashes": flashes, "user": user, "items": items},
    )


@router.get("/admin/new", response_class=HTMLResponse)
def admin_new_page(request: Request):
    flashes = pop_flashes(request)
    user = _require_user(request)

    if not is_cases_admin(user.id, bool(user.is_pro)):
        return redirect("/app", kind="error", message="Sem permissão.")

    return templates.TemplateResponse(
        "cases/admin_new.html",
        {"request": request, "flashes": flashes, "user": user},
    )


@router.post("/admin/new")
def admin_new_action(
    request: Request,
    name: str = Form(...),
    city: str = Form(""),
    service: str = Form(""),
    value: str = Form(""),
    quote: str = Form(...),
):
    user = _require_user(request)
    if not is_cases_admin(user.id, bool(user.is_pro)):
        return redirect("/app", kind="error", message="Sem permissão.")

    tid = create_testimonial(
        {"name": name, "city": city, "service": service, "value": value, "quote": quote}
    )
    return RedirectResponse(url=f"/app/cases/admin?created={tid}", status_code=303)


@router.get("/admin/{tid}/edit", response_class=HTMLResponse)
def admin_edit_page(request: Request, tid: int):
    flashes = pop_flashes(request)
    user = _require_user(request)
    if not is_cases_admin(user.id, bool(user.is_pro)):
        return redirect("/app", kind="error", message="Sem permissão.")

    t = get_testimonial(tid)
    if not t:
        return redirect("/app/cases/admin", kind="error", message="Depoimento não encontrado.")

    return templates.TemplateResponse(
        "cases/admin_edit.html",
        {"request": request, "flashes": flashes, "user": user, "t": t},
    )


@router.post("/admin/{tid}/edit")
def admin_edit_action(
    request: Request,
    tid: int,
    name: str = Form(...),
    city: str = Form(""),
    service: str = Form(""),
    value: str = Form(""),
    quote: str = Form(...),
):
    user = _require_user(request)
    if not is_cases_admin(user.id, bool(user.is_pro)):
        return redirect("/app", kind="error", message="Sem permissão.")

    update_testimonial(
        tid,
        {"name": name, "city": city, "service": service, "value": value, "quote": quote},
    )
    return RedirectResponse(url="/app/cases/admin", status_code=303)


@router.post("/admin/{tid}/delete")
def admin_delete_action(request: Request, tid: int):
    user = _require_user(request)
    if not is_cases_admin(user.id, bool(user.is_pro)):
        return redirect("/app", kind="error", message="Sem permissão.")

    delete_testimonial(tid)
    return RedirectResponse(url="/app/cases/admin", status_code=303)


@router.get("/{tid}/export", response_class=HTMLResponse)
def export_page(request: Request, tid: int):
    """
    Export simples em HTML pronto para copiar/print/screenshot.
    Se você tiver export pronto no social_proof, dá pra trocar aqui depois.
    """
    user = _require_user(request)
    t = get_testimonial(tid)
    if not t:
        return redirect("/app/cases", kind="error", message="Depoimento não encontrado.")

    return templates.TemplateResponse(
        "cases/export.html",
        {"request": request, "user": user, "t": t},
    )