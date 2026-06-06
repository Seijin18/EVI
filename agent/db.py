"""Postgres session persistence (MVP)."""

import os
from contextlib import contextmanager
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://evi:evi@postgres:5432/evidb",
)


def init_db() -> None:
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
                """
            )
        conn.commit()


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


def list_pending_commitments(limit: int = 50) -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, source, source_id, type, title,
                       event_date::text, event_time, due_date::text,
                       priority, status, raw_text, source_chat, source_label,
                       confirmed_at, confirmed_via, created_at
                FROM pending_commitments
                WHERE status = 'pending'
                ORDER BY
                    CASE priority
                        WHEN 'urgent' THEN 0
                        WHEN 'work' THEN 1
                        WHEN 'university' THEN 2
                        ELSE 3
                    END,
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
