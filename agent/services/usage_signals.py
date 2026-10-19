"""Implicit usage signals over turn_log (evi-usage-validation, task 2.2).

Pure helpers (`compute_signals`, `turn_succeeded`) plus the idempotent job
(`run_usage_signals`) and the retention prune (`prune_turn_log`). The signals dict
of each turn is fully recomputed and overwritten on every run.

Rules:
- tool_failed: some tool in `tools` has ok=false.
- correction: next turn (same session, <= NEXT_TURN_WINDOW_S) matches CORRECTION_PATTERNS.
- rephrase: next turn in the window with token Jaccard >= REPHRASE_THRESHOLD.
- cant_do: reply contains one of CANT_DO_PATTERNS.
Commands (user_text starting with "/") are neither A nor B for correction/rephrase.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

# Bump when a pattern/threshold changes, so reports can be compared across versions.
PATTERNS_VERSION = 1

NEXT_TURN_WINDOW_S = 180
REPHRASE_THRESHOLD = 0.6
DEFAULT_WINDOW_DAYS = 2
RETENTION_DAYS = 180

# Matched against normalized text (lowercase, no accents/punctuation).
# A bare leading "nao" is deliberately NOT a pattern ("Não, obrigado" is not a correction).
CORRECTION_PATTERNS = [
    r"\bnao era\b",
    r"\bnao e isso\b",
    r"\bnao foi isso\b",
    r"\bnao e esse\b",
    r"\bnao e essa\b",
    r"\bna verdade\b",
    r"\berrado\b",
    r"\berrada\b",
    r"\bvoce errou\b",
    r"^errou\b",
]
_CORRECTION_RE = [re.compile(p) for p in CORRECTION_PATTERNS]

CANT_DO_PATTERNS = ["nao consigo", "nao tenho acesso", "nao posso"]

STOPWORDS = frozenset(
    """
    a o as os um uma uns umas de do da dos das em no na nos nas por para pra com
    e ou que se me meu meus minha minhas te seu seus sua suas eu voce vc
    consegue conseguiria pode poderia podia quero queria gostaria favor
    """.split()
)

FAILURE_SIGNALS = ("tool_failed", "correction", "rephrase", "cant_do")


def normalize(text: str | None) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    s = unicodedata.normalize("NFKD", (text or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(text: str | None) -> frozenset:
    return frozenset(t for t in normalize(text).split() if t not in STOPWORDS)


def similarity(a: str | None, b: str | None) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_command(turn: Dict[str, Any] | None) -> bool:
    return bool(turn) and (turn.get("user_text") or "").lstrip().startswith("/")


def matches_correction(text: str | None) -> bool:
    n = normalize(text)
    return any(rx.search(n) for rx in _CORRECTION_RE)


def _tool_failed(turn: Dict[str, Any]) -> bool:
    return any(isinstance(t, dict) and t.get("ok") is False for t in (turn.get("tools") or []))


def _cant_do(turn: Dict[str, Any]) -> bool:
    n = normalize(turn.get("reply_text"))
    return any(p in n for p in CANT_DO_PATTERNS)


def _within_window(turn: Dict[str, Any], nxt: Dict[str, Any]) -> bool:
    delta = (nxt["ts"] - turn["ts"]).total_seconds()
    return 0 <= delta <= NEXT_TURN_WINDOW_S


def compute_signals(turn: Dict[str, Any], next_turn: Dict[str, Any] | None) -> Dict[str, bool]:
    """Signals for `turn` given the next turn of the same session (or None).

    Only fired signals are present (value True); a clean turn yields {}.
    """
    if is_command(turn):
        return {}
    sig: Dict[str, bool] = {}
    if _tool_failed(turn):
        sig["tool_failed"] = True
    if _cant_do(turn):
        sig["cant_do"] = True
    if next_turn and not is_command(next_turn) and _within_window(turn, next_turn):
        if matches_correction(next_turn.get("user_text")):
            sig["correction"] = True
        if similarity(turn.get("user_text"), next_turn.get("user_text")) >= REPHRASE_THRESHOLD:
            sig["rephrase"] = True
    return sig


def turn_succeeded(turn: Dict[str, Any]) -> bool:
    """Success = no failure signal and no 'ruim' feedback (feedback 'bom' is strong success)."""
    if turn.get("feedback") == "ruim":
        return False
    signals = turn.get("signals") or {}
    return not any(signals.get(k) for k in FAILURE_SIGNALS)


def run_usage_signals(since=None, until=None) -> Dict[str, Any]:
    """Recompute and overwrite `signals` for turns in [since, until). Idempotent.

    Default window: last DEFAULT_WINDOW_DAYS days, so late "next turns" are caught on re-runs.
    Returns {turns, updated, by_rule: {rule: count}, since, until, patterns_version}.
    """
    import db

    now = datetime.now(timezone.utc)
    until = until or now
    since = since or (until - timedelta(days=DEFAULT_WINDOW_DAYS))
    # Fetch a little past `until` so the last turns still see their next turn.
    rows = [
        r
        for r in db.list_turns(since, until + timedelta(seconds=NEXT_TURN_WINDOW_S))
        if r.get("channel") != "scheduled"  # not user activity: no follow-up signals
    ]

    next_by_id: Dict[int, Dict[str, Any] | None] = {}
    last_in_session: Dict[str, Dict[str, Any]] = {}
    for row in reversed(rows):  # newest first
        if is_command(row):
            next_by_id[row["id"]] = None
            continue
        next_by_id[row["id"]] = last_in_session.get(row["session_id"])
        last_in_session[row["session_id"]] = row

    by_rule: Dict[str, int] = {k: 0 for k in FAILURE_SIGNALS}
    scanned = updated = 0
    for row in rows:
        if row["ts"] >= until:
            continue
        scanned += 1
        sig = compute_signals(row, next_by_id.get(row["id"]))
        for k in sig:
            by_rule[k] = by_rule.get(k, 0) + 1
        if sig != (row.get("signals") or {}):
            db.update_turn_signals(row["id"], sig)
            updated += 1
    return {
        "turns": scanned,
        "updated": updated,
        "by_rule": by_rule,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "patterns_version": PATTERNS_VERSION,
    }


def prune_turn_log(days: int = RETENTION_DAYS) -> int:
    """Delete turn_log rows older than `days`. Returns the number deleted."""
    import db

    return db.delete_turns_older_than(days)
