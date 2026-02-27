from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

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


@router.get("/budgets/new", response_class=HTMLResponse)
def new_budget_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

        ok, total = can_create_budget(db, user)
        if not ok:
            return templates.TemplateResponse(
                "budget_new.html",
                {
                    "request": request,
                    "flashes": flashes,
                    "user": user,
                    "blocked": True,
                    "total": total,
                    "limit": FREE_LIMIT_TOTAL_BUDGETS,
                },
            )

    return templates.TemplateResponse(
        "budget_new.html",
        {"request": request, "flashes": flashes, "user": user, "blocked": False},
    )


@router.post("/budgets/new")
def new_budget_action(
    request: Request,
    client_name: str = Form(...),
    phone: str = Form(...),
    service_type: str = Form(...),
    value: str = Form(...),
    payment_method: str = Form(...),
    notes: str = Form(""),
):
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

        ok, _total = can_create_budget(db, user)
        if not ok:
            return redirect(
                "/app",
                kind="error",
                message=f"Limite do plano Free atingido ({FREE_LIMIT_TOTAL_BUDGETS}). Vire Premium para ilimitado.",
            )

        b = create_budget(
            db,
            user_id=uid,
            client_name=client_name,
            phone=phone,
            service_type=service_type,
            value=value,
            payment_method=payment_method,
            notes=notes,
        )

    return redirect("/app", kind="success", message=f"Orçamento criado para {b.client_name}.")


@router.post("/budgets/{budget_id}/status")
def set_status(request: Request, budget_id: int, status: str = Form(...)):
    uid = _require_user(request)
    status = (status or "").strip().lower()
    if status not in {"awaiting", "won", "lost"}:
        return redirect("/app", kind="error", message="Status inválido.")

    with SessionLocal() as db:
        b = db.get(Budget, budget_id)
        if not b or b.user_id != uid:
            return redirect("/app", kind="error", message="Orçamento não encontrado.")

        b.status = status
        db.commit()

    return redirect("/app", kind="success", message="Status atualizado.")


@router.get("/budgets/{budget_id}/whatsapp")
def send_whatsapp(request: Request, budget_id: int):
    uid = _require_user(request)
    with SessionLocal() as db:
        b = db.get(Budget, budget_id)
        if not b or b.user_id != uid:
            return redirect("/app", kind="error", message="Orçamento não encontrado.")

        msg = build_budget_message(
            client_name=b.client_name,
            service_type=b.service_type,
            value=b.value,
            payment_method=b.payment_method,
            notes=b.notes or "",
        )
        url = whatsapp_link(b.phone, msg)

    return RedirectResponse(url=url, status_code=302)


@router.get("/budgets/{budget_id}/followup")
def followup_whatsapp(request: Request, budget_id: int):
    uid = _require_user(request)
    with SessionLocal() as db:
        b = db.get(Budget, budget_id)
        if not b or b.user_id != uid:
            return redirect("/app", kind="error", message="Orçamento não encontrado.")
        if not can_followup(b.created_at):
            return redirect("/app", kind="error", message="O follow-up libera após 24h do orçamento.")

        url = whatsapp_link(b.phone, followup_message(b.client_name))

    return RedirectResponse(url=url, status_code=302)


@router.get("/upgrade", response_class=HTMLResponse)
def upgrade_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

        if user.is_pro:
            return redirect("/app", kind="success", message="Você já é Premium.")

    return templates.TemplateResponse(
        "upgrade.html",
        {"request": request, "flashes": flashes, "user": user},
    )


@router.get("/checkout")
def checkout_redirect(request: Request):
    uid = _require_user(request)

    checkout_url = (os.getenv("KIWIFY_CHECKOUT_URL") or "").strip()
    if not checkout_url:
        return redirect("/app/upgrade", kind="error", message="Checkout da Kiwify não configurado.")

    sep = "&" if "?" in checkout_url else "?"
    url = f"{checkout_url}{sep}ref=uid_{uid}"
    return RedirectResponse(url=url, status_code=302)


# =========================
# ✅ AQUISIÇÃO (PRO)
# =========================

