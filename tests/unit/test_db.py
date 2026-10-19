"""SCN-DB-01 — Postgres persistence, exercised against a real database.

`agent/db.py` had no tests: the migrations, the ON CONFLICT dedupe and the
status transitions were only ever verified by running the product. These skip
without `DATABASE_URL`, and CI provides an ephemeral Postgres service.
"""

import datetime as dt
import sys
import uuid
from pathlib import Path

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

# Every test here writes rows: run only against an ephemeral Postgres (see conftest.py).
pytestmark = pytest.mark.ephemeral_db


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


# --- needs_eval queue (evi-promise-context) ---------------------------------


def _needs_eval(next_eval_at=None, **kw):
    now = dt.datetime.now(dt.timezone.utc)
    return _insert(
        ctype="promise",
        event_date=None,
        due_date="2099-01-01",
        status="needs_eval",
        next_eval_at=next_eval_at or now - dt.timedelta(minutes=1),
        msg_ts=now - dt.timedelta(minutes=31),
        **kw,
    )


def test_needs_eval_columns_exist_and_migration_idempotent():
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    db.init_db()
    with db._conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'pending_commitments'"
        )
        cols = {r[0] for r in cur.fetchall()}
    assert {"next_eval_at", "eval_attempts", "msg_ts"} <= cols


def test_scn_debt_12_needs_eval_is_never_listed():
    import db

    rid, _ = _needs_eval()
    assert rid not in [r["id"] for r in db.list_pending_commitments(limit=500)]
    assert rid not in [r["id"] for r in db.list_pending_commitments(limit=500, include_past=True)]
    before = db.count_unnotified_pending()
    _needs_eval()
    assert db.count_unnotified_pending() == before


def test_list_promises_to_evaluate_only_due_needs_eval():
    import db

    now = dt.datetime.now(dt.timezone.utc)
    due, _ = _needs_eval()
    later, _ = _needs_eval(next_eval_at=now + dt.timedelta(hours=1))
    plain, _ = _insert()
    ids = [r["id"] for r in db.list_promises_to_evaluate(now, 500)]
    assert due in ids and later not in ids and plain not in ids


def test_finish_promise_evaluation_sets_status_title_due_once():
    import db

    rid, _ = _needs_eval()
    assert db.finish_promise_evaluation(rid, "pending", title="Mandar a proposta", due_date="2099-02-02")
    row = next(r for r in db.list_pending_commitments(limit=500, include_past=True) if r["id"] == rid)
    assert row["title"] == "Mandar a proposta" and row["due_date"] == "2099-02-02"
    assert db.finish_promise_evaluation(rid, "dismissed") is False  # no longer needs_eval


def test_finish_without_title_keeps_existing_values():
    import db

    rid, _ = _needs_eval()
    assert db.finish_promise_evaluation(rid, "pending")
    row = next(r for r in db.list_pending_commitments(limit=500, include_past=True) if r["id"] == rid)
    assert row["title"] == "Reunião" and row["due_date"] == "2099-01-01"


def test_bump_promise_eval_reschedules_and_counts_attempts():
    import db

    now = dt.datetime.now(dt.timezone.utc)
    rid, _ = _needs_eval()
    assert db.bump_promise_eval(rid, now + dt.timedelta(minutes=30))
    assert rid not in [r["id"] for r in db.list_promises_to_evaluate(now, 500)]
    with db._conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT eval_attempts FROM pending_commitments WHERE id = %s", (rid,))
        assert cur.fetchone()[0] == 1


def _promise(**kw):
    return _insert(source="whatsapp_from_me", ctype="promise", event_date=None,
                   source_chat="5511@s.whatsapp.net", **kw)


def test_sweep_helpers_select_mark_and_guard():
    import db

    now = dt.datetime.now(dt.timezone.utc)
    ok, _ = _promise()
    swept, _ = _promise()
    other_src, _ = _insert(ctype="promise", event_date=None, source_chat="x@s.whatsapp.net")
    old, _ = _promise()
    with db._conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE pending_commitments SET created_at = NOW() - interval '20 days' WHERE id = %s", (old,))
        conn.commit()
    assert db.mark_promise_swept(swept, now - dt.timedelta(hours=2))
    ids = [r["id"] for r in db.list_promises_to_sweep(now, 500)]
    assert ok in ids and swept not in ids and other_src not in ids and old not in ids
    later = now + dt.timedelta(hours=21)
    assert swept in [r["id"] for r in db.list_promises_to_sweep(later, 500)]
    assert db.mark_promise_done_by_sweep(ok) is True
    assert db.mark_promise_done_by_sweep(ok) is False  # guarded by status='pending'
    assert ok not in [r["id"] for r in db.list_promises_to_sweep(now, 500)]


def test_reeval_helpers_guarded_by_pending():
    import db

    rid, _ = _promise()
    assert rid in [r["id"] for r in db.list_pending_promises(5000)]
    assert db.update_pending_promise(rid, "Novo título", "2099-03-03")
    row = next(r for r in db.list_pending_promises(5000) if r["id"] == rid)
    assert row["title"] == "Novo título" and row["due_date"] == "2099-03-03"
    assert db.finish_pending_promise(rid, "dismissed", "auto-eval")
    assert db.finish_pending_promise(rid, "done", "auto-eval") is False
    assert db.update_pending_promise(rid, "x", None) is False


