from __future__ import annotations

import os
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_pro: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    @property
    def is_admin(self) -> bool:
        """
        Admin por e-mail (SEM mudar o banco).
        Configure no Render (Environment):
          ADMIN_EMAIL=seuemail@dominio.com
        """
        admin_email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
        if not admin_email:
            return False
        return (self.email or "").strip().lower() == admin_email