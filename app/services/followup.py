from __future__ import annotations

from datetime import datetime, timezone, timedelta


def hours_since(dt: datetime) -> float:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    return delta.total_seconds() / 3600.0


def can_followup(created_at: datetime) -> bool:
    return hours_since(created_at) >= 24.0
