from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])
templates = Jinja2Templates(directory="app/templates")


def _build_messages(nicho: str, cidade: str, servico: str) -> list[str]:
    n = nicho.strip()
    c = cidade.strip()
    s = servico.strip()

    # 10 variações com objetivos diferentes: abertura, prova, urgência, follow-up, etc.
    return [
        f"Olá! Tudo bem? Vi que você é de {c}. Eu trabalho com {s} ({n}). Posso te mandar uma opção rápida de orçamento sem compromisso?",
        f"Oi! Sou especialista em {s} para {n} aqui em {c}. Você está precisando de orçamento ou só pesquisando valores por agora?",
        f"Boa! Passando porque atendo {c} e faço {s} focado em {n}. Quer que eu te pergunte 2 coisinhas e já te passo um valor aproximado?",
        f"Olá 👋 Atendo {c}. Trabalho com {s} voltado para {n}. Se você me disser o que precisa, eu já te retorno com prazo + valor estimado.",
        f"Oi! Consegue me dizer o que você quer exatamente em {s}? É para {n} em {c}, certo? Com isso eu já te mando um orçamento bem certeiro.",
        f"Olá! Tenho agenda essa semana em {c} para {s}. É para {n}? Se quiser, te passo as opções e você escolhe a melhor.",
        f"Oi! Posso te mandar 3 opções de orçamento para {s} (voltado para {n}) aí em {c}: econômico, padrão e premium. Quer?",
        f"Olá 🙂 Só confirmando: ainda precisa de {s} para {n} em {c}? Se sim, me fala o melhor horário que eu te respondo com orçamento.",
        f"Oi! Vi sua necessidade de {s}. Eu atendo {c} e faço serviço bem caprichado para {n}. Quer que eu te mande uma proposta por WhatsApp agora?",
        f"Última mensagem pra não te incomodar 😄 Você ainda quer orçamento de {s} ({n}) em {c}? Se responder “sim”, eu já te mando as opções.",
    ]


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def acquisition_home(request: Request):
    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {"request": request, "now": datetime.now(timezone.utc)},
    )


@router.post("/generate", response_class=HTMLResponse)
def acquisition_generate(
    request: Request,
    nicho: str = Form(...),
    cidade: str = Form(...),
    servico: str = Form(...),
):
    form = {"nicho": nicho, "cidade": cidade, "servico": servico}
    messages = _build_messages(nicho, cidade, servico)

    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": form,
            "messages": messages,
        },
    )