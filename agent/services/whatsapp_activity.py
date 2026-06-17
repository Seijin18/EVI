"""Summarize recent WhatsApp activity (not email)."""

from __future__ import annotations

from services.evolution_discovery import fetch_recent_whatsapp_messages, name_query_matches


def format_recent_messages(rows: list[dict], *, header: str = "") -> str:
    if not rows:
        return "Nenhuma mensagem WhatsApp recente encontrada no cache da Evolution."
    lines = [header] if header else ["Mensagens WhatsApp recentes:"]
    for r in rows:
        ts = (r.get("ts") or "")[:16].replace("T", " ")
        chat = r.get("chat_label") or "?"
        preview = r.get("preview") or r.get("text") or ""
        lines.append(f"• {ts} — {chat}: {preview[:220]}")
    return "\n".join(lines)


def list_recent_whatsapp(*, days: int = 1, limit: int = 40) -> str:
    days = max(1, min(int(days), 30))
    rows = fetch_recent_whatsapp_messages(days=days, limit=limit)
    period = "ontem/hoje" if days <= 1 else f"últimos {days} dias"
    return format_recent_messages(
        rows,
        header=f"WhatsApp ({period}, até {limit} mensagens):",
    )


def summarize_whatsapp(*, days: int = 1) -> str:
    days = max(1, min(int(days), 14))
    rows = fetch_recent_whatsapp_messages(days=days, limit=60)
    if not rows:
        return (
            "Não encontrei mensagens WhatsApp recentes no cache da Evolution. "
            "Confirme que a instância está conectada e que houve conversas no período."
        )

    lines = []
    for r in rows:
        ts = (r.get("ts") or "")[:16]
        chat = r.get("chat_label") or "?"
        lines.append(f"- {ts} {chat}: {r.get('preview', '')[:250]}")
    context = "\n".join(lines)

    from llm import build_llm, extract_llm_text

    period_label = "do dia anterior" if days == 1 else f"dos últimos {days} dias"
    prompt = f"""Resuma em português (bullet points) a atividade WhatsApp {period_label}.
Destaque: compromissos/eventos mencionados, pedidos pendentes, contatos importantes.
Não invente — use só as mensagens abaixo.

Mensagens:
{context[:10000]}"""
    resp = build_llm(temperature=0.3).invoke(prompt)
    if hasattr(resp, "content"):
        body = extract_llm_text(resp.content).strip()
    else:
        body = str(resp).strip()
    return f"Resumo WhatsApp ({period_label}):\n\n{body}"


def filter_messages_by_contact(
    rows: list[dict],
    name_or_phone: str,
) -> list[dict]:
    q = (name_or_phone or "").strip()
    if not q:
        return rows
    out: list[dict] = []
    for r in rows:
        chat_label = r.get("chat_label") or ""
        sender = r.get("sender_label") or ""
        if name_query_matches(chat_label, q) or name_query_matches(sender, q):
            out.append(r)
    return out
