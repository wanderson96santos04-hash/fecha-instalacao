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
    # remove o caractere " " (U+FFFD) caso já esteja vindo corrompido
    s = s.replace("\ufffd", "")
    # troca travessão/en-dash por hífen normal (evita outros "quebra-texto")
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

    prazo_line = ""
    obs_line = ""

    if notes_txt:
        lower = notes_txt.lower()
        if "prazo" in lower or "dia" in lower or "hora" in lower or "semana" in lower:
            prazo_line = f"Prazo estimado: {notes_txt}\n"
        else:
            obs_line = f"Observacoes: {notes_txt}\n"

    message = (
        f"Olá {client}\n\n"
        f"Segue seu orçamento para {service}:\n\n"
        f"- Servico: {service}\n"
        f"- Investimento: R$ {value_txt}\n"
        f"- Forma de pagamento: {payment}\n"
        f"{prazo_line}"
        f"{obs_line}\n"
        f"Esse valor já inclui material e instalação completa.\n\n"
        f"Qualquer dúvida fico à disposição.\n"
        f"Podemos agendar a instalação?"
    )

    return message


def whatsapp_link(phone: str, message: str) -> str:
    p = normalize_phone_br(phone)
    msg = _clean_text(message)

    # força UTF-8 explicitamente
    encoded = quote(msg, safe="", encoding="utf-8", errors="strict")
    return f"https://wa.me/{p}?text={encoded}"


def followup_message(client_name: str) -> str:
    client = _clean_text(client_name)
    return (
        f"Olá {client}! Tudo bem?\n\n"
        f"Passando pra saber se você conseguiu ver o orçamento que te enviei.\n\n"
        f"Se quiser, já posso agendar um horário pra sua instalação.\n\n"
        f"Me confirma por aqui."
    )