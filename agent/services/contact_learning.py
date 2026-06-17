"""Synthesize contact knowledge from stored timeline, summaries and commitments."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import os

from services.contact_filesystem import (
    append_profile_section,
    read_profile_excerpt,
    read_summaries_since,
    read_timeline_since,
    resolve_contact_for_query,
)
from services.whatsapp_backfill import backfill_contact_messages


def _build_context(jid: str, label: str, days: int) -> str:
    parts: list[str] = [f"Contato: {label}", f"Janela: últimos {days} dias", ""]

    timeline = read_timeline_since(jid, days=days)
    if timeline:
        parts.append("Timeline:")
        for e in timeline:
            parts.append(f"- {e.get('ts', '')[:16]}: {e.get('text_preview', '')[:300]}")
        parts.append("")

    summaries = read_summaries_since(jid, days=days)
    if summaries:
        parts.append("Resumos diários:")
        for day, text in summaries:
            parts.append(f"### {day}\n{text[:1500]}")
        parts.append("")

    try:
        from db import init_db, list_commitments_for_chat_since

        init_db()
        rows = list_commitments_for_chat_since(jid, days=days)
        if rows:
            parts.append("Compromissos:")
            for r in rows:
                title = r.get("title") or "?"
                status = r.get("status") or "?"
                raw = (r.get("raw_text") or "")[:200]
                parts.append(f"- [{r.get('id')}] ({status}) {title}: {raw}")
            parts.append("")
    except Exception:
        pass

    existing = read_profile_excerpt(jid, max_chars=1500)
    if existing:
        parts.append("Perfil atual:")
        parts.append(existing)

    body = "\n".join(parts).strip()
    if not timeline and not summaries and "Compromissos:" not in body:
        return ""
    return body


def _llm_synthesize(context: str, label: str, days: int) -> str:
    from llm import build_llm, extract_llm_text

    prompt = f"""Você é o EVI. Com base APENAS no contexto abaixo, escreva uma síntese em português sobre o contato «{label}» nos últimos {days} dias.

Inclua, quando houver evidência:
- Relação/contexto (trabalho, amigo, grupo, etc.)
- Temas recorrentes e assuntos importantes
- Compromissos ou pedidos pendentes/relevantes
- Preferências ou fatos estáveis mencionados

Seja conciso (máx. 12 linhas). Não invente fatos ausentes do contexto.

Contexto:
{context[:12000]}"""
    resp = build_llm(temperature=0.3).invoke(prompt)
    if hasattr(resp, "content"):
        return extract_llm_text(resp.content).strip()
    return str(resp).strip()


def learn_contact(
    name_or_phone: str,
    days: int = 30,
    *,
    fetch_messages: bool = True,
) -> str:
    """Backfill WhatsApp history (optional) then synthesize contact profile."""
    days = max(1, min(int(days), 90))
    resolved, err = resolve_contact_for_query(name_or_phone)
    if not resolved:
        return err
    jid, label = resolved

    backfill_note = ""
    if fetch_messages:
        br = backfill_contact_messages(jid, label=label, days=days)
        backfill_note = br.summary(label, days)
        if br.error and br.fetched == 0:
            backfill_note += "\n\n"

    context = _build_context(jid, label, days)
    if not context:
        hint = (
            f"Não há mensagens ou compromissos sobre «{label}» nos últimos {days} dias."
        )
        if fetch_messages:
            hint += (
                " A Evolution pode não ter histórico antigo em cache; "
                "tente conversar com o contato ou habilitar syncFullHistory na instância."
            )
        if backfill_note:
            return f"{backfill_note}\n{hint}"
        return hint

    try:
        synthesis = _llm_synthesize(context, label, days)
    except Exception as exc:
        return f"Não consegui sintetizar agora: {str(exc)[:180]}"

    if not synthesis:
        return "Síntese vazia — tente novamente mais tarde."

    tz = ZoneInfo(os.getenv("EVI_TIMEZONE", "America/Sao_Paulo"))
    today = datetime.now(tz).strftime("%Y-%m-%d")
    heading = f"Síntese ({today}, últimos {days} dias)"
    append_profile_section(jid, heading=heading, body=synthesis, label=label)

    body = (
        f"Aprendizado sobre **{label}** (últimos {days} dias):\n\n{synthesis}\n\n"
        f"Perfil atualizado em `{heading}`."
    )
    if backfill_note:
        body = f"{backfill_note}\n\n{body}"
    return body
