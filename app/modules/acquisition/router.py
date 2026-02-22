from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.deps import get_user_id_from_request
from app.db.session import SessionLocal
from app.models.user import User

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])
templates = Jinja2Templates(directory="app/templates")


def _build_messages(nicho: str, cidade: str, servico: str) -> List[str]:
    nicho = (nicho or "").strip()
    cidade = (cidade or "").strip()
    servico = (servico or "").strip()

    contexto = " ".join(
        [
            p
            for p in [
                servico,
                f"em {cidade}" if cidade else "",
                f"({nicho})" if nicho else "",
            ]
            if p
        ]
    ).strip()

    if not contexto:
        contexto = "seu serviço"

    return [
        f"Oi! Vi que você atende/precisa de {contexto}. Posso te passar uma estimativa rápida sem compromisso?",
        f"Olá! Trabalho com {contexto}. Quer que eu te mande as opções (básica/intermediária/premium) e valores?",
        f"Bom dia! Faço {contexto}. Você prefere orçamento por foto/vídeo ou eu te faço 3 perguntas e já te envio?",
        f"Oi! Consigo te orientar no {contexto} e já deixar tudo no jeito. Qual o melhor horário pra eu te chamar aqui?",
        f"Olá! Estou com agenda aberta essa semana para {contexto}. Quer que eu reserve um horário e te envio o valor antes?",
        f"Oi! Pra {contexto}, geralmente o que mais muda o preço é: medidas/material/acesso. Me diz rapidinho esses 3 itens?",
        f"Olá! Se você me mandar 2 fotos do local, eu monto um orçamento de {contexto} hoje ainda. Pode ser?",
        f"Oi! Trabalho com {contexto}. Prefere algo mais econômico ou caprichado/premium? Eu te mando as duas opções.",
        f"Olá! Só confirmando: é {contexto} para quando? Dependendo da urgência eu priorizo e te passo o valor certinho.",
        f"Oi! Posso te enviar um orçamento completo de {contexto} com prazo, garantia e forma de pagamento. Me diga seu nome 🙂",
    ]


def _get_logged_user(request: Request) -> Optional[User]:
    user_id = get_user_id_from_request(request)
    if not user_id:
        return None

    db = SessionLocal()
    try:
        # seu deps.py guarda uid como string, mas seu User.id é int.
        # então a gente tenta converter, e se não der, retorna None.
        try:
            uid_int = int(user_id)
        except Exception:
            return None

        return db.query(User).filter(User.id == uid_int).first()
    finally:
        db.close()


def _require_pro(request: Request):
    user = _get_logged_user(request)

    # Não logado -> login
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # Logado mas não PRO -> upgrade
    if not getattr(user, "is_pro", False):
        return RedirectResponse(url="/app/upgrade", status_code=303)

    return None  # OK


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def acquisition_home(request: Request):
    guard = _require_pro(request)
    if guard:
        return guard

    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": {"nicho": "", "cidade": "", "servico": ""},
            "messages": [],
            "mode": "media",
        },
    )


@router.post("/generate", response_class=HTMLResponse, name="acquisition_generate")
def acquisition_generate(
    request: Request,
    nicho: str = Form(default=""),
    cidade: str = Form(default=""),
    servico: str = Form(default=""),
    mode: str = Form(default="media"),
):
    guard = _require_pro(request)
    if guard:
        return guard

    form: Dict[str, str] = {
        "nicho": (nicho or "").strip(),
        "cidade": (cidade or "").strip(),
        "servico": (servico or "").strip(),
    }

    messages = _build_messages(form["nicho"], form["cidade"], form["servico"])

    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": form,
            "messages": messages,
            "mode": (mode or "media").strip(),
        },
    )