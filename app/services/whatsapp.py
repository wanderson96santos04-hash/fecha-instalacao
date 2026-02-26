from __future__ import annotations

from urllib.parse import quote


def normalize_phone_br(phone: str) -> str:
    # Remove tudo que não for número
    digits = "".join(ch for ch in phone if ch.isdigit())

    # Se já começa com 55, mantém
    if digits.startswith("55"):
        return digits

    # Se tiver DDD + número (10 ou 11 dígitos), adiciona 55
    if len(digits) >= 10:
        return "55" + digits

    return digits


def build_budget_message(
    *,
    client_name: str,
    service_type: str,
    value: str,
    payment_method: str,
    notes: str,
) -> str:
    """
    Mensagem profissional otimizada para conversão e fechamento.
    """

    client = client_name.strip()
    service = service_type.strip()
    payment = payment_method.strip()
    value_txt = value.strip()
    notes_txt = notes.strip()

    # Prazo (opcional)
    prazo = f"📅 Prazo: {notes_txt}\n" if notes_txt else ""

    message = (
        f"Olá, {client}! 👋\n\n"
        f"Segue o seu orçamento:\n\n"
        f"🔧 Serviço: {service}\n"
        f"💰 Valor: R$ {value_txt}\n"
        f"💳 Forma de pagamento: {payment}\n"
        f"{prazo}\n"
        f"Se eu puder confirmar com você hoje, já consigo reservar a agenda e garantir sua instalação mais rápido. ✅\n\n"
        f"Fico à disposição para qualquer dúvida."
    )

    return message


def whatsapp_link(phone: str, message: str) -> str:
    p = normalize_phone_br(phone)

    # Encoding correto UTF-8
    encoded = quote(message, safe="")

    return f"https://wa.me/{p}?text={encoded}"


def followup_message(client_name: str) -> str:
    """
    Mensagem de follow-up profissional que aumenta taxa de resposta.
    """

    client = client_name.strip()

    message = (
        f"Olá, {client}! Tudo bem? 👋\n\n"
        f"Passando para saber se você conseguiu ver o orçamento que enviei.\n\n"
        f"Se quiser, já posso reservar um horário na agenda para sua instalação. ✅\n\n"
        f"Me avise que organizo tudo para você."
    )

    return message