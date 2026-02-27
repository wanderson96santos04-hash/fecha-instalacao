from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc

from app.core.deps import get_user_id_from_request, redirect, pop_flashes
from app.db.session import SessionLocal
from app.models.user import User
from app.models.budget import Budget
from app.services.budget_service import can_create_budget, FREE_LIMIT_TOTAL_BUDGETS
from app.services.followup import can_followup

router = APIRouter(prefix="/app")
templates = Jinja2Templates(directory="app/templates")


# =========================
# AUTH
# =========================

def _require_user(request: Request) -> int:
    uid_raw = get_user_id_from_request(request)

    if not uid_raw:
        raise HTTPException(status_code=401)

    try:
        return int(uid_raw)
    except:
        raise HTTPException(status_code=401)


# =========================
# HELPERS
# =========================

def _parse_brl_value(value: str) -> float:

    if not value:
        return 0.0

    s = re.sub(r"[^0-9\.,]", "", value)

    if "," in s:
        s = s.replace(".", "").replace(",", ".")
        return float(s)

    if "." in s:
        return float(s)

    return float(s)


def _money_brl(v: float) -> str:

    s = f"{v:,.2f}"

    s = s.replace(",", "X").replace(".", ",").replace("X", ".")

    return f"R$ {s}"


def _month_window_utc(now: datetime):

    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    return start, end


# =========================
# DASHBOARD
# =========================

@router.get("", response_class=HTMLResponse)
def dashboard(request: Request):

    flashes = pop_flashes(request)

    uid = _require_user(request)

    now = datetime.now(timezone.utc)

    month_start, month_end = _month_window_utc(now)

    with SessionLocal() as db:

        user = db.get(User, uid)

        if not user:
            return redirect("/login")

        budgets = list(
            db.scalars(
                select(Budget)
                .where(Budget.user_id == uid)
                .order_by(desc(Budget.created_at))
            )
        )

        total = len(budgets)

        remaining = None

        if not user.is_pro:
            remaining = max(0, FREE_LIMIT_TOTAL_BUDGETS - total)

        month_budgets = [

            b for b in budgets

            if month_start <= b.created_at.replace(tzinfo=timezone.utc) < month_end

        ]

        won = [b for b in month_budgets if b.status == "won"]

        lost = [b for b in month_budgets if b.status == "lost"]

        awaiting = [b for b in month_budgets if b.status == "awaiting"]

        won_value = sum(_parse_brl_value(b.value or "0") for b in won)

        lost_value = sum(_parse_brl_value(b.value or "0") for b in lost)

        total_month = len(month_budgets)

        conversion_pct = (

            len(won) / total_month * 100 if total_month > 0 else 0

        )

        metrics = {

            "month_won_value": _money_brl(won_value),

            "month_lost_value": _money_brl(lost_value),

            "month_conversion_pct": f"{conversion_pct:.0f}%",

            "month_total_count": total_month,

            "month_awaiting": len(awaiting),

        }

    return templates.TemplateResponse(

        "dashboard.html",

        {

            "request": request,

            "user": user,

            "budgets": budgets,

            "remaining": remaining,

            "metrics": metrics,

            "flashes": flashes,

            "can_followup": can_followup,

        },

    )


# =========================
# AQUISIÇÃO PAGE
# =========================

@router.get("/acquisition", response_class=HTMLResponse)
def acquisition_page(request: Request):

    flashes = pop_flashes(request)

    uid = _require_user(request)

    with SessionLocal() as db:

        user = db.get(User, uid)

        if not user:
            return redirect("/login")

        if not user.is_pro:

            return redirect("/app/upgrade")

    return templates.TemplateResponse(

        "acquisition.html",

        {

            "request": request,

            "user": user,

            "flashes": flashes,

            "messages": [],

            "form": {"nicho": "", "cidade": "", "servico": "", "mode": "media"},

            "mode": "media",

            "now": datetime.now(timezone.utc),

        },

    )


# =========================
# GERADOR PROFISSIONAL 10/10
# =========================

