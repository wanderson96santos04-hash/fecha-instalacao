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
from app.models.budget import Budget  # no seu projeto é esse


router = APIRouter(prefix="/app/retention", tags=["retention"])
templates = Jinja2Templates(directory="app/templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fmt_date_br(dt: datetime) -> str:
    # mantém UTC como você já usa nos módulos
    return dt.astimezone(timezone.utc).strftime("%d/%m/%Y")


def _week_window_utc(now: datetime) -> Tuple[datetime, datetime]:
    """
    Janela: últimos 7 dias (inclui hoje).
    Ex.: start = now - 7 dias
    """
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
    """
    Retenção — Relatório semanal do usuário logado (últimos 7 dias):
    - criados
    - fechados (won)
    - perdidos (lost)
    - aguardando (awaiting)
    - taxa de conversão = won / criados
    """

    flashes = pop_flashes(request)
    user = _get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    now = datetime.now(timezone.utc)
    start, end = _week_window_utc(now)

    # carrega todos os budgets da janela (mais confiável do que 4 counts soltos, e ainda é leve)
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

    # seus status reais:
    # - awaiting
    # - won
    # - lost
    won_count = sum(1 for b in budgets if (b.status or "").strip().lower() == "won")
    lost_count = sum(1 for b in budgets if (b.status or "").strip().lower() == "lost")
    awaiting_count = sum(1 for b in budgets if (b.status or "").strip().lower() == "awaiting")

    # ✅ conversão semanal: fechados / criados
    conversion = _pct(won_count, created_count)

    # texto (bem “copiável” e alinhado com o card)
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

    # ✅ “anti-bug”: se o template estiver usando outro nome, ainda assim aparece certo.
    ctx: Dict = {
        "request": request,
        "flashes": flashes,
        "user": user,
        "now": now,
        "start": start,
        "end": end,

        # números base
        "created_count": created_count,
        "won_count": won_count,
        "lost_count": lost_count,
        "awaiting_count": awaiting_count,

        # conversão em vários formatos/nomes (pra não ficar 0% por chave errada)
        "conversion": conversion,                         # float
        "conversion_pct": conversion,                     # float (alias)
        "conversion_value": conversion,                   # float (alias)
        "conversion_str": f"{conversion:.0f}%",           # "50%"
        "conversion_pct_str": f"{conversion:.0f}%",       # "50%"

        # relatório em texto
        "report_text": report_text,

        # alias caso seu template use nomes curtos
        "created": created_count,
        "closed": won_count,
        "awaiting": awaiting_count,
        "lost": lost_count,
    }

    return templates.TemplateResponse("retention/retention.html", ctx)