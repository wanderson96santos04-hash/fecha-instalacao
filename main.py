from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db.session import init_db
from app.core.deps import FLASH_COOKIE, pop_flashes
from app.routes.auth import router as auth_router
from app.routes.app import router as app_router
from app.routes.webhook import router as webhook_router

app = FastAPI(title="FECHA INSTALAÇÃO", version="0.1.0")
print(">>> MAIN.PY LOADED (commit c0a53a3)")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.middleware("http")
async def flash_middleware(request: Request, call_next):
    response = await call_next(request)

    # se alguma página chamou pop_flashes(request), limpamos o cookie aqui
    if getattr(request.state, "clear_flashes", False):
        response.delete_cookie(key=FLASH_COOKIE, path="/")

    return response


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    flashes = pop_flashes(request)
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "flashes": flashes,
            "now": datetime.now(timezone.utc),
            "product_name": "FECHA INSTALAÇÃO",
        },
    )


@app.get("/health")
def health():
    return {"ok": True, "app": "fecha-instalacao"}


app.include_router(auth_router)
app.include_router(app_router)
app.include_router(webhook_router)

# ✅ MÓDULOS ISOLADOS (opcional e seguro)
# Se o módulo ainda não existir/estiver pronto, não quebra nada.
try:
    from app.modules.acquisition.router import router as acquisition_router  # novo módulo FastAPI
    app.include_router(acquisition_router)
except Exception as e:
    print(f"[modules] Acquisition router NOT loaded: {e}")


@app.exception_handler(401)
def _unauthorized(_, __):
    return RedirectResponse(url="/login", status_code=303)