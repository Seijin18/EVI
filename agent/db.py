"""Postgres session persistence (MVP)."""

import json
import os
import threading
from contextlib import contextmanager
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://evi:evi@postgres:5432/evidb",
)

_init_lock = threading.Lock()
_db_initialized = False


def init_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    with _init_lock:
        if _db_initialized:
            return
        _run_migrations()
        _db_initialized = True


def _run_migrations() -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(128) NOT NULL,
                    role VARCHAR(32) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS pending_commitments (
                    id SERIAL PRIMARY KEY,
                    source VARCHAR(32) NOT NULL DEFAULT 'whatsapp',
                    source_id VARCHAR(128) NOT NULL,
                    type VARCHAR(16) NOT NULL,
                    title TEXT NOT NULL,
                    event_date DATE,
                    event_time VARCHAR(8),
                    due_date DATE,
                    priority VARCHAR(16) NOT NULL DEFAULT 'normal',
                    status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    raw_text TEXT,
                    notified_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(source, source_id)
                );
                CREATE INDEX IF NOT EXISTS idx_pending_status
                    ON pending_commitments(status, created_at DESC);
                ALTER TABLE pending_commitments
                    ADD COLUMN IF NOT EXISTS source_chat VARCHAR(128);
                ALTER TABLE pending_commitments
                    ADD COLUMN IF NOT EXISTS source_label VARCHAR(128);
                ALTER TABLE pending_commitments
                    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;
                ALTER TABLE pending_commitments
                    ADD COLUMN IF NOT EXISTS confirmed_via VARCHAR(32);
                CREATE TABLE IF NOT EXISTS session_tool_snapshots (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(128) NOT NULL,
                    tool_name VARCHAR(64) NOT NULL,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_session_tool_snapshots
                    ON session_tool_snapshots(session_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS whatsapp_contacts (
                    jid VARCHAR(128) PRIMARY KEY,
                    whatsapp_label VARCHAR(256),
                    display_name VARCHAR(256),
                    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
                    phone VARCHAR(32),
                    notes TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_whatsapp_contacts_display
                    ON whatsapp_contacts(display_name);
                CREATE TABLE IF NOT EXISTS turn_log (
                    id BIGSERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
                    session_id VARCHAR(128) NOT NULL,
                    channel VARCHAR(16) NOT NULL,
                    user_text TEXT NOT NULL,
                    reply_text TEXT,
                    tools JSONB NOT NULL DEFAULT '[]'::jsonb,
                    latency_ms INTEGER,
                    llm_calls INTEGER,
                    error TEXT,
                    is_test BOOLEAN NOT NULL DEFAULT false,
                    feedback VARCHAR(8),
                    feedback_note TEXT,
                    signals JSONB NOT NULL DEFAULT '{}'::jsonb
                );
                CREATE INDEX IF NOT EXISTS turn_log_ts ON turn_log (ts);
                CREATE INDEX IF NOT EXISTS turn_log_session
                    ON turn_log (session_id, ts);
                CREATE TABLE IF NOT EXISTS probe_log (
                    id BIGSERIAL PRIMARY KEY,
                    day DATE NOT NULL,
                    check_name VARCHAR(64) NOT NULL,
                    ok BOOLEAN NOT NULL,
                    reason VARCHAR(256),
                    ms INTEGER,
                    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
                    notified BOOLEAN NOT NULL DEFAULT false
                );
                CREATE INDEX IF NOT EXISTS probe_log_day_check
                    ON probe_log (day, check_name);
                CREATE TABLE IF NOT EXISTS probe_notified (
                    day DATE NOT NULL,
                    check_name VARCHAR(64) NOT NULL,
                    PRIMARY KEY (day, check_name)
                );
                CREATE TABLE IF NOT EXISTS briefing_log (
                    id SERIAL PRIMARY KEY,
                    day DATE NOT NULL,
                    kind VARCHAR(16) NOT NULL,
                    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    ok BOOLEAN NOT NULL,
                    sections JSONB NOT NULL,
                    replied_at TIMESTAMPTZ,
                    UNIQUE (day, kind)
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    text TEXT NOT NULL,
                    due_at TIMESTAMPTZ NOT NULL,
                    repeat VARCHAR(16),
                    status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    chat_id VARCHAR(64) NOT NULL,
                    created_from VARCHAR(16) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    claimed_at TIMESTAMPTZ,
                    fired_at TIMESTAMPTZ,
                    drift_s INTEGER
                );
                CREATE INDEX IF NOT EXISTS reminders_due
                    ON reminders (status, due_at);
                ALTER TABLE reminders ADD COLUMN IF NOT EXISTS anchor_day SMALLINT;
                ALTER TABLE reminders ADD COLUMN IF NOT EXISTS snooze_until TIMESTAMPTZ;
                CREATE TABLE IF NOT EXISTS reminder_fires (
                    id SERIAL PRIMARY KEY,
                    reminder_id INTEGER NOT NULL,
                    due_at TIMESTAMPTZ NOT NULL,
                    fired_at TIMESTAMPTZ NOT NULL,
                    drift_s INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS reminder_fires_fired_at
                    ON reminder_fires (fired_at);
                """
            )
        conn.commit()


def reset_db_init_for_tests() -> None:
    """Allow tests to re-run migrations."""
    global _db_initialized
    with _init_lock:
        _db_initialized = False


@contextmanager
def _conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def save_message(session_id: str, role: str, content: str) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
                (session_id, role, content),
            )
        conn.commit()


def load_recent_messages(session_id: str, limit: int = 16) -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (session_id, limit),
            )
            rows = cur.fetchall()
    rows.reverse()
    return [dict(r) for r in rows]


def insert_pending_commitment(
    *,
    source: str,
    source_id: str,
    ctype: str,
    title: str,
    event_date: str | None = None,
    event_time: str | None = None,
    due_date: str | None = None,
    priority: str = "normal",
    raw_text: str = "",
    source_chat: str = "",
    source_label: str = "",
) -> int | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pending_commitments (
                    source, source_id, type, title,
                    event_date, event_time, due_date,
                    priority, raw_text, source_chat, source_label
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, source_id) DO NOTHING
                RETURNING id
                """,
                (
                    source,
                    source_id,
                    ctype,
                    title,
                    event_date or None,
                    event_time or None,
                    due_date or None,
                    priority,
                    raw_text[:2000] if raw_text else None,
                    source_chat or None,
                    source_label or None,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return row[0] if row else None


def list_pending_commitments(limit: int = 50, *, include_past: bool = False) -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            past_filter = ""
            if not include_past:
                past_filter = """
                  AND NOT (
                    (event_date IS NOT NULL AND event_date < CURRENT_DATE)
                    OR (due_date IS NOT NULL AND due_date < CURRENT_DATE)
                  )
                """
            cur.execute(
                f"""
                SELECT id, source, source_id, type, title,
                       event_date::text, event_time, due_date::text,
                       priority, status, raw_text, source_chat, source_label,
                       confirmed_at, confirmed_via, created_at
                FROM pending_commitments
                WHERE status = 'pending'
                {past_filter}
                ORDER BY
                    CASE priority
                        WHEN 'urgent' THEN 0
                        WHEN 'work' THEN 1
                        WHEN 'university' THEN 2
                        ELSE 3
                    END,
                    COALESCE(event_date, due_date) ASC NULLS LAST,
                    created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def update_commitment_status(
    commitment_id: int,
    status: str,
    *,
    confirmed_via: str | None = None,
) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            if status == "scheduled" and confirmed_via:
                cur.execute(
                    """
                    UPDATE pending_commitments
                    SET status = %s, confirmed_at = NOW(), confirmed_via = %s
                    WHERE id = %s AND status = 'pending'
                    """,
                    (status, confirmed_via, commitment_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE pending_commitments
                    SET status = %s
                    WHERE id = %s AND status = 'pending'
                    """,
                    (status, commitment_id),
                )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def list_scheduled_today(limit: int = 50) -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, source, source_id, type, title,
                       event_date::text, event_time, due_date::text,
                       priority, status, source_chat, source_label,
                       confirmed_at, confirmed_via, created_at
                FROM pending_commitments
                WHERE status = 'scheduled'
                  AND (
                    event_date = CURRENT_DATE
                    OR due_date = CURRENT_DATE
                    OR confirmed_at::date = CURRENT_DATE
                  )
                ORDER BY confirmed_at DESC NULLS LAST, created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def list_whatsapp_contact_sources(limit: int = 50) -> List[Dict[str, Any]]:
    """Distinct WhatsApp chats with label and commitment count."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT source_chat,
                       MAX(source_label) AS source_label,
                       COUNT(*) AS commitment_count
                FROM pending_commitments
                WHERE source_chat IS NOT NULL AND source_chat <> ''
                GROUP BY source_chat
                ORDER BY MAX(source_label) NULLS LAST, source_chat
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def upsert_whatsapp_contact(
    jid: str,
    *,
    whatsapp_label: str | None = None,
    display_name: str | None = None,
    aliases: List[str] | None = None,
    phone: str | None = None,
    notes: str | None = None,
) -> None:
    """Insert or update a WhatsApp contact row."""
    if not jid:
        return
    import json

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT whatsapp_label, display_name, aliases, phone, notes FROM whatsapp_contacts WHERE jid = %s",
                (jid,),
            )
            row = cur.fetchone()
            if row:
                wl, dn, existing_aliases, ph, nt = row
                merged_wl = whatsapp_label if whatsapp_label is not None else wl
                merged_dn = display_name if display_name is not None else dn
                merged_ph = phone if phone is not None else ph
                merged_nt = notes if notes is not None else nt
                alias_list = list(existing_aliases or [])
                if aliases:
                    seen = {a.casefold() for a in alias_list if isinstance(a, str)}
                    for alias in aliases:
                        alias = (alias or "").strip()
                        if alias and alias.casefold() not in seen:
                            alias_list.append(alias)
                            seen.add(alias.casefold())
                cur.execute(
                    """
                    UPDATE whatsapp_contacts
                    SET whatsapp_label = %s,
                        display_name = %s,
                        aliases = %s::jsonb,
                        phone = %s,
                        notes = %s,
                        updated_at = NOW()
                    WHERE jid = %s
                    """,
                    (
                        merged_wl,
                        merged_dn,
                        json.dumps(alias_list),
                        merged_ph,
                        merged_nt,
                        jid,
                    ),
                )
            else:
                alias_list = [a.strip() for a in (aliases or []) if (a or "").strip()]
                cur.execute(
                    """
                    INSERT INTO whatsapp_contacts (
                        jid, whatsapp_label, display_name, aliases, phone, notes
                    ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                    """,
                    (
                        jid,
                        whatsapp_label,
                        display_name,
                        json.dumps(alias_list),
                        phone,
                        notes,
                    ),
                )
        conn.commit()


def get_whatsapp_contact(jid: str) -> Dict[str, Any] | None:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT jid, whatsapp_label, display_name, aliases, phone, notes,
                       created_at, updated_at
                FROM whatsapp_contacts
                WHERE jid = %s
                """,
                (jid,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def list_whatsapp_contacts_db(limit: int = 500) -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT jid, whatsapp_label, display_name, aliases, phone, notes,
                       created_at, updated_at
                FROM whatsapp_contacts
                ORDER BY COALESCE(display_name, whatsapp_label, jid)
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def list_commitments_for_chat(jid: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Recent commitments for a WhatsApp chat (any status)."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, type, title, status,
                       event_date::text, due_date::text,
                       source_label, created_at
                FROM pending_commitments
                WHERE source_chat = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (jid, limit),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def list_commitments_for_chat_since(
    jid: str,
    *,
    days: int = 30,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Commitments for a chat created within the last N days."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, type, title, status,
                       event_date::text, due_date::text,
                       source_label, raw_text, created_at
                FROM pending_commitments
                WHERE source_chat = %s
                  AND created_at >= NOW() - (%s || ' days')::interval
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (jid, str(int(days)), limit),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def count_unnotified_pending() -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM pending_commitments
                WHERE status = 'pending' AND notified_at IS NULL
                """
            )
            return int(cur.fetchone()[0])


def save_tool_snapshot(session_id: str, tool_name: str, payload: Dict[str, Any]) -> None:
    import json

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO session_tool_snapshots (session_id, tool_name, payload)
                VALUES (%s, %s, %s::jsonb)
                """,
                (session_id, tool_name, json.dumps(payload)),
            )
        conn.commit()


def load_tool_snapshots(session_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT tool_name, payload, created_at
                FROM session_tool_snapshots
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (session_id, limit),
            )
            rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])
        out.append(item)
    return out


def mark_pending_notified(ids: List[int]) -> None:
    if not ids:
        return
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_commitments
                SET notified_at = NOW()
                WHERE id = ANY(%s)
                """,
                (ids,),
            )
        conn.commit()


# --- turn_log / probe_log (evi-usage-validation) ------------------------------
# Retention: services/log_retention.py only prunes files (jsonl), it is not
# table-driven. turn_log (180 days) pruning must be added by a later task.

TURN_REPLY_MAX_CHARS = 2000


def insert_turn(
    *,
    session_id: str,
    channel: str,
    user_text: str,
    reply_text: str | None = None,
    tools: List[Dict[str, Any]] | None = None,
    latency_ms: int | None = None,
    llm_calls: int | None = None,
    error: str | None = None,
    is_test: bool = False,
) -> int:
    """Record one agent turn. `tools` is [{name, ok, reason, ms}]. Returns the id."""
    import json

    if reply_text is not None:
        reply_text = reply_text[:TURN_REPLY_MAX_CHARS]
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO turn_log
                    (session_id, channel, user_text, reply_text, tools,
                     latency_ms, llm_calls, error, is_test)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    session_id,
                    channel,
                    user_text,
                    reply_text,
                    json.dumps(tools or []),
                    latency_ms,
                    llm_calls,
                    error,
                    is_test,
                ),
            )
            turn_id = int(cur.fetchone()[0])
        conn.commit()
    return turn_id


def set_turn_feedback(session_id: str, feedback: str, note: str | None = None) -> int | None:
    """Attach feedback ('bom'|'ruim') to the latest non-command turn of the session.

    Returns the turn id, or None when the session has no such turn.
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE turn_log
                SET feedback = %s, feedback_note = %s
                WHERE id = (
                    SELECT id FROM turn_log
                    WHERE session_id = %s AND user_text NOT LIKE '/%%'
                    ORDER BY ts DESC, id DESC
                    LIMIT 1
                )
                RETURNING id
                """,
                (feedback, note, session_id),
            )
            row = cur.fetchone()
        conn.commit()
    return int(row[0]) if row else None


def list_turns(since, until, include_test: bool = False) -> List[Dict[str, Any]]:
    """Turns with since <= ts < until, oldest first. Test turns excluded by default."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM turn_log
                WHERE ts >= %s AND ts < %s
                  AND (%s OR NOT is_test)
                ORDER BY ts ASC, id ASC
                """,
                (since, until, include_test),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_turn(turn_id: int) -> Dict[str, Any] | None:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM turn_log WHERE id = %s", (turn_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def get_session_turns_around(turn_id: int) -> Dict[str, Dict[str, Any] | None]:
    """Previous and next turn of the same session: {"prev": row|None, "next": row|None}."""
    turn = get_turn(turn_id)
    out: Dict[str, Dict[str, Any] | None] = {"prev": None, "next": None}
    if not turn:
        return out
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM turn_log
                WHERE session_id = %s AND (ts, id) < (%s, %s)
                ORDER BY ts DESC, id DESC LIMIT 1
                """,
                (turn["session_id"], turn["ts"], turn["id"]),
            )
            row = cur.fetchone()
            out["prev"] = dict(row) if row else None
            cur.execute(
                """
                SELECT * FROM turn_log
                WHERE session_id = %s AND (ts, id) > (%s, %s)
                ORDER BY ts ASC, id ASC LIMIT 1
                """,
                (turn["session_id"], turn["ts"], turn["id"]),
            )
            row = cur.fetchone()
            out["next"] = dict(row) if row else None
    return out


def update_turn_signals(turn_id: int, signals: Dict[str, Any]) -> None:
    import json

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE turn_log SET signals = %s::jsonb WHERE id = %s",
                (json.dumps(signals), turn_id),
            )
        conn.commit()


def delete_turns_older_than(days: int) -> int:
    """Retention: delete turn_log rows older than `days`. Returns rows deleted."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM turn_log WHERE ts < now() - make_interval(days => %s)",
                (int(days),),
            )
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)


def insert_probe(day, check_name: str, ok: bool, reason: str | None = None, ms: int | None = None) -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO probe_log (day, check_name, ok, reason, ms)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (day, check_name, ok, reason, ms),
            )
            probe_id = int(cur.fetchone()[0])
        conn.commit()
    return probe_id


def probe_already_notified(day, check_name: str) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM probe_log "
                "WHERE day = %s AND check_name = %s AND notified)",
                (day, check_name),
            )
            return bool(cur.fetchone()[0])


def claim_probe_notification(day, check_name: str) -> bool:
    """Atomically claim the (day, check) warning slot. True only for the first caller."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO probe_notified (day, check_name) VALUES (%s, %s)
                ON CONFLICT DO NOTHING RETURNING 1
                """,
                (day, check_name),
            )
            claimed = cur.fetchone() is not None
        conn.commit()
    return claimed


def release_probe_notification(day, check_name: str) -> None:
    """Give the claim back (send failed) so the next run can retry."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM probe_notified WHERE day = %s AND check_name = %s",
                (day, check_name),
            )
        conn.commit()


def mark_probe_notified(day, check_name: str) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE probe_log SET notified = true WHERE day = %s AND check_name = %s",
                (day, check_name),
            )
        conn.commit()


def list_probes(since, until) -> List[Dict[str, Any]]:
    """Probe rows with since <= day <= until, oldest first."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM probe_log
                WHERE day >= %s AND day <= %s
                ORDER BY ts ASC, id ASC
                """,
                (since, until),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# --- briefing_log (evi-morning-briefing) --------------------------------------
# One row per (day, kind). `day` is the local (EVI_TIMEZONE) date supplied by the
# caller (from now_local()). A failed send (ok=false) is overwritten by a retry.


def claim_briefing(day, kind: str, stale_minutes: int = 10) -> int | None:
    """Atomically claim the (day, kind) send slot before assembling the briefing.

    Inserts an in-progress row (ok=false, sections '{}'). If a row already exists it is
    re-claimed only when it is a failed/abandoned attempt (not ok) older than
    ``stale_minutes``. Returns the row id, or None when someone else holds the claim or
    the briefing was already sent (callers tell the two apart via briefing_sent_today).
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO briefing_log (day, kind, ok, sections)
                VALUES (%s, %s, false, '{}'::jsonb)
                ON CONFLICT (day, kind) DO UPDATE
                SET sent_at = now()
                WHERE NOT briefing_log.ok
                  AND briefing_log.sent_at < now() - make_interval(mins => %s)
                RETURNING id
                """,
                (day, kind, int(stale_minutes)),
            )
            row = cur.fetchone()
        conn.commit()
    return int(row[0]) if row else None


def record_briefing(day, kind: str, ok: bool, sections: Dict[str, Any]) -> int:
    """UPSERT the (day, kind) briefing row; a retry or force resend overwrites
    sections. Never downgrades ok=true to false; sent_at/replied_at are refreshed only
    when the new send is ok (a successful resend). A failed attempt on a not-ok row
    backdates sent_at so the claim is released and an immediate retry is allowed.
    Returns the row id."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO briefing_log (day, kind, ok, sections)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (day, kind) DO UPDATE
                SET ok = briefing_log.ok OR EXCLUDED.ok,
                    sections = EXCLUDED.sections,
                    sent_at = CASE WHEN EXCLUDED.ok THEN now()
                                   WHEN briefing_log.ok THEN briefing_log.sent_at
                                   ELSE now() - interval '1 day' END,
                    replied_at = CASE WHEN EXCLUDED.ok THEN NULL
                                      ELSE briefing_log.replied_at END
                RETURNING id
                """,
                (day, kind, ok, json.dumps(sections or {})),
            )
            row_id = int(cur.fetchone()[0])
        conn.commit()
    return row_id


