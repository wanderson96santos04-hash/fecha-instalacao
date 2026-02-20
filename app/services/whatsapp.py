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

    notes_txt = notes.strip()

    obs = f"\n\nObservações:\n{notes_txt}" if notes_txt else ""

    # ⚠️ REMOVIDOS emojis para evitar problema de encoding
    return (
        f"Olá, {client_name}!\n\n"
        f"Segue o seu orçamento:\n\n"
        f"Serviço: {service_type}\n"
        f"Valor: {value}\n"
        f"Forma de pagamento: {payment_method}"
        f"{obs}\n\n"
        f"Se eu puder fechar com você hoje, posso agendar a instalação."
    )


def whatsapp_link(phone: str, message: str) -> str:
    p = normalize_phone_br(phone)

    # Garante UTF-8 antes de aplicar quote
    encoded = quote(message.encode("utf-8"))

    return f"https://wa.me/{p}?text={encoded}"


def followup_message(client_name: str) -> str:
    return (
        f"Olá, {client_name}!\n\n"
        f"Passando pra confirmar se você conseguiu ver o orçamento.\n\n"
        f"Se quiser, já deixo o melhor horário separado pra você."
    )
