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
        backfill_name_source()
        _db_initialized = True


def backfill_name_source() -> int:
    """Mark names that predate ``name_source`` (idempotent; returns rows touched).

    The two historical writers (``set_whatsapp_contact_name`` and the vCard import)
    left the same trace: ``display_name`` plus the old pushName as an alias, so they
    are NOT distinguishable in stored data. Conservative choice: every existing
    ``display_name`` becomes ``user`` and is never overwritten by the address-book
    sync. From now on the vCard import / sync write ``vcard`` / ``agenda`` explicitly.
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE whatsapp_contacts SET name_source = 'user' "
                "WHERE name_source IS NULL AND COALESCE(TRIM(display_name), '') <> ''"
            )
            n = cur.rowcount
        conn.commit()
    return n


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
                ALTER TABLE pending_commitments
                    ADD COLUMN IF NOT EXISTS next_eval_at TIMESTAMPTZ;
                ALTER TABLE pending_commitments
                    ADD COLUMN IF NOT EXISTS eval_attempts INT NOT NULL DEFAULT 0;
                ALTER TABLE pending_commitments
                    ADD COLUMN IF NOT EXISTS msg_ts TIMESTAMPTZ;
                ALTER TABLE pending_commitments
                    ADD COLUMN IF NOT EXISTS last_swept_at TIMESTAMPTZ;
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
                ALTER TABLE whatsapp_contacts
                    ADD COLUMN IF NOT EXISTS name_source text;
                ALTER TABLE whatsapp_contacts
                    ADD COLUMN IF NOT EXISTS name_prompt_ignored_until timestamptz;
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
                ALTER TABLE turn_log ADD COLUMN IF NOT EXISTS tokens_in INTEGER;
                ALTER TABLE turn_log ADD COLUMN IF NOT EXISTS tokens_out INTEGER;
                ALTER TABLE turn_log ADD COLUMN IF NOT EXISTS input_kind VARCHAR(8) NOT NULL DEFAULT 'text';
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
                CREATE TABLE IF NOT EXISTS source_status (
                    source TEXT PRIMARY KEY,
                    ok BOOLEAN NOT NULL,
                    reason TEXT,
                    down_since TIMESTAMPTZ,
                    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
                ALTER TABLE briefing_log ADD COLUMN IF NOT EXISTS feedback TEXT;
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
                CREATE TABLE IF NOT EXISTS wa_conversation_state (
                    jid VARCHAR(128) PRIMARY KEY,
                    last_in_at TIMESTAMPTZ,
                    last_in_preview TEXT,
                    last_in_id VARCHAR(128),
                    last_out_at TIMESTAMPTZ,
                    acknowledged_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS wa_jid_alias (
                    lid TEXT PRIMARY KEY,
                    phone_jid TEXT NOT NULL,
                    seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
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
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
    except psycopg2.OperationalError:
        # One retry: a connect that stalls right after Postgres/Docker is busy (cold stack,
        # sim container swap) must not turn into a swallowed soft-fail that drops a write.
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
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
    status: str = "pending",
    next_eval_at: Any = None,
    msg_ts: Any = None,
) -> int | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pending_commitments (
                    source, source_id, type, title,
                    event_date, event_time, due_date,
                    priority, raw_text, source_chat, source_label, status,
                    next_eval_at, msg_ts
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    status,
                    next_eval_at,
                    msg_ts,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return row[0] if row else None


# --- promise evaluation queue (evi-promise-context): the row is the queue --------
# status='needs_eval' rows are invisible to every listing (they filter on 'pending').

def list_promises_to_evaluate(now: Any, limit: int = 10) -> List[Dict[str, Any]]:
    """needs_eval promises whose next_eval_at is due (oldest first)."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, source_id, title, due_date::text, raw_text, source_chat,
                       msg_ts, next_eval_at, eval_attempts, created_at
                FROM pending_commitments
                WHERE status = 'needs_eval' AND next_eval_at <= %s
                ORDER BY next_eval_at ASC, id ASC
                LIMIT %s
                """,
                (now, limit),
            )
            return [dict(r) for r in cur.fetchall()]


def list_stale_needs_eval(cutoff: Any, limit: int = 100) -> List[Dict[str, Any]]:
    """needs_eval promises whose message is older than `cutoff` (48 h fallback)."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, title, due_date::text, msg_ts, created_at
                FROM pending_commitments
                WHERE status = 'needs_eval' AND COALESCE(msg_ts, created_at) < %s
                ORDER BY id ASC
                LIMIT %s
                """,
                (cutoff, limit),
            )
            return [dict(r) for r in cur.fetchall()]


def finish_promise_evaluation(
    commitment_id: int,
    new_status: str,
    title: str | None = None,
    due_date: str | None = None,
    *,
    clear_due: bool = False,
    confirmed_via: str | None = None,
) -> bool:
    """Leave needs_eval: set the final status (+ title/due when given). Only from needs_eval.

    clear_due NULLs due_date (a past due would hide the row from listings);
    confirmed_via marks automatic outcomes (e.g. 'auto-eval' for LLM rejections).
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_commitments
                SET status = %s,
                    title = COALESCE(%s, title),
                    due_date = CASE WHEN %s THEN NULL ELSE COALESCE(%s, due_date) END,
                    confirmed_via = COALESCE(%s, confirmed_via),
                    next_eval_at = NULL
                WHERE id = %s AND status = 'needs_eval'
                """,
                (new_status, title or None, clear_due, due_date or None, confirmed_via, commitment_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def release_needs_eval(today: str | None = None) -> int:
    """Release every needs_eval row to 'pending' (promise context turned off).

    A due_date before `today` (YYYY-MM-DD) is cleared so the row is not hidden.
    Returns the number of rows released.
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_commitments
                SET status = 'pending', next_eval_at = NULL,
                    due_date = CASE WHEN due_date < COALESCE(%s::date, CURRENT_DATE)
                                    THEN NULL ELSE due_date END
                WHERE status = 'needs_eval'
                """,
                (today,),
            )
            n = cur.rowcount
        conn.commit()
    return n


def bump_promise_eval(commitment_id: int, next_eval_at: Any) -> bool:
    """Reschedule a failed evaluation: next_eval_at set, eval_attempts + 1."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_commitments
                SET next_eval_at = %s, eval_attempts = eval_attempts + 1
                WHERE id = %s AND status = 'needs_eval'
                """,
                (next_eval_at, commitment_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def list_promises_to_sweep(now: Any, limit: int = 50, *, max_age_days: int = 14,
                           min_gap_hours: int = 20) -> List[Dict[str, Any]]:
    """Pending whatsapp promises (≤ max_age_days old) not swept within min_gap_hours."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, source_id, title, due_date::text, raw_text, source_chat,
                       msg_ts, created_at, last_swept_at
                FROM pending_commitments
                WHERE status = 'pending' AND type = 'promise' AND source = 'whatsapp_from_me'
                  AND source_chat IS NOT NULL AND source_chat <> ''
                  AND created_at >= %s::timestamptz - make_interval(days => %s)
                  AND (last_swept_at IS NULL
                       OR last_swept_at < %s::timestamptz - make_interval(hours => %s))
                ORDER BY id ASC
                LIMIT %s
                """,
                (now, max_age_days, now, min_gap_hours, limit),
            )
            return [dict(r) for r in cur.fetchall()]


def mark_promise_swept(commitment_id: int, ts: Any) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pending_commitments SET last_swept_at = %s WHERE id = %s",
                (ts, commitment_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def mark_promise_done_by_sweep(commitment_id: int) -> bool:
    """Fulfilment found by the daily sweep: pending → done (guarded)."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_commitments
                SET status = 'done', confirmed_via = 'auto-sweep'
                WHERE id = %s AND status = 'pending'
                """,
                (commitment_id,),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def list_pending_promises(limit: int = 500) -> List[Dict[str, Any]]:
    """Every pending type='promise' row (any source), oldest first (re-evaluation)."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, source_id, title, due_date::text, raw_text, source_chat,
                       msg_ts, created_at
                FROM pending_commitments
                WHERE status = 'pending' AND type = 'promise'
                ORDER BY id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]