def briefing_sent_today(day, kind: str) -> bool:
    """True only if a successful (ok=true) briefing exists for (day, kind)."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM briefing_log "
                "WHERE day = %s AND kind = %s AND ok)",
                (day, kind),
            )
            return bool(cur.fetchone()[0])


def get_briefing(day, kind: str) -> Dict[str, Any] | None:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM briefing_log WHERE day = %s AND kind = %s",
                (day, kind),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def mark_briefing_replied_window(hours: int = 3) -> list[str]:
    """Mark every ok briefing sent within the last ``hours`` and not yet replied.

    Returns the kinds marked (empty when none). Window-based, so it also works across
    midnight (an evening briefing answered after 00:00).
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE briefing_log SET replied_at = now()
                WHERE ok AND replied_at IS NULL
                  AND sent_at >= now() - make_interval(hours => %s)
                RETURNING kind
                """,
                (int(hours),),
            )
            kinds = [r[0] for r in cur.fetchall()]
        conn.commit()
    return kinds


def mark_briefing_replied(day, kind: str) -> bool:
    """Set replied_at once (only if NULL, on an ok=true row). True on first mark."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE briefing_log SET replied_at = now()
                WHERE day = %s AND kind = %s AND ok AND replied_at IS NULL
                RETURNING 1
                """,
                (day, kind),
            )
            marked = cur.fetchone() is not None
        conn.commit()
    return marked


# --- reminders (evi-reminders) ------------------------------------------------
# status: pending | firing | sent | done | cancelled | failed. All datetimes are aware.
# due_at holds the series schedule (anchor for recurrence); snooze_until, when set,
# overrides it for ONE delivery: effective fire time = COALESCE(snooze_until, due_at).
# claim_due() is the only way a tick takes ownership of a due row (SKIP LOCKED),
# so two concurrent ticks never fire the same reminder.

_EFFECTIVE = "COALESCE(snooze_until, due_at)"


def create_reminder(text: str, due_at, repeat: str | None, chat_id: str,
                    created_from: str, anchor_day: int | None = None) -> int:
    """anchor_day (monthly only): local day of month of the original due_at, so a
    31st reminder clamped to Feb 28 returns to the 31st in March."""
    if repeat == "monthly" and anchor_day is None:
        from tools.calendar_time import evi_timezone
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            tz = ZoneInfo(evi_timezone())
        except (ZoneInfoNotFoundError, ValueError):
            tz = ZoneInfo("America/Sao_Paulo")
        anchor_day = due_at.astimezone(tz).day
    if repeat != "monthly":
        anchor_day = None
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reminders (text, due_at, repeat, chat_id, created_from, anchor_day) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (text, due_at, repeat, chat_id, created_from, anchor_day),
            )
            rid = cur.fetchone()[0]
        conn.commit()
    return rid


def get_reminder(reminder_id: int) -> Dict[str, Any] | None:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM reminders WHERE id = %s", (reminder_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def list_reminders(chat_id: str | None = None, statuses=("pending",),
                   limit: int = 50) -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM reminders WHERE status = ANY(%s) "
                "AND (%s::text IS NULL OR chat_id = %s) "
                f"ORDER BY {_EFFECTIVE}, id LIMIT %s",
                (list(statuses), chat_id, chat_id, limit),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def claim_due(now, limit: int = 20) -> List[Dict[str, Any]]:
    """Atomically move due 'pending' rows (effective time <= now) to 'firing'."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "UPDATE reminders SET status = 'firing', claimed_at = now() "
                "WHERE id IN (SELECT id FROM reminders "
                f"             WHERE status = 'pending' AND {_EFFECTIVE} <= %s "
                f"             ORDER BY {_EFFECTIVE} FOR UPDATE SKIP LOCKED LIMIT %s) "
                "RETURNING *",
                (now, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    return sorted(
        (dict(r) for r in rows),
        key=lambda r: (r["snooze_until"] or r["due_at"], r["id"]),
    )


_FIRE_LOG_SQL = (
    "INSERT INTO reminder_fires (reminder_id, due_at, fired_at, drift_s) "
    f"SELECT id, {_EFFECTIVE}, %s, %s FROM reminders WHERE id = %s"
)


def log_reminder_fire(reminder_id: int, fired_at, drift_s: int) -> None:
    """Per-occurrence fire log (a recurring row is overwritten on every fire).

    The scheduled time is read from the row, so call before it advances. finish_fired()
    does this in its own transaction; this is for callers that need it standalone.
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_FIRE_LOG_SQL, (fired_at, drift_s, reminder_id))
        conn.commit()


def finish_fired(reminder_id: int, fired_at, drift_s: int, next_due_at=None) -> bool:
    """Record a delivered occurrence: one-off -> 'sent'; recurring -> 'pending' at next_due_at.

    Only acts on a 'firing' row (False otherwise, nothing logged). Also appends the
    occurrence to reminder_fires (same transaction, before due_at moves) and clears
    snooze_until.
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM reminders WHERE id = %s AND status = 'firing' FOR UPDATE",
                (reminder_id,),
            )
            if cur.fetchone() is None:
                conn.rollback()
                return False
            cur.execute(_FIRE_LOG_SQL, (fired_at, drift_s, reminder_id))
            if next_due_at is None:
                cur.execute(
                    "UPDATE reminders SET status = 'sent', snooze_until = NULL, "
                    "fired_at = %s, drift_s = %s WHERE id = %s AND status = 'firing'",
                    (fired_at, drift_s, reminder_id),
                )
            else:
                cur.execute(
                    "UPDATE reminders SET status = 'pending', due_at = %s, snooze_until = NULL, "
                    "fired_at = %s, drift_s = %s WHERE id = %s AND status = 'firing'",
                    (next_due_at, fired_at, drift_s, reminder_id),
                )
        conn.commit()
    return True


