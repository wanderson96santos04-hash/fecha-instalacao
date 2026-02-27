from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc

from app.core.deps import get_user_id_from_request
from app.db.session import SessionLocal
from app.models.user import User
from app.models.budget import Budget

router = APIRouter(prefix="/app")
templates = Jinja2Templates(directory="app/templates")


def _require_user_id(request: Request) -> int:
    uid_raw = get_user_id_from_request(request)
    if not uid_raw:
        raise HTTPException(status_code=401)
    try:
        return int(uid_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401)


def _status_norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _fmt_br(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%d/%m/%Y")


@router.get("/retention", response_class=HTMLResponse)
def retention_page(request: Request):
    uid = _require_user_id(request)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return RedirectResponse(url="/login", status_code=302)

        budgets = list(
            db.scalars(
                select(Budget)
                .where(Budget.user_id == uid)
                .order_by(desc(Budget.created_at), desc(Budget.id))
            ).all()
        )

    # janela semanal
    week_budgets = []
    for b in budgets:
        if not b.created_at:
            continue
        dt = b.created_at.replace(tzinfo=timezone.utc)
        if start <= dt <= now:
            week_budgets.append(b)

    created_count = len(week_budgets)

    won = [b for b in week_budgets if _status_norm(getattr(b, "status", None)) == "won"]
    lost = [b for b in week_budgets if _status_norm(getattr(b, "status", None)) == "lost"]
    awaiting = [b for b in week_budgets if _status_norm(getattr(b, "status", None)) == "awaiting"]

    closed_count = len(won)  # “fechado” = won

    conversion = (closed_count / created_count * 100.0) if created_count > 0 else 0.0
    conversion_pct = round(conversion, 1)  # ✅ já arredonda aqui

    report_text = (
        f"📊 RELATÓRIO SEMANAL — {_fmt_br(start)} a {_fmt_br(now)}\n\n"
        f"✅ Orçamentos criados: {created_count}\n"
        f"🟢 Fechados: {len(won)}\n"
        f"🟡 Aguardando: {len(awaiting)}\n"
        f"🔴 Perdidos: {len(lost)}\n"
        f"📈 Taxa de conversão: {conversion_pct:.1f}%\n\n"
        f"🎯 Ação simples (pra subir a conversão):\n"
        f"- Faça 1 follow-up em todos os “Aguardando” (em até 24h).\n"
        f"- Quem responde rápido fecha mais.\n"
    )

    ctx: Dict = {
        "request": request,
        "user": user,
        "now": now,
        "start": start,
        "created_count": created_count,
        "closed_count": closed_count,
        "awaiting_count": len(awaiting),
        "lost_count": len(lost),
        "conversion_pct": conversion_pct,  # ✅ use isso no template
        "report_text": report_text,
    }

    return templates.TemplateResponse("retention/retention.html", ctx)