def test_scn_debt_12_expired_row_with_past_due_is_listed_after_clear_due():
    import db

    rid, _ = _needs_eval(raw_text="te mando amanhã")
    with db._conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE pending_commitments SET due_date = '2020-01-01' WHERE id = %s", (rid,))
        conn.commit()
    assert db.finish_promise_evaluation(rid, "pending", clear_due=True)
    row = next(r for r in db.list_pending_commitments(limit=500) if r["id"] == rid)
    assert row["due_date"] is None and row["raw_text"] == "te mando amanhã"


def test_release_needs_eval_makes_rows_pending_and_clears_past_due():
    import db

    past, _ = _needs_eval()
    future, _ = _needs_eval()
    with db._conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE pending_commitments SET due_date = '2020-01-01' WHERE id = %s", (past,))
        conn.commit()
    assert db.release_needs_eval() >= 2
    ids = {r["id"]: r for r in db.list_pending_commitments(limit=500)}
    assert past in ids and ids[past]["due_date"] is None
    assert future in ids and ids[future]["due_date"] == "2099-01-01"


def test_chat_listings_hide_needs_eval_and_auto_eval_dismissed():
    import db

    chat = f"{_uid()}@s.whatsapp.net"
    hidden, _ = _needs_eval(source_chat=chat)
    rejected, _ = _needs_eval(source_chat=chat)
    shown, _ = _insert(source_chat=chat)
    assert db.finish_promise_evaluation(rejected, "dismissed", confirmed_via="auto-eval")
    assert [r["id"] for r in db.list_commitments_for_chat(chat)] == [shown]
    assert [r["id"] for r in db.list_commitments_for_chat_since(chat)] == [shown]
    assert hidden not in [r["id"] for r in db.list_commitments_for_chat(chat)]


def test_action_rates_exclude_needs_eval_and_llm_rejected_promises():
    import db

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    base = db.action_rates_by_type(since, until, 1.0)["promise"]["shown"]
    rid, _ = _needs_eval(source="whatsapp_from_me")
    assert db.action_rates_by_type(since, until, 1.0)["promise"]["shown"] == base  # needs_eval
    db.finish_promise_evaluation(rid, "dismissed", confirmed_via="auto-eval")
    out = db.action_rates_by_type(since, until, 1.0)["promise"]
    assert out["shown"] == base  # LLM rejection: not shown, not acted


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


def test_name_source_is_recorded_and_defaults_to_user():
    """SCN-NAME-02: who set a name is stored; an unlabeled display_name is the user's."""
    import db

    jid = f"{_uid()}@s.whatsapp.net"
    db.upsert_whatsapp_contact(jid, whatsapp_label="PN")
    assert db.get_whatsapp_contact(jid)["name_source"] is None
    db.upsert_whatsapp_contact(jid, display_name="Ana", name_source="agenda")
    assert db.get_whatsapp_contact(jid)["name_source"] == "agenda"
    db.upsert_whatsapp_contact(jid, aliases=["x"])
    assert db.get_whatsapp_contact(jid)["name_source"] == "agenda", "unrelated writes keep it"
    db.upsert_whatsapp_contact(jid, display_name="Ana Maria")
    assert db.get_whatsapp_contact(jid)["name_source"] == "user"


def test_backfill_marks_existing_names_as_user_and_is_idempotent():
    import db

    named, bare = f"{_uid()}@s.whatsapp.net", f"{_uid()}@s.whatsapp.net"
    db.upsert_whatsapp_contact(named, display_name="Antigo")
    db.upsert_whatsapp_contact(bare, whatsapp_label="PN")
    with db._conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE whatsapp_contacts SET name_source = NULL WHERE jid = %s", (named,))
        conn.commit()
    assert db.backfill_name_source() >= 1
    assert db.get_whatsapp_contact(named)["name_source"] == "user"
    assert db.get_whatsapp_contact(bare)["name_source"] is None
    assert db.backfill_name_source() == 0


def test_upsert_guard_refuses_to_overwrite_a_user_name_under_the_lock():
    import db

    jid = f"{_uid()}@s.whatsapp.net"
    db.upsert_whatsapp_contact(jid, display_name="Do Usuário")  # source -> user
    ok = db.upsert_whatsapp_contact(
        jid, display_name="Agenda", name_source="agenda",
        only_if_name_source_in=(None, "agenda", "vcard"),
    )
    assert ok is False
    assert db.get_whatsapp_contact(jid)["display_name"] == "Do Usuário"
    other = f"{_uid()}@s.whatsapp.net"
    assert db.upsert_whatsapp_contact(
        other, display_name="Agenda", name_source="agenda",
        only_if_name_source_in=(None, "agenda", "vcard"),
    ) is True


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


# --- turn_log / probe_log (SCN-USE-01) ---------------------------------------


def _window():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    return now - timedelta(minutes=5), now + timedelta(minutes=5)