def update_pending_promise(commitment_id: int, title: str | None, due_date: str | None,
                           clear_due: bool = False) -> bool:
    """Retitle / redate a still-pending promise (guarded by status='pending')."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_commitments
                SET title = COALESCE(%s, title),
                    due_date = CASE WHEN %s THEN NULL ELSE COALESCE(%s, due_date) END
                WHERE id = %s AND status = 'pending' AND type = 'promise'
                """,
                (title or None, clear_due, due_date or None, commitment_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def finish_pending_promise(commitment_id: int, new_status: str, confirmed_via: str) -> bool:
    """Re-evaluation outcome for a pending promise (dismissed/done), guarded by 'pending'."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_commitments
                SET status = %s, confirmed_via = %s
                WHERE id = %s AND status = 'pending' AND type = 'promise'
                """,
                (new_status, confirmed_via, commitment_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


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
                """,  # noqa: S608 — past_filter is one of two literal fragments, never user input; limit is bound
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
    name_source: str | None = None,
    only_if_name_source_in: tuple | None = None,
) -> bool:
    """Insert or update a WhatsApp contact row; False when a guard skipped the write.

    ``name_source`` (user | agenda | vcard) records who set ``display_name``; a
    display_name written without one counts as the user's. ``only_if_name_source_in``
    (e.g. ``(None, 'agenda', 'vcard')``) is checked under the row lock: when the stored
    source is not in it nothing is written, so a name the user sets in chat between a
    snapshot and this write is never overwritten.
    """
    if not jid:
        return True
    import json

    with _conn() as conn:
        with conn.cursor() as cur:
            # Atomic against concurrent writers (webhook vs tick loops): a bare
            # SELECT-then-INSERT lost the pushName label on a duplicate-key race, and
            # SELECT-then-UPDATE overwrote it with a stale NULL.
            cur.execute(
                "INSERT INTO whatsapp_contacts (jid, aliases) VALUES (%s, '[]'::jsonb) "
                "ON CONFLICT (jid) DO NOTHING",
                (jid,),
            )
            cur.execute(
                "SELECT whatsapp_label, display_name, aliases, phone, notes, name_source "
                "FROM whatsapp_contacts WHERE jid = %s FOR UPDATE",
                (jid,),
            )
            row = cur.fetchone()
            if row:
                wl, dn, existing_aliases, ph, nt, ns = row
                if only_if_name_source_in is not None and (ns or None) not in only_if_name_source_in:
                    conn.commit()
                    return False
                merged_ns = ns
                if display_name is not None:
                    merged_ns = name_source or "user"
                elif name_source is not None:
                    merged_ns = name_source
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
                        name_source = %s,
                        updated_at = NOW()
                    WHERE jid = %s
                    """,
                    (
                        merged_wl,
                        merged_dn,
                        json.dumps(alias_list),
                        merged_ph,
                        merged_nt,
                        merged_ns,
                        jid,
                    ),
                )
            else:
                alias_list = [a.strip() for a in (aliases or []) if (a or "").strip()]
                cur.execute(
                    """
                    INSERT INTO whatsapp_contacts (
                        jid, whatsapp_label, display_name, aliases, phone, notes,
                        name_source
                    ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                    """,
                    (
                        jid,
                        whatsapp_label,
                        display_name,
                        json.dumps(alias_list),
                        phone,
                        notes,
                        (name_source or "user") if display_name is not None else name_source,
                    ),
                )
        conn.commit()
    return True


def get_whatsapp_contact(jid: str) -> Dict[str, Any] | None:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT jid, whatsapp_label, display_name, aliases, phone, notes,
                       name_source, created_at, updated_at
                FROM whatsapp_contacts
                WHERE jid = %s
                """,
                (jid,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def set_name_prompt_ignored(jid: str, until: Any) -> None:
    """Stop the weekly "conversas sem nome" question for ``jid`` until ``until``."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO whatsapp_contacts (jid, aliases, name_prompt_ignored_until) "
                "VALUES (%s, '[]'::jsonb, %s) "
                "ON CONFLICT (jid) DO UPDATE SET name_prompt_ignored_until = EXCLUDED.name_prompt_ignored_until",
                (jid, until),
            )
        conn.commit()


