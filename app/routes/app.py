from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc
from jinja2 import TemplateNotFound  # ✅ ADICIONADO (fallback de templates)

from app.core.deps import get_user_id_from_request, redirect, pop_flashes
from app.db.session import SessionLocal
from app.models.user import User
from app.models.budget import Budget
from app.services.budget_service import can_create_budget, create_budget, FREE_LIMIT_TOTAL_BUDGETS
from app.services.whatsapp import build_budget_message, whatsapp_link, followup_message
from app.services.followup import can_followup

router = APIRouter(prefix="/app")
templates = Jinja2Templates(directory="app/templates")


def _require_user(request: Request) -> int:
    uid_raw = get_user_id_from_request(request)
    if not uid_raw:
        raise HTTPException(status_code=401)
    try:
        return int(uid_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401)


def _parse_brl_value(value: str) -> float:
    if not value:
        return 0.0
    s = str(value).strip()
    if not s:
        return 0.0

    s = re.sub(r"[^0-9\.,]", "", s)
    if not s:
        return 0.0

    if "," in s:
        s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    if "." in s:
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            try:
                return float(s)
            except Exception:
                return 0.0
        s = s.replace(".", "")
        try:
            return float(s)
        except Exception:
            return 0.0

    try:
        return float(s)
    except Exception:
        return 0.0


def _money_brl(v: float) -> str:
    s = f"{v:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _month_window_utc(now: datetime) -> tuple[datetime, datetime]:
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return start, end


# ✅ ADICIONADO: fallback de template (não quebra nada que já funciona)
def _render_template(request: Request, names: List[str], context: dict):
    """
    Tenta renderizar o primeiro template existente da lista.
    Isso evita TemplateNotFound quando o arquivo está em outro caminho no deploy.
    """
    last_err: Exception | None = None
    for name in names:
        try:
            return templates.TemplateResponse(name, context)
        except TemplateNotFound as e:
            last_err = e
            continue
    # se nenhum achou, levanta o último erro (vai aparecer no log)
    raise last_err if last_err else TemplateNotFound(names[0] if names else "unknown.html")


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    now = datetime.now(timezone.utc)
    month_start, month_end = _month_window_utc(now)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

        budgets = list(
            db.scalars(
                select(Budget)
                .where(Budget.user_id == uid)
                .order_by(desc(Budget.created_at), desc(Budget.id))
            ).all()
        )

        total = len(budgets)
        remaining = None
        if not user.is_pro:
            remaining = max(0, FREE_LIMIT_TOTAL_BUDGETS - total)

        month_budgets = [
            b for b in budgets
            if b.created_at
            and (b.created_at.replace(tzinfo=timezone.utc) >= month_start)
            and (b.created_at.replace(tzinfo=timezone.utc) < month_end)
        ]

        won = [b for b in month_budgets if (b.status or "").strip().lower() == "won"]
        lost = [b for b in month_budgets if (b.status or "").strip().lower() == "lost"]
        awaiting = [b for b in month_budgets if (b.status or "").strip().lower() == "awaiting"]

        won_value = sum(_parse_brl_value(b.value or "") for b in won)
        lost_value = sum(_parse_brl_value(b.value or "") for b in lost)

        total_month = len(month_budgets)
        conversion_pct = (len(won) / total_month * 100.0) if total_month > 0 else 0.0

        metrics = {
            "month_won_value": _money_brl(won_value),
            "month_won_count": len(won),
            "month_lost_value": _money_brl(lost_value),
            "month_lost_count": len(lost),
            "month_conversion_pct": f"{conversion_pct:.0f}%",
            "month_total_count": len(month_budgets),
            "month_awaiting": len(awaiting),
            "month_awaiting_count": len(awaiting),
        }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "budgets": budgets,
            "total": total,
            "remaining": remaining,
            "can_followup": can_followup,
            "metrics": metrics,
        },
    )


@router.get("/acquisition", response_class=HTMLResponse)
def acquisition_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

        # Aquisição é PRO — FREE vai para /app/upgrade
        if not user.is_pro:
            return redirect(
                "/app/upgrade",
                kind="error",
                message="Esse módulo é exclusivo para usuários Premium.",
            )

    return templates.TemplateResponse(
        "acquisition.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "now": datetime.now(timezone.utc),
            "messages": [],
            "form": {"nicho": "", "cidade": "", "servico": "", "mode": "media"},
            "mode": "media",
        },
    )


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
            return redirect("/login", kind="error", message="Faça login novamente.")

        # POST também precisa bloquear FREE
        if not user.is_pro:
            return redirect(
                "/app/upgrade",
                kind="error",
                message="Esse módulo é exclusivo para usuários Premium.",
            )

    messages = _generate_messages(nicho=nicho, cidade=cidade, servico=servico, mode=mode)

    return templates.TemplateResponse(
        "acquisition.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "now": datetime.now(timezone.utc),
            "messages": messages,
            "form": {"nicho": nicho, "cidade": cidade, "servico": servico, "mode": mode},
            "mode": mode,
        },
    )


# =========================
# ROTAS DO MENU (voltando a funcionar)
# =========================

@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request):
    # Se você quiser no futuro uma página onboarding.html, troca aqui.
    return RedirectResponse(url="/app", status_code=302)


@router.get("/invite", response_class=HTMLResponse)
def invite_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    invite_link = "https://fecha-instalacao.onrender.com/signup"
    copy_count = 0
    click_count = 0
    share_text = "Vem testar o sistema: https://fecha-instalacao.onrender.com/signup"

    # ✅ fallback de template (caso esteja em outro caminho no deploy)
    context = {
        "request": request,
        "flashes": flashes,
        "user": user,
        "invite_link": invite_link,
        "copy_count": copy_count,
        "click_count": click_count,
        "share_text": share_text,
    }
    return _render_template(
        request,
        names=["invite/invite.html", "invite.html"],
        context=context,
    )


@router.get("/cases", response_class=HTMLResponse)
def cases_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    # ✅ fallback de template (resolve TemplateNotFound: cases.html)
    context = {"request": request, "flashes": flashes, "user": user}
    return _render_template(
        request,
        names=["cases.html", "cases/cases.html"],
        context=context,
    )


@router.get("/social-proof", response_class=HTMLResponse)
def social_proof_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    # ✅ fallback de template
    context = {"request": request, "flashes": flashes, "user": user}
    return _render_template(
        request,
        names=["social_proof/social_proof.html", "social_proof.html"],
        context=context,
    )


# ✅ NÃO coloque /app/upgrade aqui.
# Ela fica SOMENTE em app/routes/upgrade.py


# =========================
# NOVO ORÇAMENTO
# =========================

@router.get("/budgets/new", response_class=HTMLResponse)
def budgets_new_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

        budgets = list(
            db.scalars(select(Budget).where(Budget.user_id == uid)).all()
        )

        total = len(budgets)
        remaining = None
        if not user.is_pro:
            remaining = max(0, FREE_LIMIT_TOTAL_BUDGETS - total)

    return templates.TemplateResponse(
        "budget_new.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "total": total,
            "remaining": remaining,
            "can_create_budget": can_create_budget,
        },
    )