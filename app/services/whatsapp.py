from __future__ import annotations

from urllib.parse import quote


def normalize_phone_br(phone: str) -> str:
    """
    Normaliza telefone brasileiro para padrão internacional (55 + DDD + número).
    Aceita formatos com espaços, parênteses, hífen etc.
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())

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
    Mensagem profissional (modelo UAU) com quebras corretas pro WhatsApp.
    """

    client = (client_name or "").strip()
    service = (service_type or "").strip()
    payment = (payment_method or "").strip()
    value_txt = (value or "").strip()
    notes_txt = (notes or "").strip()

    # Linhas opcionais
    prazo_line = ""
    obs_line = ""

    if notes_txt:
        lower = notes_txt.lower()

        # Heurística simples pra detectar se a nota parece prazo
        if any(w in lower for w in ["prazo", "dia", "dias", "hora", "horas", "semana", "mes", "mês"]):
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
        f"{obs_line}"
        f"\n"
        f"Esse valor já inclui material e instalação completa.\n\n"
        f"Qualquer dúvida fico à disposição 😊\n"
        f"Podemos agendar a instalação?\n\n"
    )

    return message


def whatsapp_link(phone: str, message: str) -> str:
    """
    Gera link do WhatsApp com encoding correto.
    """
    p = normalize_phone_br(phone)
    encoded = quote(message, safe="")
    return f"https://wa.me/{p}?text={encoded}"


def followup_message(client_name: str) -> str:
    """
    Mensagem de follow-up automática.
    """
    client = (client_name or "").strip()

    message = (
        f"Olá {client}! Tudo bem? 👋\n\n"
        f"Passando pra saber se você conseguiu ver o orçamento que te enviei.\n\n"
        f"Se quiser, já posso agendar um horário pra sua instalação. ✅\n\n"
        f"Me confirma por aqui 😊\n\n"
    )

    return message