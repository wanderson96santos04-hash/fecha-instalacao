from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db.session import init_db
from app.core.deps import FLASH_COOKIE, pop_flashes

# CORE ROUTERS
from app.routes.auth import router as auth_router
from app.routes.app import router as app_router
from app.routes.webhook import router as webhook_router

# ✅ NOVO ROUTER RETENTION (SEU retention.py)
from app.routes.retention import router as retention_router


app = FastAPI(title="FECHA INSTALAÇÃO", version="0.1.0")
print(">>> MAIN.PY LOADED (with retention module)")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ========================
# STARTUP
# ========================
@app.on_event("startup")
def _startup() -> None:
    init_db()


# ========================
# FLASH MIDDLEWARE
# ========================
@app.middleware("http")
async def flash_middleware(request: Request, call_next):

    response = await call_next(request)

    if getattr(request.state, "clear_flashes", False):
        response.delete_cookie(key=FLASH_COOKIE, path="/")

    return response


# ========================
# PREMIUM GATE (SEGURO)
# ========================
try:

    from app.core.deps import get_user_id_from_request
    from app.modules.premium_gate.services import get_gate_info, render_banner_html
    from jinja2 import ChoiceLoader, FileSystemLoader

    premium_templates = Jinja2Templates(directory="app/templates")

    premium_templates.env.loader = ChoiceLoader([
        premium_templates.env.loader,
        FileSystemLoader("app/modules/premium_gate/templates"),
    ])

    @app.middleware("http")
    async def premium_gate_middleware(request: Request, call_next):

        request.state.premium_banner_html = ""

        if not request.url.path.startswith("/app"):
            return await call_next(request)

        try:

            uid_raw = get_user_id_from_request(request)

            if uid_raw:

                uid = int(uid_raw)

                info = get_gate_info(uid)

                request.state.premium_banner_html = render_banner_html(info)

                if (
                    (not info.is_pro)
                    and info.at_limit
                    and request.url.path == "/app/budgets/new"
                    and request.method.upper() == "POST"
                ):
                    return premium_templates.TemplateResponse(
                        "premium_gate/limit.html",
                        {
                            "request": request,
                            "flashes": [],
                            "user": None,
                            "info": info,
                        },
                        status_code=403,
                    )

        except Exception:
            request.state.premium_banner_html = ""

        return await call_next(request)

except Exception as e:
    print(f"[modules] PremiumGate middleware NOT loaded: {e}")


# ========================
# LANDING
# ========================
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


# ========================
# HEALTH
# ========================
@app.get("/health")
def health():
    return {"ok": True}


# ========================
# CORE ROUTERS
# ========================
app.include_router(auth_router)
app.include_router(app_router)
app.include_router(webhook_router)

# ✅ NOVO RETENTION ROUTER
app.include_router(retention_router)


# ========================
# MÓDULOS OPCIONAIS
# ========================

try:
    from app.modules.acquisition.router import router as acquisition_router
    app.include_router(acquisition_router)
except Exception as e:
    print(f"[modules] Acquisition router NOT loaded: {e}")


try:
    from app.modules.social_proof.router import router as social_proof_router
    app.include_router(social_proof_router)
except Exception as e:
    print(f"[modules] SocialProof router NOT loaded: {e}")


try:
    from app.modules.onboarding.router import router as onboarding_router
    app.include_router(onboarding_router)
except Exception as e:
    print(f"[modules] Onboarding router NOT loaded: {e}")


try:
    from app.modules.invite.router import router as invite_router
    app.include_router(invite_router)
except Exception as e:
    print(f"[modules] Invite router NOT loaded: {e}")


try:
    from app.modules.premium_gate.router import router as premium_gate_router
    app.include_router(premium_gate_router)
except Exception as e:
    print(f"[modules] PremiumGate router NOT loaded: {e}")


try:
    from app.modules.cases.router import router as cases_router
    app.include_router(cases_router)
except Exception as e:
    print(f"[modules] Cases router NOT loaded: {e}")


# ========================
# AUTH HANDLER
# ========================
@app.exception_handler(401)
def _unauthorized(_, __):

    return RedirectResponse(
        url="/login",
        status_code=303,
    )