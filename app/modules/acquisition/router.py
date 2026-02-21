from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])
templates = Jinja2Templates(directory="app/templates")


def _build_messages(nicho: str, cidade: str, servico: str) -> list[str]:
    """
    Gera 10 mensagens objetivas e prontas para prospecção no WhatsApp.
    Sem depender de IA externa (funciona 100%).
    """
    n = nicho.strip()
    c = cidade.strip()
    s = servico.strip()

    base = f"{s} ({n}) em {c}" if (n and c and s) else "seu serviço"

    msgs = [
        f"Olá! Tudo bem? Vi que você pode estar precisando de {base}. Posso te passar um orçamento rapidinho?",
        f"Oi! Trabalho com {s} em {c}. Quer que eu te envie uma estimativa de valor e prazo ainda hoje?",
        f"Olá! Faço {s} na região de {c}. Se me passar uma foto/medida, eu já te mando um orçamento.",
        f"Oi! Atendo {c} com {s}. Tenho horário essa semana. Quer que eu te diga valores e disponibilidade?",
        f"Olá! Trabalho com {n} e faço {s} em {c}. Posso te ajudar com um orçamento sem compromisso?",
        f"Oi! Para {s} em {c}, eu consigo te orientar e já deixar um orçamento pronto. Pode me dizer o que precisa?",
        f"Olá! Você está buscando {s}? Atendo {c}. Posso te enviar um preço base e opções de pagamento.",
        f"Oi! Se for sobre {s} em {c}, eu consigo fazer um orçamento rápido. Tem foto do local/medidas?",
        f"Olá! Tenho experiência com {n}. Faço {s} em {c}. Quer que eu te chame e já combinamos os detalhes?",
        f"Oi! Posso te passar um orçamento de {s} em {c} agora. Me diz só: é para quando e qual o tamanho/medida?",
    ]
    return msgs


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def acquisition_home(request: Request):
    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": {"nicho": "", "cidade": "", "servico": ""},
            "messages": [],
        },
    )


@router.post("/generate", response_class=HTMLResponse)
def acquisition_generate(
    request: Request,
    nicho: str = Form(default=""),
    cidade: str = Form(default=""),
    servico: str = Form(default=""),
):
    msgs = _build_messages(nicho=nicho, cidade=cidade, servico=servico)

    messages = [
        {
            "text": text,
            "wa_link": f"https://wa.me/?text={quote(text)}",
        }
        for text in msgs
    ]

    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": {"nicho": nicho, "cidade": cidade, "servico": servico},
            "messages": messages,
        },
    )