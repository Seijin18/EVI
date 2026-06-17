"""Backfill WhatsApp chat history from Evolution API into contact timeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from messaging.evolution import EvolutionClient
from services.contact_filesystem import (
    append_timeline,
    ensure_contact,
    memory_enabled,
    timeline_source_ids,
)
from services.evolution_parser import parse_evolution_message_list
from services.evolution_client import is_evi_bot_message


@dataclass
class BackfillResult:
    fetched: int = 0
    appended: int = 0
    skipped_dup: int = 0
    skipped_old: int = 0
    skipped_empty: int = 0
    skipped_evi: int = 0
    error: str = ""

    def summary(self, label: str, days: int) -> str:
        if self.error and self.fetched == 0:
            return f"Não consegui buscar mensagens de «{label}» na Evolution: {self.error}"
        parts = [
            f"WhatsApp «{label}» (últimos {days} dias): "
            f"{self.fetched} mensagens lidas, {self.appended} novas na timeline."
        ]
        if self.skipped_dup:
            parts.append(f"{self.skipped_dup} já existiam.")
        if self.fetched == 0:
            parts.append(
                "Evolution não retornou mensagens — o cache local pode ser curto "
                "(syncFullHistory=false) ou o chat ainda não foi sincronizado."
            )
        elif self.appended == 0 and not self.error:
            parts.append("Nenhuma mensagem nova no período (ou todas filtradas).")
        return " ".join(parts)


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _format_preview(msg, *, label: str) -> str:
    text = (msg.text or "").strip()
    if msg.from_me:
        return f"[eu] {text}"
    who = label or msg.label or "contato"
    return f"[{who}] {text}"


def backfill_contact_messages(
    jid: str,
    *,
    label: str = "",
    days: int = 30,
    limit: int | None = None,
) -> BackfillResult:
    """Import Evolution-cached messages into contact timeline for the last N days."""
    result = BackfillResult()
    days = max(1, min(int(days), 90))

    if not memory_enabled():
        result.error = "EVI_CONTACT_MEMORY_DIR não configurado"
        return result

    ensure_contact(jid, label=label)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    existing_ids = timeline_source_ids(jid)

    client = EvolutionClient()
    raw = client.find_messages(jid, limit=limit)
    if raw is None:
        result.error = "Evolution API indisponível (EVOLUTION_SERVER_URL / instância)"
        return result

    messages = parse_evolution_message_list(raw, remote_jid=jid)
    result.fetched = len(messages)

    if messages and not label:
        for msg in messages:
            if msg.label:
                label = msg.label
                break

    include_from_me = os.getenv("EVI_BACKFILL_INCLUDE_FROM_ME", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    for msg in messages:
        if is_evi_bot_message(msg.text):
            result.skipped_evi += 1
            continue
        if msg.from_me and not include_from_me:
            continue
        if not msg.text.strip():
            result.skipped_empty += 1
            continue
        ts_dt = _parse_ts(msg.ts)
        if ts_dt and ts_dt < cutoff:
            result.skipped_old += 1
            continue
        if msg.id in existing_ids:
            result.skipped_dup += 1
            continue
        preview = _format_preview(msg, label=label)
        ts_iso = ts_dt.isoformat() if ts_dt else msg.ts
        if append_timeline(
            jid,
            source_id=msg.id,
            text_preview=preview,
            label=label,
            ts=ts_iso or None,
            backfill=True,
        ):
            result.appended += 1
            existing_ids.add(msg.id)

    return result
