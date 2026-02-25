from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, func

from app.db.session import SessionLocal
from app.models.user import User
from app.models.budget import Budget
from app.services.budget_service import FREE_LIMIT_TOTAL_BUDGETS


@dataclass
class PremiumGateInfo:
    is_pro: bool
    total_budgets: int
    limit: int
    remaining: Optional[int]
    near_limit: bool
    at_limit: bool


def get_gate_info(user_id: int) -> PremiumGateInfo:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            return PremiumGateInfo(
                is_pro=False,
                total_budgets=0,
                limit=FREE_LIMIT_TOTAL_BUDGETS,
                remaining=FREE_LIMIT_TOTAL_BUDGETS,
                near_limit=False,
                at_limit=False,
            )

        total = db.scalar(select(func.count()).select_from(Budget).where(Budget.user_id == user_id))
        total = int(total or 0)

        if user.is_pro:
            return PremiumGateInfo(
                is_pro=True,
                total_budgets=total,
                limit=FREE_LIMIT_TOTAL_BUDGETS,
                remaining=None,
                near_limit=False,
                at_limit=False,
            )

        remaining = max(0, FREE_LIMIT_TOTAL_BUDGETS - total)
        near_limit = (remaining > 0 and remaining <= 2)  # ex: 8/10 ou 9/10
        at_limit = remaining == 0

        return PremiumGateInfo(
            is_pro=False,
            total_budgets=total,
            limit=FREE_LIMIT_TOTAL_BUDGETS,
            remaining=remaining,
            near_limit=near_limit,
            at_limit=at_limit,
        )


def render_banner_html(info: PremiumGateInfo) -> str:
    """
    Retorna HTML pronto para injetar no base_app.html via request.state.
    (Sem precisar editar dashboard ou outras páginas.)
    """
    if info.is_pro:
        return ""

    if info.at_limit:
        return f"""
        <div class="mx-auto max-w-6xl px-4 pt-4">
          <div class="rounded-xl border bg-red-50 p-4">
            <div class="font-semibold">Você atingiu o limite do plano Free ({info.limit}).</div>
            <div class="text-sm text-slate-700 mt-1">A partir de agora, você pode perder clientes por não conseguir criar novos orçamentos.</div>
            <div class="mt-3 flex gap-2">
              <a class="px-4 py-2 rounded-xl bg-slate-900 text-white text-sm font-semibold" href="/app/upgrade">Ver Premium</a>
              <a class="px-4 py-2 rounded-xl border text-sm font-semibold" href="/app/checkout">Fazer upgrade</a>
            </div>
          </div>
        </div>
        """

    if info.near_limit:
        used = info.total_budgets
        rem = info.remaining or 0
        return f"""
        <div class="mx-auto max-w-6xl px-4 pt-4">
          <div class="rounded-xl border bg-yellow-50 p-4">
            <div class="font-semibold">Você está perto de perder clientes…</div>
            <div class="text-sm text-slate-700 mt-1">Você já usou <b>{used}/{info.limit}</b> orçamentos. Restam <b>{rem}</b>.</div>
            <div class="mt-3 flex gap-2">
              <a class="px-4 py-2 rounded-xl bg-slate-900 text-white text-sm font-semibold" href="/app/upgrade">Virar Premium</a>
              <a class="px-4 py-2 rounded-xl border text-sm font-semibold" href="/app/checkout">Upgrade rápido</a>
            </div>
          </div>
        </div>
        """

    return ""