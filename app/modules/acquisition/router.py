from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])
templates = Jinja2Templates(directory="app/templates")


def _get_user_from_request(request: Request):
    """
    Tenta achar o usuário logado sem quebrar seu app.
    Suporta:
    - request.state.user (se seu app usa middleware)
    - request.session (se seu app usa SessionMiddleware)
    """
    user = getattr(request.state, "user", None)
    if user:
        return user

    session = getattr(request, "session", None)
    if isinstance(session, dict):
        # alguns apps guardam user direto na session (raramente)
        if session.get("user"):
            return session.get("user")

    return None


def _is_logged_in(request: Request) -> bool:
    session = getattr(request, "session", None)
    if isinstance(session, dict):
        # nomes comuns
        if session.get("user_id") or session.get("uid") or session.get("user"):
            return True
    if getattr(request.state, "user", None) is not None:
        return True
    return False


def _is_pro_user(request: Request) -> bool:
    # 1) via request.state.user
    user = _get_user_from_request(request)
    if user is not None:
        try:
            return bool(getattr(user, "is_pro", False))
        except Exception:
            pass

    # 2) via session flags (caso seu app guarde)
    session = getattr(request, "session", None)
    if isinstance(session, dict):
        for key in ("is_pro", "user_is_pro", "pro", "premium"):
            if key in session:
                return bool(session.get(key))

    return False


def _require_pro(request: Request):
    """
    PRO-only:
    - Se não estiver logado -> manda pro /login
    - Se logado e não PRO -> manda pro /app/upgrade
    """
    if not _is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)

    if not _is_pro_user(request):
        return RedirectResponse(url="/app/upgrade", status_code=302)

    return None


def _build_messages(nicho: str, cidade: str, servico: str, mode: str = "media") -> List[str]:
    nicho = (nicho or "").strip()
    cidade = (cidade or "").strip()
    servico = (servico or "").strip()
    mode = (mode or "media").strip().lower()

    contexto = " ".join(
        [p for p in [servico, f"em {cidade}" if cidade else "", f"({nicho})" if nicho else ""] if p]
    ).strip()
    if not contexto:
        contexto = "seu serviço"

    base = [
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

    if mode == "curta":
        return [
            f"Oi! Você precisa de {contexto}?",
            f"Olá! Faço {contexto}. Quer um orçamento rápido?",
            f"Bom dia! Me manda 2 fotos pra eu te passar o valor de {contexto}.",
            f"Oi! Qual seu prazo pra {contexto}?",
            f"Olá! Quer opção econômica e premium pra {contexto}?",
            f"Oi! Medidas e local (bairro) pra eu precificar {contexto}?",
            f"Olá! Consigo fazer {contexto} essa semana. Quer reservar?",
            f"Oi! Prefere orçamento por foto ou vídeo pra {contexto}?",
            f"Olá! Me diz seu nome que eu já te passo o valor de {contexto}.",
            f"Oi! Posso te mandar uma proposta completa de {contexto}?",
        ]

    if mode == "agressiva":
        return [
            f"Oi! Vi que você precisa de {contexto}. Se me mandar 2 fotos agora, eu te devolvo o valor ainda hoje. Pode ser?",
            f"Olá! Faço {contexto}. Tenho vaga essa semana — quer que eu te mande o orçamento e já reserve um horário?",
            f"Bom dia! Pra fechar {contexto}, só preciso de 3 infos: medidas, material e acesso. Me passa isso aqui?",
            f"Oi! Quer que eu te mande 2 opções (econômica e premium) pra {contexto} com prazo e garantia?",
            f"Olá! Se for pra {contexto} até {cidade}, consigo priorizar dependendo da urgência. É pra quando?",
            f"Oi! Se você me confirmar o bairro e mandar 2 fotos, eu fecho o valor de {contexto} agora.",
            f"Olá! Posso te mandar a proposta completa de {contexto} e já deixar agendado. Qual seu nome?",
            f"Oi! Quer resolver {contexto} hoje? Me chama com 2 fotos que eu te passo o valor na hora.",
            f"Olá! Você prefere pagamento no Pix/cartão? Eu já monto a proposta de {contexto} certinha.",
            f"Oi! Vamos fechar {contexto}: me diga seu nome + bairro e eu te envio o orçamento completo.",
        ]

    return base


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def acquisition_home(request: Request):
    gate = _require_pro(request)
    if gate:
        return gate

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
    gate = _require_pro(request)
    if gate:
        return gate

    form: Dict[str, str] = {
        "nicho": (nicho or "").strip(),
        "cidade": (cidade or "").strip(),
        "servico": (servico or "").strip(),
    }

    messages = _build_messages(form["nicho"], form["cidade"], form["servico"], mode=mode)

    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": form,
            "messages": messages,
            "mode": mode,
        },
    )