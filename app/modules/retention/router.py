from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.session import SessionLocal
from app.models.user import User

# tenta importar seu model de orçamento com alguns nomes comuns
BUDGET_MODEL = None
try:
    from app.models.budget import Budget  # type: ignore
    BUDGET_MODEL = Budget
except Exception:
    try:
        from app.models.budgets import Budget  # type: ignore
        BUDGET_MODEL = Budget
    except Exception:
        try:
            from app.models.orcamento import Orcamento as Budget  # type: ignore
            BUDGET_MODEL = Budget
        except Exception:
            BUDGET_MODEL = None

router = APIRouter(prefix="/app", tags=["Retention"])
templates = Jinja2Templates(directory="app/templates")


def _pct(n: int, d: int) -> float:
    if d <= 0:
        return 0.0
    return (n / d) * 100.0


def _fmt_br(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%d/%m/%Y")


@router.get("/retention", response_class=HTMLResponse)
def retention_weekly_report(request: Request):
    """
    Relatório semanal (últimos 7 dias) baseado nos orçamentos do usuário logado.
    Não altera dados, apenas consulta.
    """

    # --- pega user_id do cookie/sessão (usa sua deps existente)
    try:
        from app.core.deps import get_user_id_from_request  # seu arquivo já tem isso (você mostrou)
    except Exception:
        # se esse import falhar, é porque sua deps mudou de lugar
        return HTMLResponse("Erro: não encontrei app.core.deps.get_user_id_from_request", status_code=500)

    user_id: Optional[str] = get_user_id_from_request(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    # --- valida model Budget
    if BUDGET_MODEL is None:
        return HTMLResponse(
            "Erro: não encontrei o model de Orçamento (Budget/Orcamento). "
            "Procure o nome certo em app/models e ajuste o import no router.",
            status_code=500,
        )

    # --- janela semanal (últimos 7 dias)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)

    # --- consultas
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == int(user_id)).first()

        # Nomes de campos mais comuns
        # created_at: datetime
        # user_id: int
        # status: str (aguardando/fechado/perdido)
        Budget = BUDGET_MODEL

        # Ajuste aqui se seu campo não for "created_at"
        created_field = getattr(Budget, "created_at", None)
        user_field = getattr(Budget, "user_id", None)
        status_field = getattr(Budget, "status", None)

        if created_field is None or user_field is None or status_field is None:
            return HTMLResponse(
                "Erro: seu model de orçamento não tem algum campo esperado: user_id / status / created_at. "
                "Abra o model e ajuste esses nomes no router.",
                status_code=500,
            )

        # criados na semana
        created_count = (
            db.query(Budget)
            .filter(user_field == int(user_id))
            .filter(created_field >= start)
            .count()
        )

        # fechados na semana (suporta variações de texto)
        CLOSED_VALUES = {"fechado", "fechados", "closed", "won", "ganho"}
        closed_count = (
            db.query(Budget)
            .filter(user_field == int(user_id))
            .filter(created_field >= start)
            .filter(status_field.in_(list(CLOSED_VALUES)))
            .count()
        )

        conversion = _pct(closed_count, created_count)

    # --- relatório em texto formatado
    report_text = (
        f"📊 RELATÓRIO SEMANAL — {_fmt_br(start)} a {_fmt_br(now)}\n\n"
        f"✅ Orçamentos criados: {created_count}\n"
        f"🔥 Orçamentos fechados: {closed_count}\n"
        f"📈 Taxa de conversão: {conversion:.1f}%\n\n"
        f"🎯 Meta simples:\n"
        f"- Se você aumentar +1 follow-up por orçamento, a conversão costuma subir.\n"
        f"- Use o botão COPIAR e envie pro WhatsApp/cliente/equipe.\n"
    )

    ctx: Dict = {
        "request": request,
        "now": now,
        "start": start,
        "created_count": created_count,
        "closed_count": closed_count,
        "conversion": conversion,
        "report_text": report_text,
        "user": user,
        "is_pro": bool(getattr(user, "is_pro", False)) if user else False,
    }

    return templates.TemplateResponse("retention/retention.html", ctx)