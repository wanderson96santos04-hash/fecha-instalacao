from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])
templates = Jinja2Templates(directory="app/templates")


def _normalize(s: str) -> str:
    return " ".join((s or "").strip().split())


def _title(s: str) -> str:
    s = _normalize(s)
    return s[:1].upper() + s[1:] if s else s


def _build_messages(nicho: str, cidade: str, servico: str) -> List[str]:
    # mensagens objetivas (nada genérico), variando abordagem, com CTA e opção de orçamento
    n = _title(nicho)
    c = _title(cidade)
    s = _title(servico)

    return [
        f"Olá! Vi que você é de {c}. Eu trabalho com {s}. Posso te passar um orçamento rápido? Só me diga as medidas/fotos do local.",
        f"Oi! Atendo {c} e região com {s}. Quer que eu te mande um valor estimado ainda hoje? (é só me falar o que precisa).",
        f"Olá! Faço {s} em {c}. Se você me mandar 2 fotos e uma medida aproximada, eu já retorno com preço e prazo.",
        f"Oi! Trabalho com {s}. Você precisa para casa ou comércio em {c}? Dependendo do caso, consigo encaixar ainda essa semana.",
        f"Olá! Sobre {s}: você prefere orçamento por visita ou por fotos? Em {c} eu consigo avaliar bem rápido.",
        f"Oi! Se for {s}, eu consigo te orientar agora: qual o problema/objetivo (trocar, instalar, consertar)? Aí te passo o caminho e o valor.",
        f"Olá! Atendo o nicho {n} e serviços de {s} em {c}. Quer que eu te envie duas opções: econômico e premium?",
        f"Oi! Pra {s}, você já tem material ou precisa que eu leve? Me diga isso + {c} (bairro) que te passo o orçamento certinho.",
        f"Olá! Posso te mandar um orçamento fechado de {s} com prazo e garantia. Me diga: é urgente ou pode agendar?",
        f"Oi! Se você quiser, eu já deixo pré-agendado um horário pra ver/medir e fechar o valor de {s} em {c}. Qual melhor dia/turno?",
    ]


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def acquisition_home(request: Request):
    # página inicial do módulo (sem mensagens ainda)
    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "messages": [],
            "nicho": "",
            "cidade": "",
            "servico": "",
        },
    )


@router.post("/generate", response_class=HTMLResponse)
def acquisition_generate(
    request: Request,
    nicho: str = Form(""),
    cidade: str = Form(""),
    servico: str = Form(""),
):
    nicho_n = _normalize(nicho)
    cidade_n = _normalize(cidade)
    servico_n = _normalize(servico)

    errors = []
    if not nicho_n:
        errors.append("Informe o nicho.")
    if not cidade_n:
        errors.append("Informe a cidade.")
    if not servico_n:
        errors.append("Informe o tipo de serviço.")

    messages = _build_messages(nicho_n, cidade_n, servico_n) if not errors else []

    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "messages": messages,
            "errors": errors,
            "nicho": nicho_n,
            "cidade": cidade_n,
            "servico": servico_n,
        },
    )