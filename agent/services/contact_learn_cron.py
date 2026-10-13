"""Daily contact knowledge refresh from the cold timeline (no Evolution backfill)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from services.contact_filesystem import contact_dir, is_direct_jid, list_contact_dirs, memory_enabled, sanitize_jid

DEFAULT_LIMIT = 15
MAX_LIMIT = 50


def _parse_ts(raw: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _newest_timeline_ts(jid: str) -> datetime | None:
    path = contact_dir(jid) / "timeline.jsonl"
    if not path.is_file():
        return None
    newest: datetime | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            ts = _parse_ts(json.loads(line).get("ts") or "")
        except (json.JSONDecodeError, AttributeError):
            continue
        if ts and (newest is None or ts > newest):
            newest = ts
    return newest


def _candidates() -> list[tuple[datetime, str]]:
    """Direct-contact dirs whose timeline is newer than ``knowledge_updated``, newest first."""
    from services.contact_identity import canonical_jid
    from services.contact_knowledge import read_knowledge

    out: list[tuple[datetime, str]] = []
    seen: set[str] = set()
    for d in list_contact_dirs():
        jid = d.name
        if not is_direct_jid(jid):
            continue
        canon = canonical_jid(jid)
        if sanitize_jid(canon) != jid or jid in seen:
            continue  # a non-canonical dir; its canonical sibling is the one to learn
        seen.add(jid)
        newest = _newest_timeline_ts(jid)
        if newest is None:
            continue
        profile = read_knowledge(jid)
        updated = profile.knowledge_updated if profile else None
        if updated is not None:
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if newest <= updated:
                continue
        out.append((newest, jid))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def run_contact_learn_batch(*, limit: int | None = None) -> dict[str, Any]:
    """Update knowledge of the ``limit`` most recently active contacts with new messages."""
    if not memory_enabled():
        return {"ok": True, "skipped": True, "reason": "EVI_CONTACT_MEMORY_DIR unset"}

    from services.contact_knowledge import update_contact_knowledge
    from services.soft_fail import soft_fail

    if limit is None:
        try:
            limit = int(os.getenv("EVI_CONTACT_LEARN_LIMIT", str(DEFAULT_LIMIT)))
        except ValueError:
            limit = DEFAULT_LIMIT
    limit = max(1, min(int(limit), MAX_LIMIT))

    counts = {"updated": 0, "skipped": 0, "errors": 0, "no_answer": 0}
    updated_jids: list[str] = []
    # Each contact is attempted at most once per run, so a no-answer is never retried here.
    for _, jid in _candidates()[:limit]:
        try:
            status = (update_contact_knowledge(jid) or {}).get("status")
        except Exception as exc:  # noqa: BLE001 - one contact must not stop the batch
            counts["errors"] += 1
            soft_fail("contact_learn_cron.update", exc)
            continue
        if status == "ok":
            counts["updated"] += 1
            updated_jids.append(jid)
        elif status == "no-answer":
            counts["no_answer"] += 1
        elif status in ("invalid",):
            counts["errors"] += 1
        else:
            counts["skipped"] += 1

    notify = False
    if updated_jids and os.getenv("EVI_CONTACT_LEARN_NOTIFY", "false").lower() in ("1", "true", "yes"):
        notify = _notify_control(updated_jids)

    return {"ok": True, **counts, "notified": notify}


def _notify_control(jids_learned: list[str]) -> bool:
    from services.whatsapp_control import parse_control_jids
    from services.evolution_client import send_whatsapp_text
    from services.promise_context import _contact_name

    jids = parse_control_jids()
    if not jids:
        return False
    names = [_contact_name(j) for j in jids_learned[:5]]
    body = "Conhecimento de contatos atualizado: " + ", ".join(names)
    sent = False
    for jid in jids:
        if send_whatsapp_text(jid, body, add_prefix=True):
            sent = True
    return sent