@pytest.mark.ephemeral_db
def test_turn_log_migration_idempotent_and_insert_list():
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    db.reset_db_init_for_tests()
    db.init_db()
    sid = f"test-{_uid()}"
    tools = [{"name": "calendar", "ok": True, "reason": None, "ms": 12}]
    tid = db.insert_turn(
        session_id=sid, channel="api", user_text="oi", reply_text="x" * 3000,
        tools=tools, latency_ms=5, llm_calls=2,
    )
    since, until = _window()
    rows = [r for r in db.list_turns(since, until) if r["session_id"] == sid]
    assert [r["id"] for r in rows] == [tid]
    assert rows[0]["tools"] == tools
    assert len(rows[0]["reply_text"]) == 2000
    assert rows[0]["signals"] == {}


@pytest.mark.ephemeral_db
def test_turn_log_excludes_test_by_default():
    import db

    sid = f"test-{_uid()}"
    db.insert_turn(session_id=sid, channel="api", user_text="t", is_test=True)
    since, until = _window()
    assert not [r for r in db.list_turns(since, until) if r["session_id"] == sid]
    assert [r for r in db.list_turns(since, until, include_test=True) if r["session_id"] == sid]


@pytest.mark.ephemeral_db
def test_feedback_targets_latest_non_command_turn():
    import db

    sid = f"test-{_uid()}"
    first = db.insert_turn(session_id=sid, channel="telegram", user_text="agenda?")
    second = db.insert_turn(session_id=sid, channel="telegram", user_text="e amanhã?")
    db.insert_turn(session_id=sid, channel="telegram", user_text="/ruim")
    assert db.set_turn_feedback(sid, "ruim", "errou") == second
    assert db.get_turn(second)["feedback"] == "ruim"
    assert db.get_turn(second)["feedback_note"] == "errou"
    assert db.get_turn(first)["feedback"] is None
    assert db.set_turn_feedback(f"none-{_uid()}", "bom") is None


@pytest.mark.ephemeral_db
def test_session_turns_around_and_signals():
    import db

    sid = f"test-{_uid()}"
    a = db.insert_turn(session_id=sid, channel="api", user_text="a")
    b = db.insert_turn(session_id=sid, channel="api", user_text="b")
    c = db.insert_turn(session_id=sid, channel="api", user_text="c")
    around = db.get_session_turns_around(b)
    assert around["prev"]["id"] == a and around["next"]["id"] == c
    assert db.get_session_turns_around(a)["prev"] is None
    assert db.get_session_turns_around(c)["next"] is None
    db.update_turn_signals(b, {"repeat": True})
    assert db.get_turn(b)["signals"] == {"repeat": True}
    assert db.get_turn(-1) is None


@pytest.mark.ephemeral_db
def test_probe_log_notified_flag():
    import datetime as dt

    import db

    day = dt.date(2099, 1, 1)
    chk = f"chk-{_uid()}"
    db.insert_probe(day, chk, False, "timeout", 900)
    assert not db.probe_already_notified(day, chk)
    db.mark_probe_notified(day, chk)
    assert db.probe_already_notified(day, chk)
    assert not db.probe_already_notified(dt.date(2099, 1, 2), chk)
    rows = [r for r in db.list_probes(day, day) if r["check_name"] == chk]
    assert rows and rows[0]["ok"] is False and rows[0]["reason"] == "timeout"


def test_record_source_keeps_first_down_since_and_ok_clears():
    import db

    src = f"src-{_uid()}"
    t1 = dt.datetime(2030, 1, 1, 10, 0, tzinfo=dt.timezone.utc)
    t2 = dt.datetime(2030, 1, 2, 10, 0, tzinfo=dt.timezone.utc)
    t3 = dt.datetime(2030, 1, 3, 10, 0, tzinfo=dt.timezone.utc)

    def row():
        return next((r for r in db.list_sources_down() if r["source"] == src), None)

    db.record_source(src, True, now=t1)
    assert row() is None
    db.record_source(src, False, "disconnected", now=t2)
    assert row()["down_since"] == t2 and row()["reason"] == "disconnected"
    db.record_source(src, False, "upstream_error", now=t3)
    assert row()["down_since"] == t2 and row()["reason"] == "upstream_error"
    db.record_source(src, True, now=t3)
    assert row() is None
    db.record_source(src, False, "disconnected", now=t3)
    assert row()["down_since"] == t3  # new outage restarts the clock


def test_record_source_first_fail_sets_down_since():
    import db

    src = f"src-{_uid()}"
    db.record_source(src, False, "oauth")
    r = next(r for r in db.list_sources_down() if r["source"] == src)
    assert r["down_since"] is not None and r["ok"] is False


# --- briefing_log (evi-morning-briefing) ---------------------------------------


@pytest.fixture
def briefing_days():
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    days = [dt.date(2001, 1, 1), dt.date(2001, 1, 2), dt.date(2001, 1, 3)]

    def _clean():
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM briefing_log WHERE day = ANY(%s)", (days,))
            conn.commit()

    _clean()
    yield days
    _clean()


@pytest.mark.ephemeral_db
def test_briefing_migration_idempotent(briefing_days):
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    db.reset_db_init_for_tests()
    db.init_db()
    assert db.get_briefing(briefing_days[0], "morning") is None


