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
    """
    Lê o cookie de sessão e devolve o user_id como INT.
    Isso evita erro do Postgres (integer = varchar) em filtros como Budget.user_id == uid.
    """
    uid_raw = get_user_id_from_request(request)
    if not uid_raw:
        raise HTTPException(status_code=401)

    try:
        return int(uid_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401)


def _parse_brl_value(value: str) -> float:
    """
    Converte strings tipo:
      "R$ 1.000" / "1000" / "1.000,50" / "1000,50" / "2500" / "2.500"
    para float (em reais).

    ✅ Corrige o bug clássico:
      "1.000" não pode virar 1.0, tem que virar 1000.0
    """
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

        ok, total = can_create_budget(db, user)
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


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    now = datetime.now(timezone.utc)
    last_6_weeks = now - timedelta(days=42)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

        if not user.is_pro:
            return redirect("/app/upgrade", kind="error", message="Relatórios é Premium.")

        budgets = list(
            db.scalars(
                select(Budget)
                .where(Budget.user_id == uid)
                .order_by(desc(Budget.created_at), desc(Budget.id))
            ).all()
        )

    last_budgets = []
    for b in budgets:
        if not b.created_at:
            continue
        dt = b.created_at.replace(tzinfo=timezone.utc)
        if dt < last_6_weeks:
            continue
        last_budgets.append(b)

    won_budgets = [b for b in last_budgets if (b.status or "").strip().lower() == "won"]
    lost_budgets = [b for b in last_budgets if (b.status or "").strip().lower() == "lost"]

    won_value = sum(_parse_brl_value(b.value or "") for b in won_budgets)
    lost_value = sum(_parse_brl_value(b.value or "") for b in lost_budgets)

    total_last = len(last_budgets)
    conversion = (len(won_budgets) / total_last * 100.0) if total_last > 0 else 0.0

    kpis = {
        "won_value": round(won_value, 2),
        "lost_value": round(lost_value, 2),
        "won": len(won_budgets),
        "lost": len(lost_budgets),
        "conversion": round(conversion, 1),
    }

    week_map: Dict[str, float] = {}
    for b in won_budgets:
        dt = b.created_at.replace(tzinfo=timezone.utc)
        year, week, _ = dt.isocalendar()
        key = f"{year}-W{week:02d}"
        week_map[key] = week_map.get(key, 0.0) + _parse_brl_value(b.value or "")

    week_items = sorted(week_map.items(), key=lambda x: x[0])
    chart_labels = [k for k, _ in week_items] or []
    chart_values = [round(v, 2) for _, v in week_items] or []

    service_map: Dict[str, int] = {}
    for b in won_budgets:
        service = (b.service_type or "").strip() or "Sem categoria"
        service_map[service] = service_map.get(service, 0) + 1

    ranking = sorted(service_map.items(), key=lambda x: x[1], reverse=True)[:8]

    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "flashes": flashes,
            "user": user,
            "kpis": kpis,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "ranking": ranking,
        },
    )


# =========================
# ✅ AQUISIÇÃO (PRO)
# =========================

def _acq_generate(nicho: str, cidade: str, servico: str, mode: str) -> List[str]:
    n = (nicho or "").strip()
    c = (cidade or "").strip()
    s = (servico or "").strip()
    mode = (mode or "media").strip().lower()

    if mode not in {"curta", "media", "agressiva"}:
        mode = "media"

    base = {
        "curta": [
            f"Oi! Vi que você trabalha com *{n}* aí em *{c}*. Você faz *{s}*? Se quiser, eu te mando um orçamento rapidinho.",
            f"Olá! Sou da área de *{s}* e atendo *{c}*. Posso te passar um valor hoje ainda, sem compromisso.",
            f"Oi! Atendo *{c}* com *{s}*. Quer que eu te mande um orçamento por WhatsApp?",
        ],
        "media": [
            f"Olá! Tudo bem? Vi seu trabalho de *{n}* em *{c}* e queria saber se você está pegando serviço de *{s}* agora. Se sim, posso te mandar um orçamento bem rápido.",
            f"Oi! Eu trabalho com *{s}* aqui em *{c}*. Se você quiser, eu faço uma avaliação e já te passo um valor certinho (sem compromisso).",
            f"Olá! Se você estiver em *{c}* e precisar de *{s}*, eu consigo te atender essa semana. Quer que eu te envie uma proposta?",
        ],
        "agressiva": [
            f"Oi! Posso resolver *{s}* pra você em *{c}* ainda essa semana. Me diz: é pra quando? Se me passar os detalhes, eu já fecho um valor agora.",
            f"Olá! Eu faço *{s}* em *{c}*. Se você me confirmar hoje, eu consigo encaixar e finalizar rápido. Quer orçamento agora?",
            f"Oi! Se for *{s}* em *{c}*, eu consigo te atender com prioridade. Me manda só 2 infos e eu já te passo o valor pra fechar.",
        ],
    }

    extras = [
        f"Oi! Vi seu perfil e achei top. Você está em *{c}*? Se precisar de *{s}*, eu consigo te mandar um orçamento ainda hoje.",
        f"Olá! Estou atendendo *{c}* com *{s}*. Quer que eu te passe 2 opções de valor (econômico e completo) pra você escolher?",
        f"Oi! Trabalho com *{s}* em *{c}*. Posso te mandar um valor fechado + prazo. É pra casa ou empresa?",
        f"Olá! Se for *{s}* em *{c}*, eu te mando o orçamento agora e já digo o prazo certinho. Pode ser?",
        f"Oi! Eu faço *{s}* em *{c}* e consigo atendimento rápido. Me diga só: qual tamanho/quantidade pra eu calcular?",
        f"Olá! Você trabalha com *{n}* aí em *{c}*? Tenho uma solução boa pra *{s}* — quer que eu te explique em 30s aqui?",
        f"Oi! Se você estiver em *{c}* e quiser *{s}* com garantia e prazo, me manda uma foto/medida que eu já calculo.",
    ]

    msgs = base[mode] + extras
    return msgs[:10]


@router.get("/acquisition", response_class=HTMLResponse)
def acquisition_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")
        if not user.is_pro:
            return redirect("/app/upgrade", kind="error", message="Aquisição é Premium (PRO).")

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
            return redirect("/app/upgrade", kind="error", message="Aquisição é Premium (PRO).")

    messages = _acq_generate(nicho=nicho, cidade=cidade, servico=servico, mode=mode)

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
# ✅ MAKE ADMIN (TEMP)
# =========================
@router.get("/make-admin")
def make_admin(request: Request):
    """
    Rota temporária para transformar seu usuário em admin.
    Acesse uma vez e depois pode remover.
    """
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
