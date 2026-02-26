from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc

from app.core.deps import pop_flashes, redirect, get_user_id_from_request
from app.db.session import SessionLocal
from app.models.user import User
from app.models.budget import Budget

router = APIRouter(prefix="/app")
templates = Jinja2Templates(directory="app/templates")


def _require_user(request: Request) -> int:
    uid = get_user_id_from_request(request)
    if not uid:
        return 0
    try:
        return int(uid)
    except:
        return 0


def _norm(s):
    return (s or "").strip().lower()


@router.get("/retention", response_class=HTMLResponse)
def retention_page(request: Request):

    flashes = pop_flashes(request)

    uid = _require_user(request)

    if not uid:
        return redirect("/login", kind="error", message="Faça login novamente")

    now = datetime.now(timezone.utc)

    start = now - timedelta(days=7)

    with SessionLocal() as db:

        user = db.get(User, uid)

        if not user:
            return redirect("/login", kind="error", message="Faça login novamente")

        budgets = list(
            db.scalars(
                select(Budget)
                .where(Budget.user_id == uid)
                .order_by(desc(Budget.created_at))
            ).all()
        )

    last = []

    for b in budgets:
        if not b.created_at:
            continue

        dt = b.created_at.replace(tzinfo=timezone.utc)

        if dt >= start:
            last.append(b)

    created_count = len(last)

    won = [b for b in last if _norm(b.status) == "won"]
    lost = [b for b in last if _norm(b.status) == "lost"]
    awaiting = [b for b in last if _norm(b.status) == "awaiting"]

    closed_count = len(won)
    lost_count = len(lost)
    awaiting_count = len(awaiting)

    conversion = (closed_count / created_count * 100) if created_count > 0 else 0

    report_text = (
        f"📊 RELATÓRIO SEMANAL — {start.strftime('%d/%m/%Y')} a {now.strftime('%d/%m/%Y')}\n\n"
        f"Orçamentos criados: {created_count}\n"
        f"Fechados: {closed_count}\n"
        f"Aguardando: {awaiting_count}\n"
        f"Perdidos: {lost_count}\n"
        f"Taxa de conversão: {conversion:.1f}%\n\n"
        f"Ação simples:\n"
        f"- Faça follow-up nos aguardando\n"
        f"- Quem responde rápido fecha mais\n"
    )

    return templates.TemplateResponse(
        "retention/retention.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "now": now,
            "start": start,
            "created_count": created_count,
            "closed_count": closed_count,
            "awaiting_count": awaiting_count,
            "lost_count": lost_count,
            "conversion": conversion,
            "report_text": report_text,
        },
    )