def release_reminder(reminder_id: int) -> None:
    """Failed send: give a 'firing' row back to the next tick."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reminders SET status = 'pending' "
                "WHERE id = %s AND status = 'firing'",
                (reminder_id,),
            )
        conn.commit()


def fail_reminder(reminder_id: int) -> None:
    """Undeliverable for good (e.g. Telegram not configured): 'firing' -> 'failed'."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reminders SET status = 'failed' "
                "WHERE id = %s AND status = 'firing'",
                (reminder_id,),
            )
        conn.commit()


def requeue_stuck(older_than_minutes: int = 5) -> int:
    """'firing' rows whose claim is older than the threshold (crashed tick) -> 'pending'."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reminders SET status = 'pending' WHERE status = 'firing' "
                "AND claimed_at < now() - make_interval(mins => %s)",
                (older_than_minutes,),
            )
            n = cur.rowcount
        conn.commit()
    return n


def _transition(reminder_id: int, new_status: str, from_statuses, chat_id=None) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reminders SET status = %s WHERE id = %s AND status = ANY(%s) "
                "AND (%s::text IS NULL OR chat_id = %s)",
                (new_status, reminder_id, list(from_statuses), chat_id, chat_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def snooze_reminder(reminder_id: int, until, chat_id: str | None = None) -> bool:
    """Re-deliver ONE occurrence at ``until`` without touching the series schedule.

    Sets snooze_until only (due_at keeps the series anchor); a delivered one-off goes
    back from 'sent' to 'pending'. chat_id=None means no ownership filter.
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reminders SET status = 'pending', snooze_until = %s "
                "WHERE id = %s AND status IN ('sent', 'pending') "
                "AND (%s::text IS NULL OR chat_id = %s)",
                (until, reminder_id, chat_id, chat_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def complete_reminder(reminder_id: int, chat_id: str | None = None) -> Dict[str, Any] | None:
    """'feito'. One-off -> 'done'. Recurring: only acknowledges this occurrence (status
    and series untouched; a pending snooze for it is dropped). Returns None when there
    is nothing to complete, else {"recurring": bool, "next_due_at": effective next fire
    (recurring only)}. Stopping a series is cancel_reminder's job."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "UPDATE reminders SET status = 'done', snooze_until = NULL "
                "WHERE id = %s AND repeat IS NULL "
                "AND status IN ('pending', 'firing', 'sent') "
                "AND (%s::text IS NULL OR chat_id = %s) RETURNING id",
                (reminder_id, chat_id, chat_id),
            )
            if cur.fetchone():
                conn.commit()
                return {"recurring": False, "next_due_at": None}
            cur.execute(
                "UPDATE reminders SET snooze_until = CASE WHEN status = 'pending' "
                "AND due_at > now() THEN NULL ELSE snooze_until END "
                "WHERE id = %s AND repeat IS NOT NULL "
                "AND status IN ('pending', 'firing', 'sent') "
                "AND (%s::text IS NULL OR chat_id = %s) RETURNING due_at, snooze_until",
                (reminder_id, chat_id, chat_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return {"recurring": True, "next_due_at": row["snooze_until"] or row["due_at"]}


def cancel_reminder(reminder_id: int, chat_id: str | None = None) -> bool:
    return _transition(reminder_id, "cancelled", ("pending", "sent"), chat_id)


def reminder_stats(since, until) -> Dict[str, Any]:
    """Weekly-report numbers: created, fired, late (drift_s > 300), p95 drift, raw drifts."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM reminders WHERE created_at >= %s AND created_at < %s",
                (since, until),
            )
            created = cur.fetchone()[0]
            cur.execute(
                "SELECT drift_s FROM reminder_fires WHERE fired_at >= %s AND fired_at < %s "
                "ORDER BY drift_s",
                (since, until),
            )
            drifts = [r[0] for r in cur.fetchall()]
    p95 = drifts[min(len(drifts) - 1, int(0.95 * len(drifts)))] if drifts else None
    return {
        "created": created,
        "fired": len(drifts),
        "late": sum(1 for d in drifts if d > 300),
        "p95_drift_s": p95,
        "drifts": drifts,
    }


# Removed with the dev bridge (2026-08-12): create_dev_job, get_dev_job,
# update_dev_job, list_dev_jobs, get_dev_bridge_setting, set_dev_bridge_setting.
# Existing databases keep empty `dev_jobs` and `dev_bridge_state` tables — a
# DROP in _run_migrations() would run on every startup of every install, and
# tidiness is not worth a destructive automatic statement. Drop by hand if you
# want them gone:  DROP TABLE IF EXISTS dev_jobs, dev_bridge_state;
