from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.core.deps import get_user_id_from_request
from app.db.session import SessionLocal
from app.models.user import User

from app.modules.social_proof.exporters import (
    build_social_proof_text,
    export_pdf,
    export_pptx,
)

router = APIRouter(prefix="/app/social-proof", tags=["SocialProof"])
templates = Jinja2Templates(directory="app/templates")


def _get_user(request: Request) -> Optional[User]:
    uid = get_user_id_from_request(request)
    if not uid:
        return None
    try:
        uid_int = int(uid)
    except Exception:
        return None

    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == uid_int).first()
    finally:
        db.close()


def _require_login(request: Request):
    user = _get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return user


def _require_pro(user: User):
    if not bool(getattr(user, "is_pro", False)):
        return RedirectResponse(url="/app/upgrade", status_code=303)
    return None


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def social_proof_page(request: Request):
    user_or_redirect = _require_login(request)
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    user: User = user_or_redirect

    ctx: Dict = {
        "request": request,
        "now": datetime.now(timezone.utc),
        "user": user,
        "is_pro": bool(getattr(user, "is_pro", False)),
        "form": {"servico": "", "valor": "", "cidade": "", "detalhe": ""},
        "result_text": "",
    }
    return templates.TemplateResponse("social_proof/social_proof.html", ctx)


@router.post("/generate", response_class=HTMLResponse)
def social_proof_generate(
    request: Request,
    servico: str = Form(default=""),
    valor: str = Form(default=""),
    cidade: str = Form(default=""),
    detalhe: str = Form(default=""),
):
    user_or_redirect = _require_login(request)
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    user: User = user_or_redirect

    # valor pode vir com vírgula
    raw = (valor or "").strip().replace(".", "").replace(",", ".")
    try:
        v = float(raw) if raw else 0.0
    except Exception:
        v = 0.0

    txt = build_social_proof_text(servico=servico, valor=v, cidade=cidade, detalhe=detalhe)

    ctx: Dict = {
        "request": request,
        "now": datetime.now(timezone.utc),
        "user": user,
        "is_pro": bool(getattr(user, "is_pro", False)),
        "form": {"servico": servico, "valor": valor, "cidade": cidade, "detalhe": detalhe},
        "result_text": txt,
    }
    return templates.TemplateResponse("social_proof/social_proof.html", ctx)


@router.post("/export/pdf")
def social_proof_export_pdf(
    request: Request,
    servico: str = Form(default=""),
    valor: str = Form(default=""),
    cidade: str = Form(default=""),
    detalhe: str = Form(default=""),
):
    user_or_redirect = _require_login(request)
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    user: User = user_or_redirect

    pro_guard = _require_pro(user)
    if pro_guard:
        return pro_guard

    raw = (valor or "").strip().replace(".", "").replace(",", ".")
    try:
        v = float(raw) if raw else 0.0
    except Exception:
        v = 0.0

    pdf_io = export_pdf(servico=servico, valor=v, cidade=cidade, detalhe=detalhe)

    filename = "prova-social.pdf"
    return StreamingResponse(
        pdf_io,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/pptx")
def social_proof_export_pptx(
    request: Request,
    servico: str = Form(default=""),
    valor: str = Form(default=""),
    cidade: str = Form(default=""),
    detalhe: str = Form(default=""),
):
    user_or_redirect = _require_login(request)
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    user: User = user_or_redirect

    pro_guard = _require_pro(user)
    if pro_guard:
        return pro_guard

    raw = (valor or "").strip().replace(".", "").replace(",", ".")
    try:
        v = float(raw) if raw else 0.0
    except Exception:
        v = 0.0

    pptx_io = export_pptx(servico=servico, valor=v, cidade=cidade, detalhe=detalhe)

    filename = "prova-social.pptx"
    return StreamingResponse(
        pptx_io,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )