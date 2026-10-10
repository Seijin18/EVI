"""Evolution payload shape signatures + structural capture of unseen shapes.

A webhook payload's *shape* is the set of (key path, value type) pairs. When a
shape is seen for the first time, a fully redacted copy (no text, no numbers)
is stored so it can become a fixture for the fake Evolution. Everything here is
best-effort: capture never raises and never affects the webhook response.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger("evi.payload_shapes")

MAX_KNOWN = 2000  # in-memory cache bound
MAX_FILES = 500  # on-disk bound (dynamic keys must not flood the disk)
MAX_LIST_ITEMS = 3  # redacted lists keep at most this many items
MAX_DEPTH = 20

_known: Set[str] = set()


def enabled() -> bool:
    return os.getenv("EVI_PAYLOAD_SHAPES", "1").strip().lower() not in ("0", "false", "no", "off", "")


def shapes_dir() -> Path:
    return Path(os.getenv("EVI_PAYLOAD_SHAPES_DIR", "data/payload_shapes"))


def _type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


def _paths(v: Any, prefix: str, out: Set[str], depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        out.add(f"{prefix}:deep")
        return
    if isinstance(v, dict):
        out.add(f"{prefix}:dict")
        for k, child in v.items():
            _paths(child, f"{prefix}.{k}" if prefix else str(k), out, depth + 1)
    elif isinstance(v, list):
        out.add(f"{prefix}:list")
        for item in v:
            _paths(item, f"{prefix}[]", out, depth + 1)
    else:
        out.add(f"{prefix}:{_type_name(v)}")


def signature(payload: Any) -> str:
    """sha256 of the sorted set of `path:type`; list lengths/values don't matter."""
    paths: Set[str] = set()
    _paths(payload, "", paths)
    return hashlib.sha256("\n".join(sorted(paths)).encode("utf-8")).hexdigest()


def _str_class(s: str) -> str:
    n = len(s)
    return "<str:empty>" if n == 0 else "<str:short>" if n <= 16 else "<str:medium>" if n <= 128 else "<str:long>"


def redact(payload: Any, _depth: int = 0) -> Any:
    """Same structure; strings -> class placeholder, numbers -> 0, bools/nulls kept."""
    if _depth > MAX_DEPTH:
        return "<deep>"
    if isinstance(payload, dict):
        return {str(k): redact(v, _depth + 1) for k, v in payload.items()}
    if isinstance(payload, list):
        return [redact(v, _depth + 1) for v in payload[:MAX_LIST_ITEMS]]
    if isinstance(payload, bool) or payload is None:
        return payload
    if isinstance(payload, (int, float)):
        return 0
    if isinstance(payload, str):
        return _str_class(payload)
    return f"<{_type_name(payload)}>"


def capture(payload: Any) -> str | None:
    """Store a redacted copy if the shape is new. Returns the file name written, else None."""
    if not enabled():
        return None
    try:
        sig = signature(payload)
        if sig in _known:
            return None
        if len(_known) >= MAX_KNOWN:
            _known.clear()
        _known.add(sig)
        d = shapes_dir()
        path = d / f"{sig[:16]}.json"
        if path.exists():
            return None
        d.mkdir(parents=True, exist_ok=True)
        if sum(1 for _ in d.glob("*.json")) >= MAX_FILES:
            return None
        event = payload.get("event") or payload.get("type") if isinstance(payload, dict) else None
        record = {
            "signature": sig,
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "event": event if isinstance(event, str) and len(event) <= 64 else None,
            "redacted": redact(payload),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path.name
    except Exception as exc:  # noqa: BLE001
        from services.soft_fail import soft_fail

        soft_fail("payload_shapes.capture", exc)
        return None


def list_new_shapes(since: datetime, until: datetime | None = None) -> List[Dict[str, Any]]:
    """Shapes first seen in [since, until): [{file, signature, first_seen, event}]."""
    out: List[Dict[str, Any]] = []
    d = shapes_dir()
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            fs = datetime.fromisoformat(rec["first_seen"])
            if fs.tzinfo is None:
                fs = fs.replace(tzinfo=timezone.utc)
            if fs >= since and (until is None or fs < until):
                out.append(
                    {"file": p.name, "signature": rec.get("signature"), "first_seen": fs, "event": rec.get("event")}
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("payload_shapes: unreadable %s: %s", p.name, type(exc).__name__)
    out.sort(key=lambda r: r["first_seen"])
    return out
