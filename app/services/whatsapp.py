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
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    # remove caractere corrompido (U+FFFD) caso exista
    s = s.replace("\ufffd", "")
    # normaliza travessões
    s = s.replace("–", "-").replace("—", "-")
    return s.strip()


def build_budget_message(
    *,
    client_name: str,
    service_type: str,
    value: str,
    payment_method: str,
    notes: str,
) -> str:
    client = _clean_text(client_name)
    service = _clean_text(service_type)
    payment = _clean_text(payment_method)
    value_txt = _clean_text(value)
    notes_txt = _clean_text(notes)

    observacao_line = (
        f"- Observações: {notes_txt}\n" if notes_txt else ""
    )

    message = (
        f"Olá {client}\n\n"
        f"Segue seu orçamento para {service}:\n\n"
        f"- Serviço: {service}\n"
        f"- Investimento: R$ {value_txt}\n"
        f"- Forma de pagamento: {payment}\n"
        f"{observacao_line}\n"
        f"Esse valor já inclui material e instalação completa.\n\n"
        f"Fico à disposição para qualquer dúvida.\n"
        f"Podemos agendar a instalação?"
    )

    return message


def whatsapp_link(phone: str, message: str) -> str:
    p = normalize_phone_br(phone)
    msg = _clean_text(message)

    # força UTF-8 corretamente
    encoded = quote(msg, safe="", encoding="utf-8", errors="strict")
    return f"https://wa.me/{p}?text={encoded}"


def followup_message(client_name: str) -> str:
    client = _clean_text(client_name)
    return (
        f"Olá {client}! Tudo bem?\n\n"
        f"Passando para saber se você conseguiu ver o orçamento que te enviei.\n\n"
        f"Se quiser, já posso agendar um horário para sua instalação.\n\n"
        f"Me confirma por aqui."
    )