@pytest.mark.ephemeral_db
def test_briefing_unique_and_failed_send_can_retry(briefing_days):
    import db

    day = briefing_days[0]
    assert not db.briefing_sent_today(day, "morning")
    id1 = db.record_briefing(day, "morning", False, {"agenda": {"count": 0, "error": "boom"}})
    assert not db.briefing_sent_today(day, "morning")  # ok=false does not block a retry
    id2 = db.record_briefing(day, "morning", True, {"agenda": {"count": 3, "error": None}})
    assert id2 == id1  # UPSERT, not a second row
    assert db.briefing_sent_today(day, "morning")
    row = db.get_briefing(day, "morning")
    assert row["ok"] is True and row["sections"]["agenda"]["count"] == 3
    # force resend overwrites too
    db.record_briefing(day, "morning", True, {"agenda": {"count": 5, "error": None}})
    assert db.get_briefing(day, "morning")["sections"]["agenda"]["count"] == 5
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM briefing_log WHERE day = %s AND kind = 'morning'", (day,))
            assert cur.fetchone()[0] == 1


@pytest.mark.ephemeral_db
def test_briefing_sent_today_scoped_by_day_and_kind(briefing_days):
    import db

    d1, d2, _ = briefing_days
    db.record_briefing(d1, "morning", True, {})
    assert db.briefing_sent_today(d1, "morning")
    assert not db.briefing_sent_today(d1, "evening")
    assert not db.briefing_sent_today(d2, "morning")


@pytest.mark.ephemeral_db
def test_briefing_feedback_last_tap_wins_scn_ux_09(briefing_days):
    import db

    day = briefing_days[0]
    assert db.set_briefing_feedback(day, "morning", "down") is False  # no such row yet
    db.record_briefing(day, "morning", True, {})
    assert db.get_briefing(day, "morning")["feedback"] is None
    assert db.set_briefing_feedback(day, "morning", "down") is True
    assert db.set_briefing_feedback(day, "morning", "up") is True
    assert db.get_briefing(day, "morning")["feedback"] == "up"
    assert db.set_briefing_feedback(day, "morning", "meh") is False  # only up/down
    assert db.get_briefing(day, "morning")["feedback"] == "up"
    assert db.get_briefing(day, "evening") is None  # other kind untouched


@pytest.mark.ephemeral_db
def test_mark_briefing_replied_first_mark_only(briefing_days):
    import db

    day = briefing_days[2]
    assert db.mark_briefing_replied(day, "morning") is False  # no row
    db.record_briefing(day, "morning", True, {})
    assert db.get_briefing(day, "morning")["replied_at"] is None
    assert db.mark_briefing_replied(day, "morning") is True
    first = db.get_briefing(day, "morning")["replied_at"]
    assert first is not None
    assert db.mark_briefing_replied(day, "morning") is False
    assert db.get_briefing(day, "morning")["replied_at"] == first


@pytest.mark.ephemeral_db
def test_claim_briefing_atomic_and_stale_reclaim(briefing_days):
    import db

    day = briefing_days[0]
    first = db.claim_briefing(day, "morning")
    assert first is not None
    assert db.claim_briefing(day, "morning") is None  # in progress
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE briefing_log SET sent_at = now() - interval '11 minutes' "
                        "WHERE day = %s AND kind = 'morning'", (day,))
        conn.commit()
    assert db.claim_briefing(day, "morning") == first  # stale -> reclaimable
    db.record_briefing(day, "morning", True, {})
    assert db.claim_briefing(day, "morning") is None  # already sent
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE briefing_log SET sent_at = now() - interval '1 hour' "
                        "WHERE day = %s AND kind = 'morning'", (day,))
        conn.commit()
    assert db.claim_briefing(day, "morning") is None  # ok rows are never reclaimed


@pytest.mark.ephemeral_db
def test_failed_attempt_does_not_downgrade_ok_or_clear_replied(briefing_days):
    import db

    day = briefing_days[1]
    db.record_briefing(day, "morning", True, {})
    assert db.mark_briefing_replied(day, "morning") is True
    db.record_briefing(day, "morning", False, {"x": 1})
    row = db.get_briefing(day, "morning")
    assert row["ok"] is True and row["replied_at"] is not None
    db.record_briefing(day, "morning", True, {})  # successful resend resets
    assert db.get_briefing(day, "morning")["replied_at"] is None


@pytest.mark.ephemeral_db
def test_mark_briefing_replied_window(briefing_days):
    import db

    d1, d2, d3 = briefing_days
    db.record_briefing(d1, "evening", True, {})
    db.record_briefing(d2, "morning", True, {})
    db.record_briefing(d3, "morning", False, {})
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE briefing_log SET sent_at = now() - interval '4 hours' "
                        "WHERE day = %s", (d2,))
        conn.commit()
    assert db.mark_briefing_replied_window(hours=3) == ["evening"]
    assert db.mark_briefing_replied_window(hours=3) == []


@pytest.mark.ephemeral_db
def test_failed_send_releases_claim_for_immediate_retry(briefing_days):
    import db

    day = briefing_days[2]
    assert db.claim_briefing(day, "evening") is not None
    db.record_briefing(day, "evening", False, {})
    assert db.claim_briefing(day, "evening") is not None


