from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.budget import Budget
from app.models.user import User


FREE_LIMIT_TOTAL_BUDGETS = 10


def can_create_budget(db: Session, user: User) -> tuple[bool, int]:
    if user.is_pro:
        return True, -1
    total = db.scalar(select(func.count(Budget.id)).where(Budget.user_id == user.id)) or 0
    if total >= FREE_LIMIT_TOTAL_BUDGETS:
        return False, total
    return True, total


def create_budget(
    db: Session,
    *,
    user_id: int,
    client_name: str,
    phone: str,
    service_type: str,
    value: str,
    payment_method: str,
    notes: str,
) -> Budget:
    b = Budget(
        user_id=user_id,
        client_name=client_name.strip(),
        phone=phone.strip(),
        service_type=service_type.strip(),
        value=value.strip(),
        payment_method=payment_method.strip(),
        notes=(notes or "").strip(),
        status="awaiting",
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b
