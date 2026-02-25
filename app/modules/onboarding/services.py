from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text, select, desc

from app.db.session import SessionLocal
from app.models.user import User
from app.models.budget import Budget


@dataclass
class OnboardingState:
    user_id: int
    step1_done: bool
    step2_done: bool
    step3_done: bool
    completed: bool
    target_budget_id: Optional[int]
    target_budget_status: Optional[str]


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def get_onboarding_state(user_id: int) -> OnboardingState:
    """
    Guia em 3 passos:
      1) Criou 1 orçamento? (existe Budget)
      2) Clicou para enviar WhatsApp pelo onboarding? (evento gravado)
      3) Marcou status? (awaiting/won/lost no último orçamento)
    """
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            return OnboardingState(
                user_id=user_id,
                step1_done=False,
                step2_done=False,
                step3_done=False,
                completed=False,
                target_budget_id=None,
                target_budget_status=None,
            )

        latest_budget = db.scalars(
            select(Budget)
            .where(Budget.user_id == user_id)
            .order_by(desc(Budget.created_at), desc(Budget.id))
        ).first()

        step1_done = latest_budget is not None
        target_budget_id = latest_budget.id if latest_budget else None
        target_status = _norm(latest_budget.status) if latest_budget else None

        # Step 2: evento gravado (não depende de log)
        step2_done = False
        if step1_done:
            row = db.execute(
                text(
                    "SELECT 1 FROM onboarding_events "
                    "WHERE user_id = :uid AND event = 'onboarding_whatsapp_clicked' "
                    "LIMIT 1"
                ),
                {"uid": user_id},
            ).fetchone()
            step2_done = row is not None

        step3_done = target_status in {"awaiting", "won", "lost"}
        completed = step1_done and step2_done and step3_done

        return OnboardingState(
            user_id=user_id,
            step1_done=step1_done,
            step2_done=step2_done,
            step3_done=step3_done,
            completed=completed,
            target_budget_id=target_budget_id,
            target_budget_status=target_status,
        )


def record_onboarding_event(user_id: int, event: str) -> None:
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO onboarding_events (user_id, event) VALUES (:uid, :event)"),
            {"uid": user_id, "event": event},
        )
        db.commit()