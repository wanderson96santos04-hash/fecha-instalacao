from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc

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
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    # Estado básico para o template não quebrar
    state = {
        "step1_done": False,
        "step2_done": False,
        "step3_done": False,
        "completed": False,
    }

    return templates.TemplateResponse(
        "onboarding/onboarding.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "state": state,
            "now": datetime.now(timezone.utc),
        },
    )


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

    return templates.TemplateResponse(
        "invite/invite.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "invite_link": invite_link,
            "copy_count": copy_count,
            "click_count": click_count,
            "share_text": share_text,
        },
    )


@router.get("/cases", response_class=HTMLResponse)
def cases_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    # Página pública de depoimentos: por enquanto sem banco (não quebra nada)
    items: List[Dict] = []

    return templates.TemplateResponse(
        "cases/cases.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "items": items,
            "now": datetime.now(timezone.utc),
        },
    )


# ✅ CORREÇÃO PRINCIPAL: rotas do ADMIN que estavam dando 404
@router.get("/cases/admin", response_class=HTMLResponse)
def cases_admin_list(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    items: List[Dict] = []

    return templates.TemplateResponse(
        "cases/admin_list.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "items": items,
            "now": datetime.now(timezone.utc),
        },
    )


@router.get("/cases/admin/new", response_class=HTMLResponse)
def cases_admin_new(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    return templates.TemplateResponse(
        "cases/admin_new.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "now": datetime.now(timezone.utc),
        },
    )


@router.post("/cases/admin/new")
def cases_admin_new_post(request: Request):
    # Safe: não quebra o sistema mesmo sem banco.
    return RedirectResponse(url="/app/cases/admin", status_code=302)


@router.get("/cases/admin/edit/{item_id}", response_class=HTMLResponse)
def cases_admin_edit(request: Request, item_id: int):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    item = None

    return templates.TemplateResponse(
        "cases/admin_edit.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "item": item,
            "item_id": item_id,
            "now": datetime.now(timezone.utc),
        },
    )


@router.post("/cases/admin/edit/{item_id}")
def cases_admin_edit_post(request: Request, item_id: int):
    return RedirectResponse(url="/app/cases/admin", status_code=302)


@router.get("/cases/export", response_class=HTMLResponse)
def cases_export(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    # Se seu export.html for só uma página, isso resolve.
    return templates.TemplateResponse(
        "cases/export.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "now": datetime.now(timezone.utc),
        },
    )


@router.get("/social-proof", response_class=HTMLResponse)
def social_proof_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    return templates.TemplateResponse(
        "social_proof/social_proof.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "form": {"servico": "", "valor": "", "cidade": "", "detalhe": ""},
            "result": "",
            "now": datetime.now(timezone.utc),
        },
    )


# ✅ CORREÇÃO: rota do botão "Gerar prova social" (POST) estava 404
@router.post("/social-proof/generate", response_class=HTMLResponse)
def social_proof_generate(
    request: Request,
    servico: str = Form(""),
    valor: str = Form(""),
    cidade: str = Form(""),
    detalhe: str = Form(""),
):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    servico_s = (servico or "").strip()
    valor_s = (valor or "").strip()
    cidade_s = (cidade or "").strip()
    detalhe_s = (detalhe or "").strip()

    partes = []
    if servico_s:
        partes.append(f"Serviço fechado: {servico_s}")
    if valor_s:
        partes.append(f"Valor: {valor_s}")
    if cidade_s:
        partes.append(f"Cidade: {cidade_s}")
    if detalhe_s:
        partes.append(f"Detalhe: {detalhe_s}")

    if partes:
        result = "✅ Prova social pronta:\n" + " • ".join(partes)
    else:
        result = "Preencha o formulário para gerar a prova social."

    return templates.TemplateResponse(
        "social_proof/social_proof.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "form": {"servico": servico_s, "valor": valor_s, "cidade": cidade_s, "detalhe": detalhe_s},
            "result": result,
            "now": datetime.now(timezone.utc),
        },
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