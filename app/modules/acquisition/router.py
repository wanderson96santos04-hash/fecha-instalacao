from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])
templates = Jinja2Templates(directory="app/templates")


def _build_messages(nicho: str, cidade: str, servico: str) -> List[str]:
    nicho = (nicho or "").strip()
    cidade = (cidade or "").strip()
    servico = (servico or "").strip()

    contexto = " ".join(
        [p for p in [servico, f"em {cidade}" if cidade else "", f"({nicho})" if nicho else ""] if p]
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


def _get_logged_user(request: Request, db: Session) -> Optional[User]:
    """
    Lê o usuário logado pela sessão.
    Ajuste o nome da chave caso no seu login você salve diferente.
    """
    user_id = None

    # jeito mais comum (Starlette SessionMiddleware)
    if hasattr(request, "session"):
        user_id = request.session.get("user_id")

    # fallback se você salva direto como "id"
    if not user_id and hasattr(request, "session"):
        user_id = request.session.get("id")

    if not user_id:
        return None

    return db.query(User).filter(User.id == int(user_id)).first()


def _require_login_and_pro(request: Request, db: Session) -> User:
    user = _get_logged_user(request, db)
    if not user:
        return None  # tratado nas rotas com redirect

    return user


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def acquisition_home(request: Request, db: Session = Depends(get_db)):
    user = _get_logged_user(request, db)

    # Não logou? joga pro login
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Não é PRO? joga pro upgrade
    if not user.is_pro:
        return RedirectResponse(url="/app/upgrade", status_code=302)

    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": {"nicho": "", "cidade": "", "servico": "", "mode": "media"},
            "messages": [],
        },
    )


@router.post("/generate", response_class=HTMLResponse, name="acquisition_generate")
def acquisition_generate(
    request: Request,
    db: Session = Depends(get_db),
    nicho: str = Form(default=""),
    cidade: str = Form(default=""),
    servico: str = Form(default=""),
    mode: str = Form(default="media"),
):
    user = _get_logged_user(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not user.is_pro:
        return RedirectResponse(url="/app/upgrade", status_code=302)

    form: Dict[str, str] = {
        "nicho": (nicho or "").strip(),
        "cidade": (cidade or "").strip(),
        "servico": (servico or "").strip(),
        "mode": (mode or "media").strip(),
    }

    messages = _build_messages(form["nicho"], form["cidade"], form["servico"])

    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": form,
            "messages": messages,
            "mode": form["mode"],
        },
    )