"""Cold per-contact filesystem memory (Etapa 5a)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_JID_SAFE = re.compile(r"[^a-zA-Z0-9@._-]+")
_PROFILE_TEMPLATE = """# Contact memory

- **jid**: {jid}
- **label**: {label}
- **created**: {created}

Stable facts and preferences go here (manual or future LLM enrichment).
"""


def memory_enabled() -> bool:
    return bool(os.getenv("EVI_CONTACT_MEMORY_DIR", "").strip())


def memory_root() -> Path:
    raw = os.getenv("EVI_CONTACT_MEMORY_DIR", "").strip()
    if not raw:
        raise RuntimeError("EVI_CONTACT_MEMORY_DIR not set")
    return Path(raw)


def sanitize_jid(jid: str) -> str:
    cleaned = _JID_SAFE.sub("_", (jid or "unknown").strip())
    return cleaned[:120] or "unknown"


def contact_dir(jid: str) -> Path:
    return memory_root() / "contacts" / sanitize_jid(jid)


def ensure_contact(jid: str, *, label: str = "") -> Path:
    root = contact_dir(jid)
    root.mkdir(parents=True, exist_ok=True)
    (root / "summaries").mkdir(exist_ok=True)
    profile = root / "profile.md"
    if not profile.exists():
        profile.write_text(
            _PROFILE_TEMPLATE.format(
                jid=jid,
                label=label or jid,
                created=datetime.now(timezone.utc).isoformat(),
            ),
            encoding="utf-8",
        )
    timeline = root / "timeline.jsonl"
    if not timeline.exists():
        timeline.touch()
    return root


def append_timeline(
    jid: str,
    *,
    source_id: str,
    text_preview: str,
    commitment_id: int | None = None,
    label: str = "",
) -> bool:
    if not memory_enabled() or not jid:
        return False
    ensure_contact(jid, label=label)
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "text_preview": (text_preview or "")[:500],
    }
    if commitment_id is not None:
        entry["commitment_id"] = commitment_id
    path = contact_dir(jid) / "timeline.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return True


def ingest_commitment(
    *,
    jid: str,
    source_id: str,
    title: str,
    raw_text: str,
    commitment_id: int,
    label: str = "",
) -> bool:
    """Write timeline entry after a commitment is queued."""
    preview = f"{title}: {(raw_text or '')[:200]}".strip()
    return append_timeline(
        jid,
        source_id=source_id,
        text_preview=preview,
        commitment_id=commitment_id,
        label=label,
    )


def list_contact_dirs() -> list[Path]:
    if not memory_enabled():
        return []
    base = memory_root() / "contacts"
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir())
