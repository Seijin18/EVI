"""Guard for DB-mutating tests.

Tests marked `@pytest.mark.ephemeral_db` insert/update/delete rows (and some run the
signals/prune jobs). They run only against a throwaway Postgres: set both
DATABASE_URL and EVI_TEST_EPHEMERAL_DB=1 (CI does). A developer whose DATABASE_URL
points at the dev database never has them touch it. Rows inserted through
db.insert_turn / db.insert_probe during such a test are deleted afterwards.
"""

import os

import pytest


def _enabled() -> bool:
    return bool(os.getenv("DATABASE_URL")) and os.getenv("EVI_TEST_EPHEMERAL_DB") == "1"


def pytest_collection_modifyitems(config, items):
    if _enabled():
        return
    skip = pytest.mark.skip(
        reason="DB-mutating test: needs DATABASE_URL and EVI_TEST_EPHEMERAL_DB=1 (ephemeral Postgres only)"
    )
    for item in items:
        if "ephemeral_db" in item.keywords:
            item.add_marker(skip)


_SERIAL_TABLES = (
    "messages",
    "pending_commitments",
    "session_tool_snapshots",
    "turn_log",
    "probe_log",
    "briefing_log",
    "reminders",
    "reminder_fires",
)
_KEYED_TABLES = (  # (table, key columns)
    ("whatsapp_contacts", ("jid",)),
    ("wa_conversation_state", ("jid",)),
    ("probe_notified", ("day", "check_name")),
)


def _snapshot(cur) -> dict:
    snap: dict = {}
    for t in _SERIAL_TABLES:
        cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {t}")
        snap[t] = cur.fetchone()[0]
    for t, cols in _KEYED_TABLES:
        cur.execute(f"SELECT {', '.join(cols)} FROM {t}")
        snap[t] = {tuple(r) for r in cur.fetchall()}
    return snap


def _delete_new_rows(cur, before: dict) -> None:
    """Delete exactly the rows that appeared during the test: serial ids above the
    pre-test max, and keys that were not present before. Never a pattern match."""
    cur.execute("SELECT id FROM reminders WHERE id > %s", (before["reminders"],))
    new_reminders = [r[0] for r in cur.fetchall()]
    cur.execute(
        "DELETE FROM reminder_fires WHERE id > %s OR reminder_id = ANY(%s)",
        (before["reminder_fires"], new_reminders),
    )
    for t in _SERIAL_TABLES:
        if t != "reminder_fires":
            cur.execute(f"DELETE FROM {t} WHERE id > %s", (before[t],))
    for t, cols in _KEYED_TABLES:
        cur.execute(f"SELECT {', '.join(cols)} FROM {t}")
        for key in {tuple(r) for r in cur.fetchall()} - before[t]:
            cur.execute(
                f"DELETE FROM {t} WHERE " + " AND ".join(f"{c} = %s" for c in cols), key
            )


@pytest.fixture(autouse=True)
def _cleanup_inserted_rows(request):
    """Ephemeral mode: every test (marked or not) leaves the tables as it found them,
    removing only the rows it created, identified by id/key. Otherwise, with a
    DATABASE_URL set but no EVI_TEST_EPHEMERAL_DB, an unmarked test may not touch the
    database at all (its `db._conn` raises) so it can never write to a dev database."""
    if not os.getenv("DATABASE_URL"):
        yield
        return
    import db

    if not _enabled():
        if "ephemeral_db" in request.keywords:
            yield  # skipped before reaching here; defensive
            return
        real_conn = db._conn

        def _blocked(*a, **k):
            raise RuntimeError(
                "test touched Postgres without @pytest.mark.ephemeral_db "
                "(needs EVI_TEST_EPHEMERAL_DB=1)"
            )

        db._conn = _blocked
        try:
            yield
        finally:
            db._conn = real_conn
        return

    before = None
    try:
        db.init_db()
        with db._conn() as conn:
            with conn.cursor() as cur:
                before = _snapshot(cur)
    except Exception:
        before = None
    try:
        yield
    finally:
        if before is not None:
            try:
                with db._conn() as conn:
                    with conn.cursor() as cur:
                        _delete_new_rows(cur, before)
                    conn.commit()
            except Exception:
                pass


@pytest.fixture(autouse=True)
def _isolate_payload_shapes(request, tmp_path, monkeypatch):
    """Webhook tests would otherwise write redacted shapes into the real data/payload_shapes
    and share the in-memory signature cache across tests (order-dependent captures)."""
    if request.module.__name__.endswith("test_payload_shapes"):
        yield  # that module owns its own isolation
        return
    from services import payload_shapes as ps

    monkeypatch.setenv("EVI_PAYLOAD_SHAPES_DIR", str(tmp_path / "payload_shapes"))
    ps._known.clear()
    yield
    ps._known.clear()
