"""Replay commitment extraction from evolution_webhook.jsonl ingest lines."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.message_sources import IncomingMessage
from services.whatsapp_processor import Commitment


@dataclass
class ReplayResult:
    scanned: int = 0
    extracted: int = 0
    queued: int = 0
    skipped_existing: int = 0

    def summary(self) -> str:
        return (
            f"Replay compromissos: {self.scanned} mensagens no log, "
            f"{self.extracted} extraídas, {self.queued} enfileiradas, "
            f"{self.skipped_existing} já existiam."
        )


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _queue_commitment(msg: IncomingMessage, commitment: Commitment) -> bool:
    """Insert pending commitment + side effects. Returns True if new row."""
    from db import init_db, insert_pending_commitment

    init_db()
    row_id = insert_pending_commitment(
        source="evolution",
        source_id=commitment.source_id,
        ctype=commitment.type,
        title=commitment.title,
        event_date=commitment.date,
        event_time=commitment.time,
        due_date=commitment.due,
        priority=commitment.priority,
        raw_text=msg.text[:2000],
        source_chat=msg.sender,
        source_label=msg.label,
    )
    if not row_id:
        return False
    try:
        from services.contact_filesystem import ingest_commitment

        ingest_commitment(
            jid=msg.sender,
            source_id=commitment.source_id,
            title=commitment.title,
            raw_text=msg.text,
            commitment_id=row_id,
            label=msg.label,
        )
    except Exception:
        pass
    try:
        from services.graph_sync import sync_commitment

        sync_commitment(
            commitment_id=row_id,
            jid=msg.sender,
            title=commitment.title,
            ctype=commitment.type,
            status="pending",
            label=msg.label,
        )
    except Exception:
        pass
    try:
        from services.commitment_capture_notify import notify_commitment_captured

        notify_commitment_captured(row_id, commitment.title, commitment.type)
    except Exception:
        pass
    return True


def replay_commitments_from_evolution_log(
    *,
    jid: str = "",
    days: int = 14,
    log_path: Path | None = None,
) -> ReplayResult:
    """Scan webhook ingest log and queue commitments not yet in Postgres."""
    from services.whatsapp_llm_extract import extract_commitment_with_fallback

    result = ReplayResult()
    days = max(1, min(int(days), 90))
    log_path = log_path or Path(os.getenv("EVI_LOG_DIR", "/logs")) / "evolution_webhook.jsonl"
    if not log_path.is_file():
        return result

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    seen_source_ids: set[str] = set()

    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("step") != "ingest":
            continue
        sender = row.get("sender") or ""
        if jid and sender != jid:
            continue
        source_id = str(row.get("source_id") or "")
        if not source_id or source_id in seen_source_ids:
            continue
        seen_source_ids.add(source_id)

        text = (row.get("raw_text") or row.get("raw_preview") or "").strip()
        if len(text) < 12:
            continue

        ts_raw = str(row.get("message_ts") or row.get("ts") or "")
        ts_dt = _parse_ts(ts_raw)
        if ts_dt and ts_dt < cutoff:
            continue

        result.scanned += 1
        msg = IncomingMessage(
            id=source_id,
            sender=sender,
            text=text,
            ts=ts_raw,
            from_me=bool(row.get("from_me")),
            is_group=bool(row.get("is_group")),
            label=str(row.get("label") or row.get("pushName") or ""),
        )
        commitment, _method = extract_commitment_with_fallback(msg)
        if not commitment:
            continue
        result.extracted += 1
        if _queue_commitment(msg, commitment):
            result.queued += 1
        else:
            result.skipped_existing += 1

    if result.queued:
        try:
            from db import init_db, list_pending_commitments
            from services.commitment_review import maybe_notify_new_pending

            init_db()
            pending = list_pending_commitments(limit=100)
            ids = [p["id"] for p in pending[-result.queued :]]
            maybe_notify_new_pending(ids, ["normal"] * len(ids))
        except Exception:
            pass

    return result