def list_whatsapp_contacts_db(limit: int = 500) -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT jid, whatsapp_label, display_name, aliases, phone, notes,
                       name_source, name_prompt_ignored_until, created_at, updated_at
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
                  AND status <> 'needs_eval'
                  AND confirmed_via IS DISTINCT FROM 'auto-eval'
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
                  AND status <> 'needs_eval'
                  AND confirmed_via IS DISTINCT FROM 'auto-eval'
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
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    input_kind: str = "text",
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
                     latency_ms, llm_calls, error, is_test, tokens_in, tokens_out,
                     input_kind)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
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
                    tokens_in,
                    tokens_out,
                    input_kind or "text",
                ),
            )
            turn_id = int(cur.fetchone()[0])
        conn.commit()
    return turn_id


def capabilities_used_since(since) -> set[str]:
    """Markers of what the user's real (non-test) turns used since ``since``: the names of
    the tools that ran (not failed) and ``input_kind:<kind>`` (voice, button, ...)."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT t->>'name'
                FROM turn_log,
                     jsonb_array_elements(
                         CASE WHEN jsonb_typeof(tools) = 'array' THEN tools ELSE '[]'::jsonb END
                     ) AS t
                WHERE ts >= %s AND NOT is_test
                  AND jsonb_typeof(t) = 'object'
                  AND COALESCE(t->>'ok', 'true') <> 'false'
                UNION
                SELECT DISTINCT 'input_kind:' || input_kind
                FROM turn_log
                WHERE ts >= %s AND NOT is_test
                """,
                (since, since),
            )
            rows = cur.fetchall()
    return {r[0] for r in rows if r[0]}


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


