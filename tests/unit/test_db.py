"""SCN-DB-01 — Postgres persistence, exercised against a real database.

`agent/db.py` had no tests: the migrations, the ON CONFLICT dedupe and the
status transitions were only ever verified by running the product. These skip
without `DATABASE_URL`, and CI provides an ephemeral Postgres service.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL (ephemeral Postgres)"
)


@pytest.fixture(scope="module", autouse=True)
def _schema():
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    yield


def _uid() -> str:
    return uuid.uuid4().hex[:12]


# --- migrations -------------------------------------------------------------


def test_init_db_is_idempotent():
    """It runs on every startup; a second call must not raise."""
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    db.init_db()


def test_removed_dev_bridge_tables_are_not_recreated():
    """The dev bridge was removed; init_db must not bring its tables back."""
    import db

    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name IN ('dev_jobs','dev_bridge_state') "
                "AND table_schema = current_schema()"
            )
            # Pre-existing installs may still carry them; a fresh CI database
            # must not, which is what this asserts.
            assert cur.fetchone()[0] == 0


# --- messages ---------------------------------------------------------------


def test_messages_round_trip_in_order():
    import db

    sid = f"test-{_uid()}"
    db.save_message(sid, "user", "primeira")
    db.save_message(sid, "assistant", "segunda")
    rows = db.load_recent_messages(sid, limit=10)
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "primeira", "oldest first after the reverse()"


def test_messages_are_scoped_to_the_session():
    import db

    a, b = f"test-{_uid()}", f"test-{_uid()}"
    db.save_message(a, "user", "de A")
    db.save_message(b, "user", "de B")
    assert [r["content"] for r in db.load_recent_messages(a)] == ["de A"]


def test_load_recent_respects_limit():
    import db

    sid = f"test-{_uid()}"
    for i in range(5):
        db.save_message(sid, "user", f"m{i}")
    assert len(db.load_recent_messages(sid, limit=2)) == 2


# --- pending commitments ----------------------------------------------------


def _insert(**kw):
    import db

    params = dict(
        source="test",
        source_id=f"src-{_uid()}",
        ctype="event",
        title="Reunião",
        event_date="2026-09-01",
        priority="normal",
    )
    params.update(kw)
    return db.insert_pending_commitment(**params), params["source_id"]


def test_insert_returns_the_new_id():
    rid, _ = _insert()
    assert isinstance(rid, int) and rid > 0


def test_duplicate_source_id_is_ignored():
    """ON CONFLICT DO NOTHING is what stops a replayed webhook double-queueing."""
    import db

    rid, source_id = _insert()
    again = db.insert_pending_commitment(
        source="test", source_id=source_id, ctype="event", title="Duplicada"
    )
    assert again is None


def test_same_source_id_under_a_different_source_is_allowed():
    import db

    _, source_id = _insert()
    other = db.insert_pending_commitment(
        source="outra-origem", source_id=source_id, ctype="event", title="X"
    )
    assert other is not None


def test_confirm_sets_status_and_audit_columns():
    import db

    rid, _ = _insert()
    assert db.update_commitment_status(rid, "scheduled", confirmed_via="chat") is True
    row = next(r for r in db.list_scheduled_today(limit=200) if r["id"] == rid)
    assert row["status"] == "scheduled"
    assert row["confirmed_via"] == "chat"
    assert row["confirmed_at"] is not None


def test_status_update_only_applies_to_pending():
    """Guards against a double confirm silently rewriting an audited row."""
    import db

    rid, _ = _insert()
    assert db.update_commitment_status(rid, "scheduled", confirmed_via="chat") is True
    assert db.update_commitment_status(rid, "dismissed") is False


def test_past_commitments_are_hidden_by_default():
    import db

    rid, _ = _insert(event_date="2020-01-01")
    ids = [r["id"] for r in db.list_pending_commitments(limit=500)]
    assert rid not in ids
    ids_all = [r["id"] for r in db.list_pending_commitments(limit=500, include_past=True)]
    assert rid in ids_all


def test_urgent_sorts_before_normal():
    import db

    normal, _ = _insert(priority="normal", title="normal", event_date="2026-12-31")
    urgent, _ = _insert(priority="urgent", title="urgente", event_date="2026-12-31")
    order = [r["id"] for r in db.list_pending_commitments(limit=500)]
    assert order.index(urgent) < order.index(normal)


def test_raw_text_is_truncated_not_rejected():
    rid, _ = _insert(raw_text="x" * 5000)
    assert rid is not None


# --- contacts ---------------------------------------------------------------


def test_upsert_merges_aliases_without_duplicating():
    import db

    jid = f"{_uid()}@s.whatsapp.net"
    db.upsert_whatsapp_contact(jid, display_name="Pedro", aliases=["PN"])
    db.upsert_whatsapp_contact(jid, aliases=["pn", "Pedrão"])
    row = db.get_whatsapp_contact(jid)
    assert row["display_name"] == "Pedro", "an omitted field must not be wiped"
    lowered = [a.lower() for a in row["aliases"]]
    assert lowered.count("pn") == 1, "alias merge is case-insensitive"
    assert "pedrão" in lowered


def test_upsert_ignores_an_empty_jid():
    import db

    db.upsert_whatsapp_contact("")  # must not raise


def test_get_unknown_contact_returns_none():
    import db

    assert db.get_whatsapp_contact(f"{_uid()}@s.whatsapp.net") is None


# --- tool snapshots ---------------------------------------------------------


def test_tool_snapshots_round_trip_newest_first():
    import db

    sid = f"snap-{_uid()}"
    db.save_tool_snapshot(sid, "summarize_inbox", {"n": 1})
    db.save_tool_snapshot(sid, "summarize_inbox", {"n": 2})
    rows = db.load_tool_snapshots(sid, limit=5)
    assert rows[0]["payload"]["n"] == 2
    assert isinstance(rows[0]["created_at"], str), "must be JSON-serialisable"
