# -*- coding: utf-8 -*-
from __future__ import annotations

from urllib.parse import quote


def normalize_phone_br(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("55"):
        return digits
    if len(digits) >= 10:
        return "55" + digits
    return digits


def _clean_text(s: str) -> str:
    """
    Evita caracteres problemáticos e normaliza espaços.
    """
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    # remove caracteres de substituição comuns ( )
    s = s.replace("\ufffd", "")
    return s.strip()


def build_budget_message(
    *,
    client_name: str,
    service_type: str,
    value: str,
    payment_method: str,
    notes: str,
) -> str:
    """
    Mensagem profissional otimizada (modelo 'UAU').

    IMPORTANTE:
    - Use emojis comuns (👋 🔧 💰 💳 📅 📝 😊 ✅) que são bem suportados.
    - Se o ambiente estiver quebrando emoji, ainda assim o texto fica legível.
    """
    client = _clean_text(client_name)
    service = _clean_text(service_type)
    payment = _clean_text(payment_method)
    value_txt = _clean_text(value)
    notes_txt = _clean_text(notes)

    prazo_line = ""
    obs_line = ""

    if notes_txt:
        lower = notes_txt.lower()
        if "prazo" in lower or "dia" in lower or "hora" in lower or "semana" in lower:
            prazo_line = f"📅 Prazo estimado: {notes_txt}\n"
        else:
            obs_line = f"📝 Observações: {notes_txt}\n"

    message = (
        f"Olá {client} 👋\n\n"
        f"Segue seu orçamento para {service}:\n\n"
        f"🔧 Serviço: {service}\n"
        f"💰 Investimento: R$ {value_txt}\n"
        f"💳 Forma de pagamento: {payment}\n"
        f"{prazo_line}"
        f"{obs_line}\n"
        f"Esse valor já inclui material e instalação completa.\n\n"
        f"Qualquer dúvida fico à disposição 😊\n"
        f"Podemos agendar a instalação?"
    )

    return message


def whatsapp_link(phone: str, message: str) -> str:
    p = normalize_phone_br(phone)

    # garante que a mensagem está limpa e encode UTF-8 corretamente
    msg = _clean_text(message)

    # quote já trabalha com UTF-8; safe="" força encode de tudo que precisa
    encoded = quote(msg, safe="")

    return f"https://wa.me/{p}?text={encoded}"


def followup_message(client_name: str) -> str:
    client = _clean_text(client_name)
    message = (
        f"Olá {client}! Tudo bem? 👋\n\n"
        f"Passando pra saber se você conseguiu ver o orçamento que te enviei.\n\n"
        f"Se quiser, já posso agendar um horário pra sua instalação. ✅\n\n"
        f"Me confirma por aqui 😊"
    )
    return message