from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple

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


def _month_window_utc(now: datetime) -> Tuple[datetime, datetime]:
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _render_first_existing(template_names: List[str], ctx: Dict, status_code: int = 200):
    """
    Tenta renderizar o primeiro template que existir.
    Se nenhum existir, devolve erro claro (pra não ficar 500 genérico).
    """
    last_err = None
    for name in template_names:
        try:
            templates.env.get_template(name)
            return templates.TemplateResponse(name, ctx, status_code=status_code)
        except Exception as e:
            last_err = e
            continue

    return HTMLResponse(
        f"Template não encontrado. Tentei: {template_names}. Detalhe: {last_err}",
        status_code=500,
    )


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


# =========================
# BUDGETS
# =========================
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


# =========================
# UPGRADE / CHECKOUT
# =========================
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
# AQUISIÇÃO
# =========================
def _generate_acquisition_messages(nicho: str, cidade: str, servico: str, mode: str) -> List[str]:
    n = nicho.strip()
    c = cidade.strip()
    s = servico.strip()
    m = (mode or "media").strip().lower()

    if m == "curta":
        base = [
            f"Oi! Vi que você trabalha com {n} em {c}. Você atende {s}? Posso te mostrar uma ideia rápida.",
            f"Olá! {n} em {c}: vocês fazem {s}? Se sim, posso te mandar uma mensagem pronta.",
            f"Oi 👋 Trabalho com {n} em {c}. Posso te enviar uma abordagem rápida sobre {s}?",
        ]
    elif m == "agressiva":
        base = [
            f"Fala! {n} em {c}. Dá pra aumentar fechamento de {s} com um ajuste simples. Quer que eu te mostre?",
            f"Oi! Se vocês atendem {s} em {c}, eu te mando um roteiro pra fechar mais. Posso enviar?",
            f"Olá — {n} em {c} tem demanda de {s}. Quer um plano rápido pra captar mais?",
        ]
    else:
        base = [
            f"Oi, tudo bem? Vi seu trabalho com {n} em {c}. Vocês oferecem {s}? Posso te mandar uma sugestão pra captar mais clientes.",
            f"Olá! Eu ajudo negócios de {n} em {c} a melhorar a prospecção. Posso te mandar uma mensagem modelo pra {s}?",
            f"Oi 👋 Você atende {s} em {c}? Se sim, posso compartilhar um texto de WhatsApp que costuma gerar respostas.",
        ]

    extras = [
        f"Oi! Você é de {c}? Vi que atua com {n}. Posso te enviar 3 mensagens prontas pra {s}?",
        f"Olá! Para {n} em {c}, {s} costuma ter boa procura. Quer 5 abordagens pra testar hoje?",
        f"Oi 👋 Rapidinho: vocês atendem {s}? Se sim, te mando uma abordagem pronta para {n} em {c}.",
        f"Olá! Quer que eu te mande agora um texto curto e outro médio pra prospectar {s} em {c}?",
        f"Oi! Se você trabalha com {n} em {c}, posso te mandar um roteiro simples pra fechar mais {s}. Quer receber?",
        f"Olá 👋 Posso te enviar uma mensagem que aumenta resposta no WhatsApp para {s} (nicho {n}, cidade {c}).",
        f"Oi! Quer 10 mensagens diferentes pra abordar clientes de {s} em {c}? Eu te mando aqui.",
    ]

    return (base + extras)[:10]


@router.get("/acquisition", response_class=HTMLResponse)
def acquisition_page(request: Request):
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    ctx = {
        "request": request,
        "flashes": flashes,
        "user": user,
        "now": datetime.now(timezone.utc),
        "messages": [],
        "form": {"nicho": "", "cidade": "", "servico": "", "mode": "media"},
        "mode": "media",
    }

    return _render_first_existing(["acquisition.html", "acquisition/acquisition.html"], ctx)


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

    messages = _generate_acquisition_messages(nicho, cidade, servico, mode)

    ctx = {
        "request": request,
        "flashes": flashes,
        "user": user,
        "now": datetime.now(timezone.utc),
        "messages": messages,
        "form": {"nicho": nicho, "cidade": cidade, "servico": servico, "mode": mode},
        "mode": mode,
    }

    return _render_first_existing(["acquisition.html", "acquisition/acquisition.html"], ctx)


# =========================
# DEPOIMENTOS (CASES)
# =========================
@router.get("/cases", response_class=HTMLResponse)
def cases_page(request: Request):
    """
    Resolve o 404 do /app/cases (botão Depoimentos).
    Aqui eu tento carregar o template que você já tem no projeto.
    """
    flashes = pop_flashes(request)
    uid = _require_user(request)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            return redirect("/login", kind="error", message="Faça login novamente.")

    ctx = {
        "request": request,
        "flashes": flashes,
        "user": user,
        "now": datetime.now(timezone.utc),
    }

    # ⚠️ coloque aqui os nomes reais dos templates de depoimentos no seu projeto.
    # Eu deixei várias tentativas comuns.
    return _render_first_existing(
        [
            "cases.html",
            "depoimentos.html",
            "testimonials.html",
            "social_proof.html",
            "cases/index.html",
            "depoimentos/index.html",
            "social_proof/index.html",
        ],
        ctx,
    )


# =========================
# MAKE ADMIN (TEMP)
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