def record_source(source: str, ok: bool, reason: str | None = None, now=None) -> None:
    """Upsert the current state of a source. down_since is set on the first failure
    (or an ok -> fail transition), kept while it stays down, cleared on ok."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_status (source, ok, reason, down_since, checked_at)
                VALUES (%(s)s, %(ok)s, %(r)s,
                        CASE WHEN %(ok)s THEN NULL ELSE COALESCE(%(now)s, now()) END,
                        COALESCE(%(now)s, now()))
                ON CONFLICT (source) DO UPDATE SET
                    ok = EXCLUDED.ok,
                    reason = EXCLUDED.reason,
                    down_since = CASE
                        WHEN EXCLUDED.ok THEN NULL
                        WHEN source_status.ok OR source_status.down_since IS NULL
                            THEN EXCLUDED.down_since
                        ELSE source_status.down_since END,
                    checked_at = EXCLUDED.checked_at
                """,
                {"s": source, "ok": ok, "r": reason, "now": now},
            )
        conn.commit()


def list_sources_down() -> List[Dict[str, Any]]:
    """Sources whose last check failed, oldest outage first."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT source, ok, reason, down_since, checked_at FROM source_status "
                "WHERE NOT ok ORDER BY down_since, source"
            )
            return [dict(r) for r in cur.fetchall()]


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


def set_briefing_feedback(day, kind: str, value: str) -> bool:
    """Store the user's 👍/👎 (``up`` | ``down``) for the (day, kind) briefing; the last
    tap wins. False when there is no such row or the value is not allowed."""
    if value not in ("up", "down"):
        return False
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE briefing_log SET feedback = %s WHERE day = %s AND kind = %s RETURNING 1",
                (value, day, kind),
            )
            found = cur.fetchone() is not None
        conn.commit()
    return found


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
                "SELECT * FROM reminders WHERE status = ANY(%s) "  # noqa: S608 — interpolated _EFFECTIVE is a module-level constant; values are bound via %s
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
                "UPDATE reminders SET status = 'firing', claimed_at = now() "  # noqa: S608 — interpolated _EFFECTIVE is a module-level constant; values are bound via %s
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
    "INSERT INTO reminder_fires (reminder_id, due_at, fired_at, drift_s) "  # noqa: S608 — interpolated _EFFECTIVE is a module-level constant; values are bound via %s
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


# --- wa_conversation_state (evi-reply-debts) ---------------------------------
# One row per direct WhatsApp conversation. Timestamps only move forward, so a
# webhook redelivery or out-of-order message never regresses the state.

_PREVIEW_MAX = 160


def record_inbound(jid: str, ts, preview: str, msg_id: str) -> None:
    preview = (preview or "")[:_PREVIEW_MAX]
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO wa_conversation_state "
                "(jid, last_in_at, last_in_preview, last_in_id) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (jid) DO UPDATE SET "
                "last_in_at = EXCLUDED.last_in_at, "
                "last_in_preview = EXCLUDED.last_in_preview, "
                "last_in_id = EXCLUDED.last_in_id, updated_at = now() "
                "WHERE wa_conversation_state.last_in_at IS NULL "
                "OR EXCLUDED.last_in_at > wa_conversation_state.last_in_at",
                (jid, ts, preview, msg_id),
            )
        conn.commit()


def record_outbound(jid: str, ts) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO wa_conversation_state (jid, last_out_at) VALUES (%s, %s) "
                "ON CONFLICT (jid) DO UPDATE SET "
                "last_out_at = GREATEST(wa_conversation_state.last_out_at, EXCLUDED.last_out_at), "
                "updated_at = now()",
                (jid, ts),
            )
        conn.commit()


def acknowledge(jid: str, ts) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO wa_conversation_state (jid, acknowledged_at) VALUES (%s, %s) "
                "ON CONFLICT (jid) DO UPDATE SET "
                "acknowledged_at = GREATEST(wa_conversation_state.acknowledged_at, EXCLUDED.acknowledged_at), "
                "updated_at = now()",
                (jid, ts),
            )
        conn.commit()


def get_state(jid: str) -> Dict[str, Any] | None:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM wa_conversation_state WHERE jid = %s", (jid,))
            row = cur.fetchone()
    return dict(row) if row else None


def list_states() -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM wa_conversation_state ORDER BY updated_at DESC")
            return [dict(r) for r in cur.fetchall()]


def merge_conversation_state(src_jid: str, dst_jid: str) -> bool:
    """Fold the ``src_jid`` row into ``dst_jid`` (later timestamps win) and drop src.

    One transaction: src is locked (FOR UPDATE), the upsert into dst takes dst's row
    lock and computes GREATEST in SQL, so a concurrent record_inbound/outbound is
    never overwritten. Preview/id follow the later ``last_in_at``. Returns False when
    there was no src row.
    """
    if src_jid == dst_jid:
        return False
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_in_at, last_in_preview, last_in_id, last_out_at, acknowledged_at "
                "FROM wa_conversation_state WHERE jid = %s FOR UPDATE",
                (src_jid,),
            )
            src = cur.fetchone()
            if not src:
                return False
            t = "wa_conversation_state"
            cur.execute(
                f"INSERT INTO {t} "  # noqa: S608 — `t` is the module-local constant table name; values are bound params
                "(jid, last_in_at, last_in_preview, last_in_id, last_out_at, acknowledged_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (jid) DO UPDATE SET "
                f"last_in_preview = CASE WHEN EXCLUDED.last_in_at IS NOT NULL AND "
                f"({t}.last_in_at IS NULL OR EXCLUDED.last_in_at > {t}.last_in_at) "
                f"THEN EXCLUDED.last_in_preview ELSE {t}.last_in_preview END, "
                f"last_in_id = CASE WHEN EXCLUDED.last_in_at IS NOT NULL AND "
                f"({t}.last_in_at IS NULL OR EXCLUDED.last_in_at > {t}.last_in_at) "
                f"THEN EXCLUDED.last_in_id ELSE {t}.last_in_id END, "
                f"last_in_at = GREATEST({t}.last_in_at, EXCLUDED.last_in_at), "
                f"last_out_at = GREATEST({t}.last_out_at, EXCLUDED.last_out_at), "
                f"acknowledged_at = GREATEST({t}.acknowledged_at, EXCLUDED.acknowledged_at), "
                "updated_at = now()",
                (dst_jid, *src),
            )
            cur.execute("DELETE FROM wa_conversation_state WHERE jid = %s", (src_jid,))
        conn.commit()
    return True


def list_debt_candidates(now, min_age, max_age, limit: int = 200) -> List[Dict[str, Any]]:
    """Conversations whose last inbound is unanswered and unacknowledged, aged
    between ``min_age`` and ``max_age`` (timedeltas) relative to ``now``.
    Oldest first. The closing-message filter is applied by the caller."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT jid, last_in_at, last_in_preview FROM wa_conversation_state "
                "WHERE last_in_at IS NOT NULL "
                "AND last_in_at > COALESCE(last_out_at, '-infinity') "
                "AND last_in_at > COALESCE(acknowledged_at, '-infinity') "
                "AND last_in_at <= %s AND last_in_at >= %s "
                "ORDER BY last_in_at ASC LIMIT %s",
                (now - min_age, now - max_age, limit),
            )
            return [dict(r) for r in cur.fetchall()]


