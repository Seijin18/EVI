"""Limit Evolution webhook volume to recent, relevant messages only."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple, TypedDict

from services.message_sources import IncomingMessage


class DroppedMessage(TypedDict):
    source_id: str
    message_ts: str
    sender: str
    from_me: bool
    is_group: bool
    raw_preview: str
    reason: str

_MAX_SEEN_IDS = 5000


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.isdigit():
            return datetime.utcfromtimestamp(int(ts)).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, OSError):
        return None


def _load_seen_ids(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(data[-_MAX_SEEN_IDS:])
    except (json.JSONDecodeError, OSError):
        pass
    return set()


def _save_seen_ids(path: Path, seen: Set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = list(seen)[-_MAX_SEEN_IDS:]
    path.write_text(json.dumps(trimmed), encoding="utf-8")


def seen_ids_path(log_dir: Path | None = None) -> Path:
    return (log_dir or Path("/tmp/evi-logs")) / "evolution_seen_ids.json"


def claim_message_id(msg_id: str, *, log_dir: Path | None = None) -> bool:
    """Return True if id is new (claim it); False if duplicate and dedupe is on."""
    dedupe = os.getenv("EVI_WHATSAPP_DEDUPE_IDS", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if not dedupe or not msg_id:
        return True
    path = seen_ids_path(log_dir)
    seen = _load_seen_ids(path)
    if msg_id in seen:
        return False
    seen.add(msg_id)
    _save_seen_ids(path, seen)
    return True


def _parse_group_whitelist() -> Set[str]:
    raw = os.getenv("EVI_WHATSAPP_GROUP_WHITELIST", "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def filter_for_processing(
    messages: List[IncomingMessage],
    *,
    log_dir: Path | None = None,
) -> Tuple[List[IncomingMessage], Dict[str, int], List[DroppedMessage]]:
    """Keep only recent, new, incoming direct-chat messages."""
    max_per = int(os.getenv("EVI_WHATSAPP_MAX_PER_WEBHOOK", "10"))
    max_age_h = float(os.getenv("EVI_WHATSAPP_MAX_AGE_HOURS", "24"))
    incoming_only = os.getenv("EVI_WHATSAPP_INCOMING_ONLY", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    skip_groups = os.getenv("EVI_WHATSAPP_SKIP_GROUPS", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    group_whitelist = _parse_group_whitelist()
    dedupe = os.getenv("EVI_WHATSAPP_DEDUPE_IDS", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    stats = {
        "received": len(messages),
        "skipped_from_me": 0,
        "skipped_group": 0,
        "skipped_old": 0,
        "skipped_seen": 0,
        "kept": 0,
    }
    dropped: List[DroppedMessage] = []
    if not messages:
        return [], stats, dropped

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_h)
    seen_path = seen_ids_path(log_dir)
    seen = _load_seen_ids(seen_path) if dedupe else set()

    def _drop(msg: IncomingMessage, reason: str) -> None:
        dropped.append(
            {
                "source_id": msg.id,
                "message_ts": msg.ts or "",
                "sender": msg.sender,
                "from_me": msg.from_me,
                "is_group": msg.is_group,
                "raw_preview": msg.text[:80],
                "reason": reason,
            }
        )

    evi_prefix = os.getenv("EVI_WHATSAPP_REPLY_PREFIX", "[EVI] ").strip()

    candidates: List[IncomingMessage] = []
    for msg in messages:
        if evi_prefix and msg.text.strip().startswith(evi_prefix):
            stats["skipped_from_me"] += 1
            _drop(msg, "evi_echo")
            continue
        if incoming_only and msg.from_me:
            stats["skipped_from_me"] += 1
            _drop(msg, "from_me")
            continue
        if skip_groups and msg.is_group and msg.sender not in group_whitelist:
            stats["skipped_group"] += 1
            _drop(msg, "group")
            continue
        parsed = _parse_ts(msg.ts)
        if parsed and parsed < cutoff:
            stats["skipped_old"] += 1
            _drop(msg, "old")
            continue
        if dedupe and msg.id in seen:
            stats["skipped_seen"] += 1
            _drop(msg, "seen")
            continue
        candidates.append(msg)

    candidates.sort(
        key=lambda m: _parse_ts(m.ts) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    kept = candidates[:max_per]
    stats["kept"] = len(kept)
    for msg in candidates[max_per:]:
        _drop(msg, "max_per_webhook")

    if dedupe and kept:
        seen.update(m.id for m in kept)
        _save_seen_ids(seen_path, seen)

    return kept, stats, dropped
