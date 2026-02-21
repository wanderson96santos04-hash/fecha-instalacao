from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/acquisition", tags=["Acquisition"])
templates = Jinja2Templates(directory="app/templates")


def _contexto(nicho: str, cidade: str, servico: str) -> str:
    nicho = (nicho or "").strip()
    cidade = (cidade or "").strip()
    servico = (servico or "").strip()

    partes = []
    if servico:
        partes.append(servico)
    if cidade:
        partes.append(f"em {cidade}")
    if nicho:
        partes.append(f"({nicho})")

    ctx = " ".join(partes).strip()
    return ctx or "seu serviço"


def _build_messages(nicho: str, cidade: str, servico: str, mode: str = "media") -> List[str]:
    """
    Gera 10 mensagens bem personalizadas para WhatsApp,
    com variação por tom: curta | media | agressiva
    """
    ctx = _contexto(nicho, cidade, servico)
    mode = (mode or "media").strip().lower()

    # Normaliza
    if mode not in {"curta", "media", "agressiva"}:
        mode = "media"

    if mode == "curta":
        # Mais curtas, bem diretas
        return [
            f"Oi! Você precisa de {ctx}? Posso te passar um valor rápido?",
            f"Olá! Faço {ctx}. Quer que eu te mande uma estimativa agora?",
            f"Bom dia! É sobre {ctx}: pode me mandar 2 fotos pra eu calcular?",
            f"Oi! Quer orçamento de {ctx} por aqui mesmo? É rápido.",
            f"Olá! Tenho agenda essa semana pra {ctx}. Quer um horário?",
            f"Pra {ctx}, me diga: medida aproximada + material + bairro.",
            f"Se você me falar a urgência do {ctx}, eu te passo o valor certinho.",
            f"Oi! Prefere opção econômica ou premium pro {ctx}?",
            f"Consigo te mandar o orçamento de {ctx} hoje. Pode ser?",
            f"Fecho um orçamento completo de {ctx} (prazo + garantia). Qual seu nome? 🙂",
        ]

    if mode == "agressiva":
        # Mais persuasiva, com urgência e CTA forte (sem ser grosseiro)
        return [
            f"Oi! Vi que você precisa de {ctx}. Se me mandar 2 fotos, eu fecho seu orçamento ainda hoje. Pode enviar?",
            f"Olá! Trabalho com {ctx}. Quer que eu te mande 3 opções (econômica/intermediária/premium) com valores agora?",
            f"Bom dia! Sobre {ctx}: você quer resolver hoje ou essa semana? Se for urgente eu priorizo sua avaliação.",
            f"Oi! Pra {ctx}, eu consigo te passar um preço bem certeiro com 3 infos: medida, material e local. Me fala rapidinho?",
            f"Olá! Tenho um horário livre nos próximos dias para {ctx}. Quer que eu reserve e já te envio o valor?",
            f"Oi! Se você quiser, eu já te mando o orçamento completo de {ctx} com prazo, garantia e forma de pagamento. Pode ser?",
            f"Olá! Pra agilizar: me diga o bairro e se já tem material/precisa que eu leve. Aí eu fecho o valor de {ctx}.",
            f"Oi! Quer que eu te mande a proposta de {ctx} no WhatsApp pronta pra você só aprovar?",
            f"Olá! Só confirmando: {ctx} é pra quando? Se for essa semana eu encaixo e te passo prioridade.",
            f"Oi! Me diz seu nome e o melhor horário — eu já te mando a proposta de {ctx} e você decide sem compromisso 🙂",
        ]

    # mode == "media" (padrão) -> mantém seu estilo atual
    return [
        f"Oi! Vi que você atende/precisa de {ctx}. Posso te passar uma estimativa rápida sem compromisso?",
        f"Olá! Trabalho com {ctx}. Quer que eu te mande as opções (básica/intermediária/premium) e valores?",
        f"Bom dia! Faço {ctx}. Você prefere orçamento por foto/vídeo ou eu te faço 3 perguntas e já te envio?",
        f"Oi! Consigo te orientar no {ctx} e já deixar tudo no jeito. Qual o melhor horário pra eu te chamar aqui?",
        f"Olá! Estou com agenda aberta essa semana para {ctx}. Quer que eu reserve um horário e te envio o valor antes?",
        f"Oi! Pra {ctx}, geralmente o que mais muda o preço é: medidas/material/acesso. Me diz rapidinho esses 3 itens?",
        f"Olá! Se você me mandar 2 fotos do local, eu monto um orçamento de {ctx} hoje ainda. Pode ser?",
        f"Oi! Trabalho com {ctx}. Prefere algo mais econômico ou caprichado/premium? Eu te mando as duas opções.",
        f"Olá! Só confirmando: é {ctx} para quando? Dependendo da urgência eu priorizo e te passo o valor certinho.",
        f"Oi! Posso te enviar um orçamento completo de {ctx} com prazo, garantia e forma de pagamento. Me diga seu nome 🙂",
    ]


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def acquisition_home(request: Request):
    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": {"nicho": "", "cidade": "", "servico": ""},
            "mode": "media",
            "messages": [],
        },
    )


# BÔNUS: evita "Method Not Allowed" se alguém abrir /acquisition/generate no navegador.
@router.get("/generate", response_class=HTMLResponse)
def acquisition_generate_get(request: Request):
    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": {"nicho": "", "cidade": "", "servico": ""},
            "mode": "media",
            "messages": [],
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
    form: Dict[str, str] = {
        "nicho": (nicho or "").strip(),
        "cidade": (cidade or "").strip(),
        "servico": (servico or "").strip(),
    }

    mode = (mode or "media").strip().lower()
    if mode not in {"curta", "media", "agressiva"}:
        mode = "media"

    messages = _build_messages(form["nicho"], form["cidade"], form["servico"], mode=mode)

    return templates.TemplateResponse(
        "acquisition/acquisition.html",
        {
            "request": request,
            "now": datetime.now(timezone.utc),
            "form": form,
            "mode": mode,
            "messages": messages,
        },
    )