def action_rates_by_type(since, until, debt_hours: float) -> Dict[str, Dict[str, int]]:
    """Counts only (no text): shown / acted per item type for the weekly report.

    reply_debt: conversations whose last inbound fell in [since, until) and was
    still unanswered ``debt_hours`` later (so it became a debt); acted = answered
    (last_out_at > last_in_at) or acknowledged since. Uses CURRENT state, so a
    conversation that got a newer inbound later drops out of the older week.
    promise: type='promise' created in the week; acted = done/dismissed/scheduled.
    dated: other types, not 'undated', not evi-test; acted = scheduled/confirmed.
    """
    out: Dict[str, Dict[str, int]] = {}
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE "
                "last_out_at > last_in_at OR acknowledged_at >= last_in_at) "
                "FROM wa_conversation_state "
                "WHERE last_in_at >= %s AND last_in_at < %s "
                "AND last_in_at + make_interval(secs => %s) <= LEAST(%s, now()) "
                "AND (last_out_at IS NULL OR last_out_at <= last_in_at "
                "OR last_out_at > last_in_at + make_interval(secs => %s))",
                (since, until, debt_hours * 3600, until, debt_hours * 3600),
            )
            shown, acted = cur.fetchone()
            out["reply_debt"] = {"shown": int(shown), "acted": int(acted)}
            cur.execute(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE status IN ('done','dismissed','scheduled')) "
                "FROM pending_commitments WHERE type = 'promise' AND source <> 'evi-test' "
                "AND status <> 'needs_eval' AND confirmed_via IS DISTINCT FROM 'auto-eval' "
                "AND created_at >= %s AND created_at < %s",
                (since, until),
            )
            shown, acted = cur.fetchone()
            out["promise"] = {"shown": int(shown), "acted": int(acted)}
            cur.execute(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'scheduled') "
                "FROM pending_commitments WHERE type <> 'promise' AND status <> 'undated' "
                "AND source <> 'evi-test' AND created_at >= %s AND created_at < %s",
                (since, until),
            )
            shown, acted = cur.fetchone()
            out["dated"] = {"shown": int(shown), "acted": int(acted)}
    return out


