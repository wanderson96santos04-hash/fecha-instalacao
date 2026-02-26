from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_user_id_from_request, pop_flashes
from app.db.session import SessionLocal
from app.models.user import User
from app.models.budget import Budget

router = APIRouter(prefix="/app/retention", tags=["retention"])
templates = Jinja2Templates(directory="app/templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fmt_date_br(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%d/%m/%Y")


def _week_window_utc(now: datetime) -> Tuple[datetime, datetime]:
    start = now - timedelta(days=7)
    return start, now


def _pct(n: int, d: int) -> float:
    if d <= 0:
        return 0.0
    return (n / d) * 100.0


def _get_current_user(request: Request, db: Session) -> User | None:
    uid_raw = get_user_id_from_request(request)
    if not uid_raw:
        return None
    try:
        uid = int(uid_raw)
    except Exception:
        return None
    return db.get(User, uid)


@router.get("", response_class=HTMLResponse)
def retention_weekly_report(request: Request, db: Session = Depends(get_db)):
    flashes = pop_flashes(request)
    user = _get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    now = datetime.now(timezone.utc)
    start, end = _week_window_utc(now)

    budgets = list(
        db.scalars(
            select(Budget).where(
                Budget.user_id == user.id,
                Budget.created_at >= start,
                Budget.created_at <= end,
            )
        ).all()
    )

    created_count = len(budgets)

    won_count = sum(1 for b in budgets if (b.status or "").strip().lower() == "won")
    lost_count = sum(1 for b in budgets if (b.status or "").strip().lower() == "lost")
    awaiting_count = sum(1 for b in budgets if (b.status or "").strip().lower() == "awaiting")

    conversion = _pct(won_count, created_count)

    report_text = (
        f"📊 RELATÓRIO SEMANAL — {_fmt_date_br(start)} a {_fmt_date_br(now)}\n\n"
        f"✅ Orçamentos criados: {created_count}\n"
        f"🟢 Fechados: {won_count}\n"
        f"🟡 Aguardando: {awaiting_count}\n"
        f"🔴 Perdidos: {lost_count}\n"
        f"📈 Taxa de conversão: {conversion:.1f}%\n\n"
        f"🎯 Ação simples (pra subir a conversão):\n"
        f"- Faça 1 follow-up em todos os “Aguardando” (em até 24h).\n"
        f"- Quem responde rápido fecha mais.\n"
    )

    # ✅ ALIASES (pra bater com qualquer template antigo/novo)
    conversion_str_0 = f"{conversion:.0f}%"
    conversion_str_1 = f"{conversion:.1f}%"

    ctx: Dict = {
        "request": request,
        "flashes": flashes,
        "user": user,
        "now": now,
        "start": start,
        "end": end,

        # nomes principais
        "created_count": created_count,
        "won_count": won_count,
        "lost_count": lost_count,
        "awaiting_count": awaiting_count,
        "conversion": conversion,
        "report_text": report_text,

        # ✅ nomes MUITO usados em template (cards)
        "closed_count": won_count,               # se o card usa closed_count
        "closed": won_count,                     # se o card usa closed
        "lost": lost_count,
        "awaiting": awaiting_count,
        "created": created_count,

        # ✅ conversão em vários nomes
        "conversion_pct": conversion,            # se usa conversion_pct (float)
        "conversion_percentage": conversion,     # alias
        "conversion_rate": conversion,           # alias
        "conversion_str": conversion_str_0,      # "50%"
        "conversion_pct_str": conversion_str_0,  # "50%"
        "conversion_display": conversion_str_0,  # "50%"
        "conversion_display_1": conversion_str_1 # "50.0%"
    }

    return templates.TemplateResponse("retention/retention.html", ctx)