from __future__ import annotations
from urllib.parse import quote


def normalize_phone_br(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("55"):
        return digits
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
    Mensagem profissional otimizada para conversão e fechamento (modelo 'UAU').
    """

    client = client_name.strip()
    service = service_type.strip()
    payment = payment_method.strip()
    value_txt = value.strip()
    notes_txt = (notes or "").strip()

    # Se você quiser tratar 'notes' como prazo, deixe assim.
    # Se preferir separar prazo e observações em campos diferentes, eu ajusto depois.
    prazo_line = ""
    obs_line = ""

    if notes_txt:
        lower = notes_txt.lower()
        # heurística simples: se a obs contém "prazo" ou "dias/horas", tratamos como prazo
        if "prazo" in lower or "dia" in lower or "hora" in lower or "semana" in lower:
            prazo_line = f"📅 Prazo estimado: {notes_txt}\n"
        else:
            obs_line = f"📝 Observações: {notes_txt}\n"

    message = (
        f"Olá {client} 👋\n\n"
        f"Segue seu orçamento para instalação de {service}:\n\n"
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
    encoded = quote(message, safe="")
    return f"https://wa.me/{p}?text={encoded}"


def followup_message(client_name: str) -> str:
    client = client_name.strip()
    message = (
        f"Olá {client}! Tudo bem? 👋\n\n"
        f"Passando pra saber se você conseguiu ver o orçamento que te enviei.\n\n"
        f"Se quiser, já posso agendar um horário pra sua instalação. ✅\n\n"
        f"Me confirma por aqui 😊"
    )
    return message