from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from app.db.session import SessionLocal


@dataclass
class Testimonial:
    id: int
    name: str
    city: str
    service: str
    value: str
    quote: str


def is_cases_admin(user_id: int, user_is_pro: bool) -> bool:
    """
    Admin simples:
      - Pro pode administrar
      - OU env ADMIN_UIDS="1,2,3"
    """
    if user_is_pro:
        return True

    raw = (os.getenv("ADMIN_UIDS") or "").strip()
    if not raw:
        return False
    allowed = {s.strip() for s in raw.split(",") if s.strip()}
    return str(user_id) in allowed


def list_testimonials() -> List[Testimonial]:
    with SessionLocal() as db:
        rows = db.execute(
            text(
                "SELECT id, name, city, service, value, quote "
                "FROM testimonials "
                "ORDER BY created_at DESC, id DESC"
            )
        ).fetchall()

    return [
        Testimonial(
            id=int(r[0]),
            name=str(r[1] or ""),
            city=str(r[2] or ""),
            service=str(r[3] or ""),
            value=str(r[4] or ""),
            quote=str(r[5] or ""),
        )
        for r in rows
    ]


def get_testimonial(tid: int) -> Optional[Testimonial]:
    with SessionLocal() as db:
        r = db.execute(
            text(
                "SELECT id, name, city, service, value, quote "
                "FROM testimonials WHERE id = :id"
            ),
            {"id": tid},
        ).fetchone()

    if not r:
        return None

    return Testimonial(
        id=int(r[0]),
        name=str(r[1] or ""),
        city=str(r[2] or ""),
        service=str(r[3] or ""),
        value=str(r[4] or ""),
        quote=str(r[5] or ""),
    )


def create_testimonial(data: Dict[str, Any]) -> int:
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO testimonials (name, city, service, value, quote) "
                "VALUES (:name, :city, :service, :value, :quote)"
            ),
            data,
        )
        db.commit()
        tid = db.execute(text("SELECT MAX(id) FROM testimonials")).scalar()
        return int(tid or 0)


def update_testimonial(tid: int, data: Dict[str, Any]) -> None:
    with SessionLocal() as db:
        db.execute(
            text(
                "UPDATE testimonials "
                "SET name=:name, city=:city, service=:service, value=:value, quote=:quote "
                "WHERE id=:id"
            ),
            {**data, "id": tid},
        )
        db.commit()


def delete_testimonial(tid: int) -> None:
    with SessionLocal() as db:
        db.execute(text("DELETE FROM testimonials WHERE id = :id"), {"id": tid})
        db.commit()