# --- reminders (evi-reminders) ---------------------------------------------


@pytest.fixture
def rem_ids():
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    ids: list = []
    yield ids
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM reminder_fires WHERE reminder_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM reminders WHERE id = ANY(%s)", (ids,))
        conn.commit()


def _mk(ids, due, repeat=None, text="x"):
    import db

    rid = db.create_reminder(text, due, repeat, f"chat-{_uid()}", "agent")
    ids.append(rid)
    return rid


def _t(minutes):
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


@pytest.mark.ephemeral_db
def test_reminders_migration_twice_and_create_get_list(rem_ids):
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    db.reset_db_init_for_tests()
    db.init_db()
    rid = _mk(rem_ids, _t(60), repeat="daily", text="beber agua")
    row = db.get_reminder(rid)
    assert row["status"] == "pending" and row["repeat"] == "daily"
    assert row["due_at"].tzinfo is not None
    assert db.get_reminder(-1) is None
    assert rid in [r["id"] for r in db.list_reminders(chat_id=row["chat_id"])]
    assert db.list_reminders(chat_id=row["chat_id"], statuses=("sent",)) == []


@pytest.mark.ephemeral_db
def test_scn_rem_02_concurrent_claims_are_disjoint(rem_ids):
    """SCN-REM-02: two ticks claiming at once never get the same reminder id."""
    import threading

    import db

    ids = [_mk(rem_ids, _t(-10 + i * 0.01)) for i in range(30)]
    barrier = threading.Barrier(2)
    results: list = [None, None]

    def tick(i):
        barrier.wait()
        results[i] = {r["id"] for r in db.claim_due(_t(1), limit=30) if r["id"] in ids}

    threads = [threading.Thread(target=tick, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results[0].isdisjoint(results[1])
    assert results[0] | results[1] == set(ids)
    assert all(db.get_reminder(i)["status"] == "firing" for i in ids)


@pytest.mark.ephemeral_db
def test_claim_due_only_due_pending_ordered(rem_ids):
    import db

    late = _mk(rem_ids, _t(-30))
    soon = _mk(rem_ids, _t(-5))
    future = _mk(rem_ids, _t(60))
    got = [r["id"] for r in db.claim_due(_t(0), limit=1000) if r["id"] in rem_ids]
    assert got == [late, soon]
    assert db.get_reminder(future)["status"] == "pending"
    assert db.get_reminder(late)["claimed_at"] is not None
    assert [r for r in db.claim_due(_t(0)) if r["id"] in rem_ids] == []


@pytest.mark.ephemeral_db
def test_finish_fired_one_off_vs_recurring(rem_ids):
    import db

    one = _mk(rem_ids, _t(-1))
    rec = _mk(rem_ids, _t(-1), repeat="daily")
    db.claim_due(_t(0), limit=1000)
    fired = _t(0)
    db.finish_fired(one, fired, 42)
    row = db.get_reminder(one)
    assert row["status"] == "sent" and row["drift_s"] == 42 and row["fired_at"] is not None
    nxt = _t(24 * 60)
    db.finish_fired(rec, fired, 7, next_due_at=nxt)
    row = db.get_reminder(rec)
    assert row["status"] == "pending" and row["due_at"] == nxt and row["drift_s"] == 7
    assert row["fired_at"] is not None


@pytest.mark.ephemeral_db
def test_release_and_requeue_stuck(rem_ids):
    import db

    a = _mk(rem_ids, _t(-1))
    b = _mk(rem_ids, _t(-1))
    db.claim_due(_t(0), limit=1000)
    db.release_reminder(a)
    assert db.get_reminder(a)["status"] == "pending"
    assert db.requeue_stuck(older_than_minutes=5) >= 0
    assert db.get_reminder(b)["status"] == "firing"  # fresh claim not requeued
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE reminders SET claimed_at = now() - interval '10 minutes' "
                        "WHERE id = %s", (b,))
        conn.commit()
    assert db.requeue_stuck(older_than_minutes=5) >= 1
    assert db.get_reminder(b)["status"] == "pending"


@pytest.mark.ephemeral_db
def test_snooze_complete_cancel(rem_ids):
    import db

    r = _mk(rem_ids, _t(-1))
    db.claim_due(_t(0), limit=1000)
    assert db.snooze_reminder(r, _t(10)) is False  # firing: not snoozable
    db.finish_fired(r, _t(0), 1)
    until = _t(15)
    assert db.snooze_reminder(r, until) is True
    row = db.get_reminder(r)
    assert row["status"] == "pending" and row["snooze_until"] == until
    assert db.cancel_reminder(r) is True
    assert db.get_reminder(r)["status"] == "cancelled"
    assert db.cancel_reminder(r) is False
    assert db.snooze_reminder(r, _t(5)) is False
    assert db.complete_reminder(r) is None

    one = _mk(rem_ids, _t(60))
    assert db.complete_reminder(one) == {"recurring": False, "next_due_at": None}
    assert db.get_reminder(one)["status"] == "done"


@pytest.mark.ephemeral_db
def test_complete_recurring_only_acknowledges(rem_ids):
    import db

    due = _t(60)
    rec = _mk(rem_ids, due, repeat="weekly")
    res = db.complete_reminder(rec)
    assert res["recurring"] is True and res["next_due_at"] == due
    row = db.get_reminder(rec)
    assert row["status"] == "pending" and row["due_at"] == due
    assert db.cancel_reminder(rec) is True  # only cancel stops the series
    assert db.get_reminder(rec)["status"] == "cancelled"


@pytest.mark.ephemeral_db
def test_snooze_recurring_keeps_series_and_claims_on_snooze_time(rem_ids):
    """daily 08:00 + 'adia 1h': fires at the snooze time, due_at (series) untouched."""
    import db

    rec = _mk(rem_ids, _t(-1), repeat="daily")
    db.claim_due(_t(0), limit=1000)
    tomorrow = _t(24 * 60)
    db.finish_fired(rec, _t(0), 1, next_due_at=tomorrow)
    snooze = _t(30)
    assert db.snooze_reminder(rec, snooze) is True
    row = db.get_reminder(rec)
    assert row["due_at"] == tomorrow and row["snooze_until"] == snooze
    assert [r for r in db.claim_due(_t(10), limit=1000) if r["id"] == rec] == []
    got = [r for r in db.claim_due(_t(31), limit=1000) if r["id"] == rec]
    assert len(got) == 1 and got[0]["snooze_until"] == snooze
    db.finish_fired(rec, _t(31), 5, next_due_at=got[0]["due_at"])
    row = db.get_reminder(rec)
    assert row["status"] == "pending" and row["snooze_until"] is None and row["due_at"] == tomorrow


@pytest.mark.ephemeral_db
def test_finish_fired_requires_firing_and_chat_filter(rem_ids):
    import db

    r = _mk(rem_ids, _t(60))  # pending, never claimed
    assert db.finish_fired(r, _t(0), 1) is False
    assert db.get_reminder(r)["status"] == "pending"
    chat = db.get_reminder(r)["chat_id"]
    assert db.snooze_reminder(r, _t(5), chat_id="other") is False
    assert db.cancel_reminder(r, chat_id="other") is False
    assert db.complete_reminder(r, chat_id="other") is None
    assert db.snooze_reminder(r, _t(5), chat_id=chat) is True
    assert db.complete_reminder(r, chat_id=chat)["recurring"] is False


@pytest.mark.ephemeral_db
def test_fail_reminder(rem_ids):
    import db

    r = _mk(rem_ids, _t(-1))
    db.claim_due(_t(0), limit=1000)
    db.fail_reminder(r)
    assert db.get_reminder(r)["status"] == "failed"
    assert [x for x in db.claim_due(_t(5), limit=1000) if x["id"] == r] == []


@pytest.mark.ephemeral_db
def test_reminder_stats(rem_ids):
    import db

    ids = [_mk(rem_ids, _t(-1)) for _ in range(4)]
    db.claim_due(_t(0), limit=1000)
    for rid, d in zip(ids, (1, 2, 400, 3)):
        db.finish_fired(rid, _t(0), d)
    since, until = _window()
    st = db.reminder_stats(since, until)
    assert st["created"] >= 4 and st["fired"] >= 4 and st["late"] >= 1
    assert {1, 2, 400, 3} <= set(st["drifts"]) and st["p95_drift_s"] >= 3


@pytest.mark.ephemeral_db
def test_reminder_stats_counts_every_recurring_fire(rem_ids):
    """A recurring row is overwritten on each fire; reminder_fires keeps each occurrence."""
    import db

    rec = _mk(rem_ids, _t(-1), repeat="daily")
    since, until = _window()
    before = db.reminder_stats(since, until)
    for d, nxt in ((10, 60), (500, 120), (2, 180)):
        db.claim_due(_t(0), limit=1000)
        db.finish_fired(rec, _t(0), d, next_due_at=_t(-1) if nxt != 180 else _t(nxt))
    st = db.reminder_stats(since, until)
    assert st["fired"] - before["fired"] == 3
    assert st["late"] - before["late"] == 1
    assert {10, 500, 2} <= set(st["drifts"])
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM reminder_fires WHERE reminder_id = ANY(%s)", (rem_ids,))
        conn.commit()


@pytest.mark.ephemeral_db
def test_create_reminder_stores_monthly_anchor_day(rem_ids):
    import db
    from datetime import datetime
    from zoneinfo import ZoneInfo

    due = datetime(2026, 1, 31, 23, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))  # Feb 1 in UTC
    m = _mk(rem_ids, due, repeat="monthly")
    d = _mk(rem_ids, due, repeat="daily")
    assert db.get_reminder(m)["anchor_day"] == 31
    assert db.get_reminder(d)["anchor_day"] is None


