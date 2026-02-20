from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str = _req("DATABASE_URL")
    SESSION_SECRET: str = _req("SESSION_SECRET")
    KIWIFY_WEBHOOK_SECRET: str = _req("KIWIFY_WEBHOOK_SECRET")
    BASE_URL: str = os.getenv("BASE_URL", "http://127.0.0.1:8000").strip()


settings = Settings()
