from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])

templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def acquisition_home(request: Request):
    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
        },
    )