# --- wa_conversation_state (evi-reply-debts) ----------------------------------


@pytest.mark.ephemeral_db
def test_wa_conversation_state_forward_only_and_idempotent():
    import db

    jid = f"{_uid()}@s.whatsapp.net"
    t1 = dt.datetime(2026, 6, 3, 10, 0, tzinfo=dt.timezone.utc)
    t2 = t1 + dt.timedelta(hours=1)
    db.record_inbound(jid, t2, "x" * 300, "m2")
    db.record_inbound(jid, t2, "x" * 300, "m2")  # redelivery
    db.record_inbound(jid, t1, "velha", "m1")  # older: ignored
    st = db.get_state(jid)
    assert st["last_in_id"] == "m2" and st["last_in_at"] == t2
    assert len(st["last_in_preview"]) == 160
    assert st["last_out_at"] is None

    db.record_outbound(jid, t2)
    db.record_outbound(jid, t1)  # older: ignored
    assert db.get_state(jid)["last_out_at"] == t2
    db.acknowledge(jid, t2)
    assert db.get_state(jid)["acknowledged_at"] == t2
    assert any(r["jid"] == jid for r in db.list_states())
    assert db.get_state("nope@s.whatsapp.net") is None


@pytest.mark.ephemeral_db
def test_wa_conversation_state_outbound_first_then_inbound():
    import db

    jid = f"{_uid()}@s.whatsapp.net"
    t = dt.datetime(2026, 6, 3, 10, 0, tzinfo=dt.timezone.utc)
    db.record_outbound(jid, t)
    db.record_inbound(jid, t + dt.timedelta(minutes=1), "oi", "m1")
    st = db.get_state(jid)
    assert st["last_out_at"] == t and st["last_in_id"] == "m1"



