from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.models.base import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, default="")
    city = Column(String, nullable=False, default="")
    service = Column(String, nullable=False, default="")
    value = Column(String, nullable=False, default="")
    phrase = Column(String, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)