def _generate_messages(nicho: str, cidade: str, servico: str, mode: str) -> List[str]:

    nicho = (nicho or "").strip()

    cidade = (cidade or "").strip()

    servico = (servico or "").strip()

    mode = (mode or "media").strip().lower()

    base = {

        "curta": [

            f"Olá! Trabalho com {servico} em {cidade}. Posso te enviar uma estimativa gratuita?",

            f"Oi! Atendo clientes de {nicho} em {cidade}. Quer saber quanto custaria o {servico} no seu caso?",

            f"Olá! Faço {servico} em {cidade}. Posso te passar um valor aproximado sem compromisso.",

            f"Boa tarde! Você já considerou {servico}? Posso te explicar rapidamente como funciona em {cidade}.",

            f"Olá! Muitos clientes em {cidade} estão procurando {servico}. Quer que eu te envie uma estimativa?",

            f"Oi! Trabalho com {servico} na região de {cidade}. Posso te mandar uma simulação gratuita.",

            f"Olá! Posso te passar uma orientação rápida sobre {servico} em {cidade}. Sem compromisso.",

            f"Oi! Atendo projetos de {servico} em {cidade}. Quer ver quanto ficaria no seu caso?",

            f"Olá! Posso te mostrar quanto você economizaria com {servico} em {cidade}.",

            f"Boa tarde! Faço {servico} em {cidade}. Quer receber uma estimativa gratuita?",

        ],

        "media": [

            f"Olá! Tudo bem? Trabalho com {servico} em {cidade}. Posso te enviar uma estimativa gratuita baseada no seu perfil?",

            f"Oi! Atendo clientes que buscam {servico} em {cidade}. Posso te passar uma simulação rápida sem compromisso.",

            f"Olá! Faço projetos de {servico} em {cidade}. Muitos clientes conseguem ótimo custo-benefício. Quer que eu te envie uma estimativa?",

            f"Boa tarde! Posso te explicar rapidamente como funciona o {servico} e quanto ficaria em média no seu caso em {cidade}.",

            f"Olá! Trabalho com {servico} na região de {cidade}. Posso te enviar uma previsão de investimento e retorno.",

            f"Oi! Atendo projetos de {nicho} em {cidade}. Posso te mandar uma orientação inicial e estimativa gratuita.",

            f"Olá! Muitos clientes em {cidade} estão procurando {servico}. Posso te mostrar quanto ficaria no seu caso.",

            f"Boa tarde! Posso te enviar uma simulação personalizada de {servico} para sua realidade em {cidade}.",

            f"Olá! Faço atendimento especializado em {servico}. Quer receber uma estimativa sem compromisso?",

            f"Oi! Posso te enviar uma projeção realista de custo e benefício do {servico} em {cidade}.",

        ],

        "agressiva": [

            f"Olá! Trabalho com {servico} em {cidade}. Posso te enviar uma estimativa gratuita hoje mesmo.",

            f"Oi! Muitos clientes em {cidade} estão iniciando {servico}. Posso te mostrar quanto ficaria no seu caso.",

            f"Olá! Posso te enviar uma simulação completa de {servico} com valores atualizados.",

            f"Boa tarde! Faço {servico} em {cidade}. Quer receber uma estimativa sem compromisso?",

            f"Olá! Posso te mostrar quanto você economizaria com {servico}.",

            f"Oi! Atendo clientes em {cidade}. Posso te enviar uma previsão de investimento.",

            f"Olá! Trabalho com instalação profissional de {servico}. Quer ver uma estimativa?",

            f"Boa tarde! Posso te enviar uma simulação gratuita e personalizada.",

            f"Olá! Posso te explicar rapidamente os valores do {servico} em {cidade}.",

            f"Oi! Quer receber uma estimativa gratuita e sem compromisso?",

        ],

    }

    return base.get(mode, base["media"])


# =========================
# POST GERAR
# =========================

@router.post("/acquisition/generate", response_class=HTMLResponse)
def acquisition_generate(

    request: Request,

    nicho: str = Form(...),

    cidade: str = Form(...),

    servico: str = Form(...),

    mode: str = Form("media"),

):

    flashes = pop_flashes(request)

    uid = _require_user(request)

    with SessionLocal() as db:

        user = db.get(User, uid)

        if not user:
            return redirect("/login")

        if not user.is_pro:
            return redirect("/app/upgrade")

    messages = _generate_messages(nicho, cidade, servico, mode)

    return templates.TemplateResponse(

        "acquisition.html",

        {

            "request": request,

            "user": user,

            "flashes": flashes,

            "messages": messages,

            "form": {

                "nicho": nicho,

                "cidade": cidade,

                "servico": servico,

                "mode": mode,

            },

            "mode": mode,

            "now": datetime.now(timezone.utc),

        },

    )