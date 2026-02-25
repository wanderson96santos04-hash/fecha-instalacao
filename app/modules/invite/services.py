from __future__ import annotations

import secrets
import string
from dataclasses import dataclass

from sqlalchemy import text

from app.db.session import SessionLocal


@dataclass
class InviteInfo:
    code: str
    copy_count: int
    click_count: int


def _new_code(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_or_create_invite(user_id: int) -> InviteInfo:
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT code, copy_count, click_count FROM invite_referrals WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()

        if row:
            return InviteInfo(
                code=str(row[0]),
                copy_count=int(row[1] or 0),
                click_count=int(row[2] or 0),
            )

        code = _new_code()
        db.execute(
            text(
                "INSERT INTO invite_referrals (user_id, code, copy_count, click_count) "
                "VALUES (:uid, :code, 0, 0)"
            ),
            {"uid": user_id, "code": code},
        )
        db.commit()
        return InviteInfo(code=code, copy_count=0, click_count=0)


def increment_copy(user_id: int) -> None:
    with SessionLocal() as db:
        db.execute(
            text("UPDATE invite_referrals SET copy_count = COALESCE(copy_count,0) + 1 WHERE user_id = :uid"),
            {"uid": user_id},
        )
        db.commit()


def increment_click_by_code(code: str) -> None:
    with SessionLocal() as db:
        db.execute(
            text("UPDATE invite_referrals SET click_count = COALESCE(click_count,0) + 1 WHERE code = :code"),
            {"code": code},
        )
        db.commit()