"""Canonical contact identity: ``…@lid`` ↔ ``…@s.whatsapp.net`` (evi-contact-knowledge §9).

WhatsApp delivers the same person under two JIDs; Evolution exposes the pair in
``key.remoteJidAlt``. The pair is stored in ``wa_jid_alias`` and every per-contact
path (timeline, reply debts, WhatsApp summary) goes through ``canonical_jid``.
Every function here soft-fails: an unavailable DB means "jid unchanged".
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.soft_fail import soft_fail

_LID = "@lid"
_PHONE = "@s.whatsapp.net"
_TTL_S = 60.0
_FAIL_TTL_S = 30.0  # unreachable DB: do not retry on every @lid message
_cache: dict[str, tuple[float, str]] = {}
_MERGED_MARK = ".merged-"


def reset_cache_for_tests() -> None:
    _cache.clear()


def canonical_jid(jid: str) -> str:
    """Phone JID when the alias of a ``@lid`` is known, else ``jid`` itself."""
    j = jid or ""
    if not j.endswith(_LID) or not os.getenv("DATABASE_URL"):
        return j
    now = time.monotonic()
    hit = _cache.get(j)
    if hit and hit[0] > now:
        return hit[1]
    try:
        import db

        db.init_db()
        phone = db.get_jid_alias(j) or j
    except Exception as exc:  # noqa: BLE001
        soft_fail("contact_identity.canonical_jid", exc)
        _cache[j] = (now + _FAIL_TTL_S, j)
        return j
    _cache[j] = (now + _TTL_S, phone)
    return phone


def record_alias(lid: str, phone_jid: str) -> bool:
    """Persist one pair; True when it was written. Only lid -> phone pairs are accepted."""
    if not (lid or "").endswith(_LID) or not (phone_jid or "").endswith(_PHONE):
        return False
    if not os.getenv("DATABASE_URL"):
        return False
    hit = _cache.get(lid)
    if hit and hit[0] > time.monotonic() and hit[1] == phone_jid:
        return False
    try:
        import db

        db.init_db()
        db.upsert_jid_alias(lid, phone_jid)
        # State recorded under the lid before the alias was known joins the phone's.
        db.merge_conversation_state(lid, phone_jid)
    except Exception as exc:  # noqa: BLE001
        soft_fail("contact_identity.record_alias", exc)
        return False
    _cache[lid] = (time.monotonic() + _TTL_S, phone_jid)
    return True


def record_alias_from_message(raw: Any) -> bool:
    """Record the pair carried by one raw Evolution message record (``key.remoteJid`` +
    ``key.remoteJidAlt``). Also accepts a ``data``-wrapped payload."""
    try:
        rec = raw
        if isinstance(rec, dict) and isinstance(rec.get("data"), dict) and "key" not in rec:
            rec = rec["data"]
        key = rec.get("key") if isinstance(rec, dict) else None
        if not isinstance(key, dict):
            return False
        main_jid = str(key.get("remoteJid") or rec.get("remoteJid") or "")
        alt = str(key.get("remoteJidAlt") or "")
        return record_alias(main_jid, alt)
    except Exception as exc:  # noqa: BLE001
        soft_fail("contact_identity.record_alias_from_message", exc)
        return False


# --- migration: merge @lid contact dirs into the phone's ---------------------


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _ts_key(row: dict[str, Any]) -> tuple[int, float, str]:
    raw = str(row.get("ts") or "")
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (0, dt.timestamp(), raw)
    except ValueError:
        return (1, 0.0, raw)


def merge_timelines(
    target: list[dict[str, Any]], extra: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """Union by ``source_id`` (or (ts, text_preview) when absent), ordered by ts.
    Returns (merged, number of rows taken from ``extra``)."""
    seen_ids = {str(r["source_id"]) for r in target if r.get("source_id")}
    seen_pairs = {(r.get("ts"), r.get("text_preview")) for r in target}
    merged = list(target)
    added = 0
    for r in extra:
        sid = r.get("source_id")
        pair = (r.get("ts"), r.get("text_preview"))
        if (sid and str(sid) in seen_ids) or pair in seen_pairs:
            continue
        if sid:
            seen_ids.add(str(sid))
        seen_pairs.add(pair)
        merged.append(r)
        added += 1
    merged.sort(key=_ts_key)  # stable
    return merged, added


def _merge_dir(lid_dir: Path, phone_dir: Path, phone_jid: str, stamp: str) -> dict[str, int]:
    from services.contact_filesystem import _PROFILE_TEMPLATE

    phone_dir.mkdir(parents=True, exist_ok=True)
    (phone_dir / "summaries").mkdir(exist_ok=True)

    # timeline
    merged, added = merge_timelines(
        _read_jsonl(phone_dir / "timeline.jsonl"), _read_jsonl(lid_dir / "timeline.jsonl")
    )
    tl = phone_dir / "timeline.jsonl"
    if tl.is_file() and tl.stat().st_size:
        shutil.copy2(tl, phone_dir / f"timeline.jsonl.pre-merge-{stamp}")
    tmp = phone_dir / f"timeline.jsonl.tmp-{os.getpid()}"
    tmp.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged), encoding="utf-8"
    )
    os.replace(tmp, tl)

    # summaries/ and history.md: copied only when absent
    copied = 0
    lsum = lid_dir / "summaries"
    if lsum.is_dir():
        for f in lsum.iterdir():
            dest = phone_dir / "summaries" / f.name
            if f.is_file() and not dest.exists():
                shutil.copy2(f, dest)
                copied += 1
    if (lid_dir / "history.md").is_file() and not (phone_dir / "history.md").exists():
        shutil.copy2(lid_dir / "history.md", phone_dir / "history.md")
        copied += 1

    # profile: the phone's stays; the lid's goes to history.md as a section
    lid_profile = lid_dir / "profile.md"
    if not (phone_dir / "profile.md").exists():
        (phone_dir / "profile.md").write_text(
            _PROFILE_TEMPLATE.format(jid=phone_jid, label=phone_jid, created=stamp),
            encoding="utf-8",
        )
    profile_moved = 0
    if lid_profile.is_file():
        body = lid_profile.read_text(encoding="utf-8").strip()
        if body:
            hist = phone_dir / "history.md"
            block = "## Perfil anterior (@lid)\n\n" + body + "\n"
            cur = hist.read_text(encoding="utf-8") if hist.exists() else ""
            if block not in cur:
                prev = cur.rstrip() + "\n\n" if cur.strip() else ""
                hist.write_text(prev + block, encoding="utf-8")
                profile_moved = 1
    return {"timeline_added": added, "files_copied": copied, "profiles_to_history": profile_moved}


def migrate_lid_dirs(*, apply: bool = False) -> dict[str, int]:
    """Merge every ``@lid`` contact dir whose alias is known into the phone's dir.

    Dry-run by default; run ``--apply`` when idle (no live ingestion). The phone
    timeline is backed up to ``timeline.jsonl.pre-merge-<ts>`` and replaced atomically.
    The lid dir is renamed ``<dir>.merged-<ts>``, never deleted;
    ``wa_conversation_state`` rows are folded lid -> phone. Returns counts only.
    """
    from services.contact_filesystem import (
        list_contact_dirs,
        memory_enabled,
        memory_root,
        sanitize_jid,
    )

    counts = {
        "lid_dirs": 0, "mergeable": 0, "merged": 0, "timeline_added": 0,
        "files_copied": 0, "profiles_to_history": 0, "state_rows_merged": 0,
    }
    if not memory_enabled():
        return counts
    aliases: dict[str, str] = {}
    try:
        import db

        db.init_db()
        aliases = {a["lid"]: a["phone_jid"] for a in db.list_jid_aliases()}
    except Exception as exc:  # noqa: BLE001
        soft_fail("contact_identity.migrate_aliases", exc)
    by_dir = {sanitize_jid(lid): (lid, phone) for lid, phone in aliases.items()}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = memory_root() / "contacts"
    for path in list_contact_dirs():
        if _MERGED_MARK in path.name or not path.name.endswith(_LID):
            continue
        counts["lid_dirs"] += 1
        hit = by_dir.get(path.name)
        if not hit:
            continue
        lid, phone = hit
        counts["mergeable"] += 1
        if not apply:
            continue
        res = _merge_dir(path, root / sanitize_jid(phone), phone, stamp)
        for k, v in res.items():
            counts[k] += v
        path.rename(path.with_name(f"{path.name}{_MERGED_MARK}{stamp}"))
        counts["merged"] += 1
    if apply:
        for lid, phone in aliases.items():
            try:
                if db.merge_conversation_state(lid, phone):
                    counts["state_rows_merged"] += 1
            except Exception as exc:  # noqa: BLE001
                soft_fail("contact_identity.migrate_state", exc)
    else:
        for lid in aliases:
            try:
                if db.get_state(lid):
                    counts["state_rows_merged"] += 1  # would merge
            except Exception as exc:  # noqa: BLE001
                soft_fail("contact_identity.migrate_state_dry", exc)
    return counts


def format_migration(counts: dict[str, int], *, apply: bool) -> str:
    mode = "APPLIED" if apply else "dry-run (use --apply)"
    body = ", ".join(f"{k}={v}" for k, v in counts.items())
    return f"contact-identity-migrate {mode}: {body}"
