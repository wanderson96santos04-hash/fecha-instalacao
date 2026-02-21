"""
Módulo de Aquisição (FastAPI).

Integração simples (sem mexer no que já existe):

    from app.modules.acquisition import register as register_acquisition
    register_acquisition(app)

Este módulo registra APENAS o APIRouter do módulo.
"""
from __future__ import annotations

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    # Import local para manter o módulo isolado
    from .router import router
    app.include_router(router)
