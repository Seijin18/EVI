"""Weekly contact re-learning from FS + Postgres (no Evolution backfill)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from services.contact_filesystem import collect_known_contacts, memory_enabled, read_timeline_since
from services.contact_learning import learn_contact


def run_contact_learn_batch(*, days: int = 7, limit: int = 10) -> dict[str, Any]:
    """Re-synthesize contacts with recent timeline activity."""
    if not memory_enabled():
        return {"ok": True, "skipped": True, "reason": "EVI_CONTACT_MEMORY_DIR unset"}

    days = max(1, min(int(days), 30))
    limit = max(1, min(int(limit), 25))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    processed: list[str] = []
    errors: list[str] = []

    for c in collect_known_contacts():
        if len(processed) >= limit:
            break
        jid = c.get("jid") or ""
        label = c.get("label") or jid
        timeline = read_timeline_since(jid, days=days)
        if not timeline:
            continue
        newest = timeline[-1].get("ts") or ""
        try:
            ts = datetime.fromisoformat(newest.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                continue
        except ValueError:
            continue
        try:
            result = learn_contact(label, days=days, fetch_messages=False)
            processed.append(label)
            if "Não há mensagens" in result or "Não consegui" in result:
                errors.append(f"{label}: {result[:80]}")
        except Exception as exc:
            errors.append(f"{label}: {str(exc)[:80]}")

    notify = False
    if processed and os.getenv("EVI_CONTACT_LEARN_NOTIFY", "false").lower() in (
        "1",
        "true",
        "yes",
    ):
        notify = _notify_control(processed)

    return {
        "ok": True,
        "processed": processed,
        "count": len(processed),
        "errors": errors[:5],
        "notified": notify,
    }


def _notify_control(labels: list[str]) -> bool:
    from services.whatsapp_control import parse_control_jids
    from services.evolution_client import send_whatsapp_text

    jids = parse_control_jids()
    if not jids:
        return False
    body = "Síntese automática de contatos: " + ", ".join(labels[:5])
    sent = False
    for jid in jids:
        if send_whatsapp_text(jid, body, add_prefix=True):
            sent = True
    return sent