# --- wa_jid_alias (evi-contact-knowledge §9) ---------------------------------
# WhatsApp delivers one person as ``…@lid`` and ``…@s.whatsapp.net``; the pair
# comes from key.remoteJidAlt. contact_identity.canonical_jid reads it.


def upsert_jid_alias(lid: str, phone_jid: str) -> None:
    """Last writer wins (Evolution is authoritative); a changed phone is logged."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT phone_jid FROM wa_jid_alias WHERE lid = %s", (lid,))
            prev = cur.fetchone()
            cur.execute(
                "INSERT INTO wa_jid_alias (lid, phone_jid) VALUES (%s, %s) "
                "ON CONFLICT (lid) DO UPDATE SET phone_jid = EXCLUDED.phone_jid, seen_at = now()",
                (lid, phone_jid),
            )
        conn.commit()
    if prev and prev[0] != phone_jid:
        from services.soft_fail import soft_fail

        tail = lambda j: "…" + j.split("@", 1)[0][-4:]  # noqa: E731 (no PII beyond 4 digits)
        soft_fail(
            "db.upsert_jid_alias",
            RuntimeError(f"alias {tail(lid)} remapped {tail(prev[0])} -> {tail(phone_jid)}"),
        )


def get_jid_alias(lid: str) -> str | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT phone_jid FROM wa_jid_alias WHERE lid = %s", (lid,))
            row = cur.fetchone()
    return row[0] if row else None


def list_jid_aliases() -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT lid, phone_jid, seen_at FROM wa_jid_alias ORDER BY seen_at DESC")
            return [dict(r) for r in cur.fetchall()]
