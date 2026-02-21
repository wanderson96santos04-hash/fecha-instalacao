from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

# ✅ usa o MESMO templates do app principal (layout Premium idêntico)
from main import templates

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def acquisition_home(request: Request):
    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            # mantém o padrão do seu app principal
            "product_name": "FECHA INSTALAÇÃO",
        },
    )