def _build_acquisition_messages(nicho: str, cidade: str, servico: str, mode: str) -> List[str]:
    nicho = nicho.strip()
    cidade = cidade.strip()
    servico = servico.strip()
    mode = (mode or "media").strip().lower()

    if mode == "curta":
        templates_list = [
            f"Oi! Vi que você trabalha com {nicho} em {cidade}. Você já tem alguém cuidando de {servico} com garantia e prazo? Se quiser, te passo uma proposta rápida.",
            f"Olá! {servico} para {nicho} em {cidade}: consigo te atender essa semana. Quer que eu te mande valores e prazo?",
            f"Fala! Atendo {servico} aí em {cidade}. Qual o melhor horário pra eu te mandar uma estimativa e tirar 2 dúvidas rápidas?",
            f"Oi, tudo bem? Trabalho com {servico} focado em {nicho} em {cidade}. Posso te mandar uma opção de orçamento hoje?",
            f"Olá! Você tem demanda de {servico} aí em {cidade}? Se sim, me diga só o tipo e eu te retorno com prazo e valor.",
            f"Oi! {cidade} — {servico} para {nicho}. Se você me disser o tamanho/quantidade, eu já te passo uma base agora.",
            f"Olá! Estou com agenda aberta em {cidade}. Quer que eu te envie uma proposta de {servico} para {nicho}?",
            f"Fala! Se você precisar de {servico} (nicho {nicho}) em {cidade}, eu resolvo do começo ao fim. Quer detalhes?",
            f"Oi! Posso te atender em {cidade} com {servico}. Se preferir, mando um orçamento em 3 linhas agora.",
            f"Olá! Você quer reduzir dor de cabeça com {servico} no seu {nicho}? Me diz “sim” que eu te mando a proposta.",
        ]
        return templates_list

    if mode == "agressiva":
        templates_list = [
            f"Oi! {cidade}. Eu cuido de {servico} pra {nicho} com prazo fechado e garantia. Se eu te mandar um orçamento hoje, você consegue me responder ainda hoje?",
            f"Olá — trabalho com {servico} pra {nicho} em {cidade}. Tenho 2 horários livres essa semana. Quer reservar antes que feche a agenda?",
            f"Fala! Se {servico} tá travando algo aí no seu {nicho} em {cidade}, eu resolvo rápido. Me diz o que precisa e eu já te passo prazo + valor.",
            f"Oi! Eu consigo iniciar {servico} em {cidade} em até 48h (dependendo do volume). Quer que eu mande a proposta agora?",
            f"Olá! {servico} pra {nicho} em {cidade}: faço com checklist e entrego pronto. Se eu te mandar valores, você decide hoje?",
            f"Fala! Tenho um pacote direto pra {nicho} em {cidade} (inclui {servico}). Quer receber 2 opções: econômica e completa?",
            f"Oi! Posso assumir {servico} aí em {cidade} e te livrar disso essa semana. Qual a melhor forma: te mando no WhatsApp ou aqui mesmo?",
            f"Olá! Se você quer fechar {servico} sem enrolação: me diga o tamanho/quantidade e eu envio um preço fechado agora.",
            f"Fala! Atendo {nicho} em {cidade}. Se você topar, eu te mando proposta + garantia + prazo ainda hoje e você só aprova.",
            f"Oi! Se {servico} é prioridade no seu {nicho} em {cidade}, eu consigo te atender primeiro. Quer que eu te ligue 2 minutos ou prefere texto?",
        ]
        return templates_list

    # mode == "media"
    templates_list = [
        f"Oi! Tudo bem? Eu trabalho com {servico} voltado pra {nicho} aí em {cidade}. Posso te fazer 2 perguntas rápidas pra entender e te mandar um orçamento certinho?",
        f"Olá! Vi seu negócio na área de {nicho} em {cidade}. Eu ajudo com {servico} com garantia e prazos bem alinhados. Quer que eu te envie uma proposta?",
        f"Fala! Atendo {cidade} com {servico} pra {nicho}. Você já tem alguém cuidando disso ou ainda está cotando?",
        f"Oi! Posso te ajudar com {servico} aí em {cidade}. Qual seria o objetivo principal: reduzir custo, melhorar qualidade ou ganhar velocidade?",
        f"Olá! Trabalho com {servico} para clientes de {nicho} em {cidade}. Se você me disser o tamanho/quantidade, eu te mando 2 opções (básica e completa).",
        f"Fala! Tenho um processo bem simples: você me passa as infos, eu envio proposta e, se fizer sentido, já agendamos. Quer seguir assim para {servico} em {cidade}?",
        f"Oi! Em {cidade}, eu faço {servico} com foco em {nicho}. Você prefere que eu te mande um orçamento “fechado” ou uma estimativa primeiro?",
        f"Olá! Se você estiver cotando {servico} pra {nicho} aí em {cidade}, posso te mandar uma proposta rápida hoje e ajustar conforme sua necessidade.",
        f"Fala! Eu atendo {nicho} em {cidade} e consigo te orientar no melhor caminho pra {servico}. Quer que eu te envie um resumo com prazo + valor?",
        f"Oi! Pra não tomar seu tempo: me diga só (1) bairro/área em {cidade} e (2) o que você precisa em {servico}. Aí eu te retorno com orçamento.",
    ]
    return templates_list


@router.get("/acquisition", response_class=HTMLResponse)
def acquisition_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

        if not user.is_pro:
            return redirect("/app/upgrade", kind="error", message="Aquisição é Premium.")

    return templates.TemplateResponse(
        "acquisition.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "now": datetime.now(timezone.utc),
            "messages": [],
            "form": {"nicho": "", "cidade": "", "servico": "", "mode": "media"},
        },
    )


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
        if not user.is_pro:
            return redirect("/app/upgrade", kind="error", message="Aquisição é Premium.")

    messages = _build_acquisition_messages(nicho=nicho, cidade=cidade, servico=servico, mode=mode)

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
# ✅ ROTA TEMPORÁRIA: MAKE ADMIN + PRO
# =========================
@router.get("/make-admin")
def make_admin(request: Request):
    user_id = get_user_id_from_request(request)
    if not user_id:
        return {"error": "not logged"}

    with SessionLocal() as db:
        user = db.get(User, int(user_id))
        if not user:
            return {"error": "user not found"}

        user.is_admin = True
        user.is_pro = True
        db.commit()

    return {"success": True, "message": "Você agora é admin e premium"}