@pytest.mark.ephemeral_db
def test_list_debt_candidates_window_and_state_rules():
    import db

    now = dt.datetime(2026, 6, 10, 12, 0, tzinfo=dt.timezone.utc)
    h = lambda n: now - dt.timedelta(hours=n)  # noqa: E731
    u = _uid()
    cases = {
        "old": h(30), "mid": h(6), "fresh": h(1), "ancient": h(24 * 9),
        "replied": h(8), "acked": h(8),
    }
    jids = {k: f"{k}{u}@s.whatsapp.net" for k in cases}
    for k, ts in cases.items():
        db.record_inbound(jids[k], ts, k, f"m-{k}")
    db.record_outbound(jids["replied"], h(7))
    db.acknowledge(jids["acked"], h(7))
    rows = db.list_debt_candidates(now, dt.timedelta(hours=4), dt.timedelta(days=7))
    got = [r["jid"] for r in rows if r["jid"].endswith(f"{u}@s.whatsapp.net")]
    assert got == [jids["old"], jids["mid"]]
    # a newer inbound after the ack/reply revives the debt
    db.record_inbound(jids["acked"], h(5), "de novo", "m2")
    rows = db.list_debt_candidates(now, dt.timedelta(hours=4), dt.timedelta(days=7))
    assert jids["acked"] in [r["jid"] for r in rows]


# --- awaiting_reply (evi-awaiting-their-reply) --------------------------------


@pytest.mark.ephemeral_db
def test_list_awaiting_candidates_window_and_state_rules():
    import db

    now = dt.datetime(2026, 6, 10, 12, 0, tzinfo=dt.timezone.utc)
    d = lambda n: now - dt.timedelta(days=n)  # noqa: E731
    u = _uid()
    jids = {k: f"{k}{u}@s.whatsapp.net" for k in ("old", "mid", "fresh", "ancient", "replied", "inonly")}
    db.record_outbound(jids["old"], d(20))
    db.record_outbound(jids["mid"], d(4))
    db.record_outbound(jids["fresh"], d(1))
    db.record_outbound(jids["ancient"], d(40))
    db.record_outbound(jids["replied"], d(5))
    db.record_inbound(jids["replied"], d(2), "oi", "m1")  # they answered after
    db.record_inbound(jids["inonly"], d(5), "oi", "m2")  # user never spoke
    rows = db.list_awaiting_candidates(now, dt.timedelta(days=3), dt.timedelta(days=30))
    got = [r["jid"] for r in rows if r["jid"].endswith(f"{u}@s.whatsapp.net")]
    assert got == [jids["old"], jids["mid"]]  # oldest first
    # their older inbound does not hide it
    db.record_inbound(jids["mid"], d(6), "antes", "m3")
    rows = db.list_awaiting_candidates(now, dt.timedelta(days=3), dt.timedelta(days=30))
    assert jids["mid"] in [r["jid"] for r in rows]


@pytest.mark.ephemeral_db
def test_awaiting_dismissal_is_per_outbound_message_and_idempotent():
    import db

    jid = f"{_uid()}@s.whatsapp.net"
    t1 = dt.datetime(2026, 6, 3, 10, 0, 0, 123456, tzinfo=dt.timezone.utc)
    assert not db.is_awaiting_dismissed(jid, t1)
    db.dismiss_awaiting(jid, t1)
    db.dismiss_awaiting(jid, t1)  # second tap: no error, still one row
    assert db.is_awaiting_dismissed(jid, t1)
    assert not db.is_awaiting_dismissed(jid, t1 + dt.timedelta(hours=1))  # newer message reopens


# --- scheduled tasks (evi-scheduled-tasks) ---------------------------------------


