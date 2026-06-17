"""Postgres session persistence (MVP)."""

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
                CREATE TABLE IF NOT EXISTS dev_jobs (
                    job_id VARCHAR(16) PRIMARY KEY,
                    description TEXT NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    requested_by VARCHAR(128) DEFAULT '',
                    result_summary TEXT,
                    log_path TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_dev_jobs_status
                    ON dev_jobs(status, created_at DESC);
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


def create_dev_job(job_id: str, description: str, *, requested_by: str = "") -> None:
    init_db()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dev_jobs (job_id, description, requested_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (job_id) DO NOTHING
                """,
                (job_id, description, requested_by),
            )
        conn.commit()


def get_dev_job(job_id: str) -> Dict[str, Any] | None:
    init_db()
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM dev_jobs WHERE job_id = %s", (job_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def update_dev_job(
    job_id: str,
    *,
    status: str,
    result_summary: str = "",
    log_path: str = "",
) -> None:
    init_db()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dev_jobs
                SET status = %s,
                    result_summary = COALESCE(NULLIF(%s, ''), result_summary),
                    log_path = COALESCE(NULLIF(%s, ''), log_path),
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (status, result_summary, log_path, job_id),
            )
        conn.commit()


def list_dev_jobs(*, limit: int = 10) -> List[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT job_id, description, status, requested_by, created_at
                FROM dev_jobs
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]