@pytest.fixture
def sched_ids():
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    ids: list = []
    yield ids
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scheduled_tasks WHERE id = ANY(%s)", (ids,))
        conn.commit()


@pytest.mark.ephemeral_db
def test_scheduled_tasks_crud_due_and_caps(sched_ids):
    import db

    db.reset_db_init_for_tests()
    db.init_db()  # migration twice is harmless
    before = db.count_active_scheduled_tasks()
    a = db.create_scheduled_task("a", "pergunta a", _t(-5), "weekly")
    b = db.create_scheduled_task("b", "pergunta b", _t(600), None)
    sched_ids.extend([a, b])
    row = db.get_scheduled_task(a)
    assert row["active"] and row["repeat"] == "weekly" and row["runs_today"] == 0
    assert row["next_at"].tzinfo is not None and db.get_scheduled_task(-1) is None
    assert db.count_active_scheduled_tasks() == before + 2
    due = [r["id"] for r in db.due_scheduled_tasks(_t(0))]
    assert a in due and b not in due
    assert db.set_scheduled_task_active(b, False) and not db.get_scheduled_task(b)["active"]
    assert db.count_active_scheduled_tasks() == before + 1
    assert b not in [r["id"] for r in db.list_scheduled_tasks(active_only=True)]
    assert db.set_scheduled_task_active(b, True, _t(900))
    assert db.delete_scheduled_task(b) and db.get_scheduled_task(b) is None


@pytest.mark.ephemeral_db
def test_claim_scheduled_task_is_compare_and_swap(sched_ids):
    import datetime as _dt

    import db

    day = _dt.date(2031, 5, 5)
    t = _t(-1)
    tid = db.create_scheduled_task("c", "p", t, "daily")
    sched_ids.append(tid)
    base = db.scheduled_runs_on(day)
    nxt = _t(60 * 24)
    got = db.claim_scheduled_task(tid, t, nxt, True, day)
    assert got and got["next_at"] == nxt and got["runs_today"] == 1 and got["runs_day"] == day
    # a second tick with the stale next_at loses the race
    assert db.claim_scheduled_task(tid, t, nxt, True, day) is None
    assert db.scheduled_runs_on(day) == base + 1
    got = db.claim_scheduled_task(tid, nxt, _t(60 * 48), True, day)
    assert got["runs_today"] == 2
    # a capped (uncounted) claim advances without bumping the counter
    got = db.claim_scheduled_task(tid, got["next_at"], _t(60 * 72), True, day, count_run=False)
    assert got["runs_today"] == 2
    # a one-shot claim deactivates the row; new day resets the counter
    one = db.create_scheduled_task("d", "p", _t(-1), None)
    sched_ids.append(one)
    r = db.get_scheduled_task(one)
    got = db.claim_scheduled_task(one, r["next_at"], r["next_at"], False, day)
    assert got["active"] is False
    assert db.due_scheduled_tasks(_t(0)) == [x for x in db.due_scheduled_tasks(_t(0)) if x["id"] != one]
    db.finish_scheduled_task(one, "ok", _t(0))
    r = db.get_scheduled_task(one)
    assert r["last_status"] == "ok" and r["last_run_at"] is not None
    nxt_day = _dt.date(2031, 5, 6)
    got = db.claim_scheduled_task(tid, got_next(tid), _t(60 * 96), True, nxt_day)
    assert got["runs_today"] == 1 and got["runs_day"] == nxt_day


def got_next(tid):
    import db

    return db.get_scheduled_task(tid)["next_at"]


@pytest.mark.ephemeral_db
def test_scheduled_create_cap_is_atomic_and_soft_delete_keeps_run_count(sched_ids):
    import datetime as _dt
    import threading

    import db

    base = db.count_active_scheduled_tasks()
    cap = base + 1
    out: list = []
    ts = [
        threading.Thread(
            target=lambda: out.append(db.create_scheduled_task("t", "p", _t(60), None, max_active=cap))
        )
        for _ in range(6)
    ]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    made = [i for i in out if i is not None]
    sched_ids.extend(made)
    assert len(made) == 1 and out.count(None) == 5  # only one slot, no race overshoot
    assert db.count_active_scheduled_tasks() == cap
    # soft delete: leaves lists and the active count, keeps today's run counter
    day = _dt.date(2032, 1, 1)
    row = db.get_scheduled_task(made[0])
    db.claim_scheduled_task(made[0], row["next_at"], row["next_at"], True, day)
    assert db.scheduled_runs_on(day) == 1
    assert db.delete_scheduled_task(made[0]) and not db.delete_scheduled_task(made[0])
    assert db.get_scheduled_task(made[0]) is None
    assert made[0] not in [r["id"] for r in db.list_scheduled_tasks()]
    assert db.count_active_scheduled_tasks() == base
    assert db.scheduled_runs_on(day) == 1
    # resume cap
    a = db.create_scheduled_task("a", "p", _t(60), None)
    sched_ids.append(a)
    db.set_scheduled_task_active(a, False)
    assert db.set_scheduled_task_active(a, True, max_active=db.count_active_scheduled_tasks()) is False
    assert db.set_scheduled_task_active(a, True, max_active=db.count_active_scheduled_tasks() + 1) is True
