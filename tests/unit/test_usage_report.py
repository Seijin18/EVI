"""SCN-USE-05: weekly usage report (pure KPIs + DB-backed endpoint)."""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services import usage_report as ur  # noqa: E402

from zoneinfo import ZoneInfo  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")
MON = datetime(2026, 9, 28, tzinfo=TZ)  # local ISO 2026-W40


def mk(i, day=0, signals=None, test=False, feedback=None, lat=1000, llm=2, tools=None, ch="api"):
    return {
        "id": i,
        "ts": MON + timedelta(days=day, hours=10, minutes=i),
        "session_id": "s",
        "channel": ch,
        "user_text": f"pergunta {i}",
        "is_test": test,
        "signals": signals or {},
        "feedback": feedback,
        "latency_ms": lat,
        "llm_calls": llm,
        "tools": tools or [],
    }


def seeded_week():
    turns = [mk(i, day=i % 3, ch="telegram" if i < 4 else "api", lat=100 * (i + 1)) for i in range(10)]
    turns[2]["signals"] = {"correction": True}
    turns[7]["signals"] = {"correction": True}
    turns += [mk(100 + i, test=True, signals={"tool_failed": True}) for i in range(5)]
    return turns


def test_scn_use_05_exact_numbers():
    turns = seeded_week()
    k = ur.compute_kpis(turns)
    assert k["turns"] == 10
    assert k["success_rate"] == 0.8
    assert k["active_days"] == 3
    assert k["by_channel"] == {"telegram": 4, "api": 6}
    assert k["failure_total"] == 0  # test turns excluded
    rev = ur.review_candidates(turns)
    assert sorted(i["turn"]["id"] for i in rev) == [2, 7]
    assert all(i["flags"] == ["correction"] for i in rev)


def test_percentiles_and_llm_calls():
    k = ur.compute_kpis(seeded_week())
    assert k["latency_p50"] == 500.0
    assert k["latency_p95"] == 1000.0
    assert k["llm_calls_per_turn"] == 2.0
    assert ur.percentile([], 50) is None


def test_failures_by_tool_reason_and_review_priority():
    turns = [
        mk(1, signals={"rephrase": True}),
        mk(2, signals={"correction": True}),
        mk(3, signals={"tool_failed": True}, tools=[{"name": "calendar", "ok": False, "reason": "auth"}]),
        mk(4, feedback="ruim"),
        mk(5),
    ]
    k = ur.compute_kpis(turns)
    assert k["failures"] == {"calendar / auth": 1}
    assert [i["turn"]["id"] for i in ur.review_candidates(turns)] == [4, 3, 2, 1]
    assert len(ur.review_candidates([mk(i, signals={"rephrase": True}) for i in range(9)])) == 5


def test_deltas_vs_previous_and_baseline():
    cur = ur.compute_kpis(seeded_week())
    prev = dict(cur, success_rate=0.9, turns=8.0)
    base = dict(cur, success_rate=0.5, turns=5.0)
    rows = {r[0]: r for r in ur._kpi_rows(cur, prev, base)}
    assert rows["Taxa de sucesso"][2] == "-10 pp"
    assert rows["Taxa de sucesso"][3] == "+30 pp"
    assert rows["Turnos"][2] == "+2"
    assert ur._delta(None, 1.0) == "—"


def test_baseline_window_and_weeks():
    first = datetime(2026, 9, 2, 9, tzinfo=timezone.utc)  # Wednesday
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    start, end = ur.baseline_window(first, now)
    assert start == datetime(2026, 9, 7, tzinfo=TZ) and end - start == timedelta(days=14)
    assert ur.baseline_window(first, datetime(2026, 9, 20, tzinfo=timezone.utc)) is None
    assert ur.baseline_window(None, now) is None
    assert ur.parse_week("2026-W40") == MON
    with pytest.raises(ValueError):
        ur.parse_week("garbage")


def test_default_week_rule():
    sun = datetime(2026, 10, 4, 20, tzinfo=TZ)
    assert ur.default_week_start(sun) == MON  # Sunday 20h: week that is ending
    assert ur.default_week_start(datetime(2026, 10, 7, 12, tzinfo=TZ)) == MON  # Wed -> previous week W40
    assert ur.default_week_start(datetime(2026, 10, 5, 8, tzinfo=TZ)) == MON  # Monday -> previous week
    assert ur.default_week_start(datetime(2026, 10, 10, 23, tzinfo=TZ)) == MON  # Saturday -> previous week
    assert ur.default_week_start(datetime(2026, 10, 11, 20, tzinfo=TZ)) == MON + timedelta(days=7)


def test_local_sunday_night_turn_belongs_to_sunday_week():
    # local Sunday 23:30 == Monday 02:30 UTC
    t = mk(1)
    t["ts"] = datetime(2026, 10, 4, 23, 30, tzinfo=TZ)
    assert t["ts"].astimezone(timezone.utc).weekday() == 0
    end = ur._monday_midnight(MON.date() + timedelta(days=7))
    assert MON <= t["ts"] < end
    assert ur.compute_kpis([t])["active_days"] == 1
    assert ur.week_label(MON) == "2026-W40"


def test_probe_failure_days():
    d1, d2 = datetime(2026, 9, 28).date(), datetime(2026, 9, 29).date()
    probes = [
        {"day": d1, "check_name": "gmail", "ok": False},
        {"day": d1, "check_name": "gmail", "ok": False},
        {"day": d2, "check_name": "gmail", "ok": False},
        {"day": d2, "check_name": "calendar", "ok": True},
    ]
    assert ur.probe_failure_days(probes) == {"gmail": 2}


def test_telegram_has_no_user_text_and_max_10_lines():
    turns = seeded_week()
    r = {
        "label": "2026-W40", "start": MON, "end": MON + timedelta(days=7),
        "kpis": ur.compute_kpis(turns), "prev_kpis": None, "base_kpis": None,
        "baseline_range": None, "commitments": {"confirmed": 1, "dismissed": 2, "pending": 3},
        "probes": {"gmail": 2}, "review": ur.review_candidates(turns),
    }
    tg = ur.render_telegram(r)
    assert len(tg.splitlines()) <= 10
    assert "pergunta" not in tg and "2, 7" in tg
    md = ur.render_markdown(r)
    assert "pergunta 2" in md and "em formação" in md
    r["kpis"] = r["commitments"] = r["probes"] = r["review"] = None
    assert ur.UNAVAILABLE in ur.render_markdown(r)


needs_db = pytest.mark.ephemeral_db


@needs_db
def test_endpoint_end_to_end(tmp_path, monkeypatch):
    import db
    from fastapi.testclient import TestClient

    db.reset_db_init_for_tests()
    db.init_db()
    monkeypatch.setenv("EVI_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("EVI_API_KEY", raising=False)
    sent = []
    import services.telegram_notify as tn

    monkeypatch.setattr(tn, "send_telegram_message", lambda text, chat_id=None: sent.append(text) or True)

    week = "2020-W10"  # far past: isolated from real data
    monkeypatch.setattr(ur, "prune_turn_log", lambda days=180: 0)  # 2020 rows would be pruned
    start = ur.parse_week(week)
    sid = f"usr-{uuid.uuid4().hex[:8]}"
    ids = []
    for i in range(10):
        ids.append(db.insert_turn(session_id=f"{sid}-{i}", channel="api", user_text=f"consulta unica {i} {sid}",
                                  latency_ms=100 * (i + 1), llm_calls=2))
    for i in range(5):
        ids.append(db.insert_turn(session_id=f"evi-test-{sid}-{i}", channel="api", user_text="teste", is_test=True))
    with db._conn() as conn:
        with conn.cursor() as cur:  # only the rows this test inserted (cleaned up by conftest)
            cur.execute("UPDATE turn_log SET ts = %s WHERE id = ANY(%s)",
                        (start + timedelta(days=1, hours=10), ids))
        conn.commit()
    ids = ids[:10]
    for tid in ids[:2]:
        db.update_turn_signals(tid, {"correction": True})

    import main

    resp = TestClient(main.app).post(f"/jobs/usage-report?week={week}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # signals are recomputed by the job (no real corrections in the data) -> rerun-safe check on shape
    assert body["week"] == week and body["kpis"]["turns"] == 10
    md = Path(body["path"]).read_text(encoding="utf-8")
    assert Path(body["path"]).parent == tmp_path / "reports"
    assert "Turnos para revisar" in md
    assert len(sent) == 1 and len(sent[0].splitlines()) <= 10 and "consulta unica" not in sent[0]
    assert body["local_report"] == body["path"]
    assert TestClient(main.app).post("/jobs/usage-report?week=bad").status_code == 400
    assert TestClient(main.app).post("/jobs/usage-signals").json()["ok"] is True


def test_baseline_is_persisted_and_never_recomputed(tmp_path, monkeypatch):
    import db

    monkeypatch.setenv("EVI_WORKSPACE", str(tmp_path))
    first = datetime(2026, 9, 2, 9, tzinfo=TZ)
    calls = {"n": 0}

    def fake_list(since, until, include_test=False):
        calls["n"] += 1
        return seeded_week()

    monkeypatch.setattr(db, "list_turns", fake_list)
    monkeypatch.setattr(db, "list_probes", lambda *a: [])
    monkeypatch.setattr(ur, "run_usage_signals", lambda **k: {})
    monkeypatch.setattr(ur, "prune_turn_log", lambda d=180: 0)
    monkeypatch.setattr(ur, "_first_real_turn_ts", lambda: first)
    monkeypatch.setattr(ur, "_fetch_commitments", lambda s, e: {"confirmed": 0, "dismissed": 0, "pending": 0})
    now = datetime(2026, 10, 10, tzinfo=TZ)
    r1 = ur.build_report(MON, now)
    stored = ur._load_baseline()
    assert stored and stored["start_week"] == "2026-W37" and stored["end_week"] == "2026-W38"
    assert (tmp_path / "reports" / "baseline.json").exists()
    assert r1["base_kpis"]["turns"] == 5.0 and r1["baseline_range"] == "2026-09-07 a 2026-09-20"
    # first turn "moves" (prune drift) and data changes: stored baseline wins
    monkeypatch.setattr(ur, "_first_real_turn_ts", lambda: datetime(2026, 12, 1, tzinfo=TZ))
    monkeypatch.setattr(db, "list_turns", lambda *a, **k: [])
    r2 = ur.build_report(MON, now)
    assert r2["base_kpis"] == r1["base_kpis"] and r2["baseline_range"] == r1["baseline_range"]


def test_baseline_in_formation_writes_nothing(tmp_path, monkeypatch):
    import db

    monkeypatch.setenv("EVI_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(db, "list_turns", lambda *a, **k: [])
    monkeypatch.setattr(db, "list_probes", lambda *a: [])
    monkeypatch.setattr(ur, "run_usage_signals", lambda **k: {})
    monkeypatch.setattr(ur, "prune_turn_log", lambda d=180: 0)
    monkeypatch.setattr(ur, "_first_real_turn_ts", lambda: datetime(2026, 10, 1, tzinfo=TZ))
    monkeypatch.setattr(ur, "_fetch_commitments", lambda s, e: {"confirmed": 0, "dismissed": 0, "pending": 0})
    r = ur.build_report(MON, datetime(2026, 10, 10, tzinfo=TZ))
    assert r["base_kpis"] is None and not (tmp_path / "reports" / "baseline.json").exists()


def test_markdown_write_failure_still_sends_summary(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(ur, "build_report", lambda ws, now=None: {
        "label": "2026-W40", "start": MON, "end": MON + timedelta(days=7), "kpis": None, "review": None,
        "prev_kpis": None, "base_kpis": None, "baseline_range": None, "commitments": None, "probes": None,
    })
    blocker = tmp_path / "ws"
    blocker.write_text("not a dir")  # reports/ cannot be created under a file
    monkeypatch.setenv("EVI_WORKSPACE", str(blocker))
    monkeypatch.setattr("services.telegram_notify.send_telegram_message", lambda t, chat_id=None: sent.append(t) or True)
    out = ur.generate_report(week="2026-W40")
    assert out["ok"] is True and out["path"] is None and out["local_report"] == "relatório local indisponível"
    assert len(sent) == 1 and out["telegram_sent"] is True


def test_report_lists_new_payload_shapes_without_values():
    base = {
        "label": "2026-W41", "start": datetime(2026, 10, 5, tzinfo=timezone.utc),
        "end": datetime(2026, 10, 12, tzinfo=timezone.utc), "kpis": None, "review": None,
        "prev_kpis": None, "base_kpis": None, "commitments": None, "probes": None,
    }
    md = ur.render_markdown({**base, "shapes": [{"file": "abc123.json", "event": "messages.upsert"}]})
    assert "## Formatos novos do Evolution" in md and "abc123.json" in md
    assert ur.UNAVAILABLE in ur.render_markdown({**base, "shapes": None}).split("Formatos novos")[1]


def test_reminders_section_renders_counts_only_and_telegram_cap():
    turns = seeded_week()
    r = {
        "label": "2026-W40", "start": MON, "end": MON + timedelta(days=7),
        "kpis": ur.compute_kpis(turns), "prev_kpis": None, "base_kpis": None,
        "baseline_range": None, "commitments": {"confirmed": 1, "dismissed": 2, "pending": 3},
        "probes": {"gmail": 2}, "review": ur.review_candidates(turns),
        "reminders": {"created": 12, "fired": 10, "late": 0, "p95_drift_s": 240},
    }
    md = ur.render_markdown(r)
    assert "## Lembretes" in md and "disparados: 10" in md and "atrasados (>5 min): 0" in md and "240 s" in md
    tg = ur.render_telegram(r)
    assert "Lembretes: 12 criados / 10 disp. / 0 atras." in tg and len(tg.splitlines()) <= 10
    r["reminders"] = {"created": 0, "fired": 0, "late": 0, "p95_drift_s": None}
    assert "Lembretes" not in ur.render_telegram(r)
    r["reminders"] = None
    assert ur.UNAVAILABLE in ur.render_markdown(r).split("## Lembretes")[1].split("##")[0]
    assert "Lembretes" not in ur.render_telegram(r)


@needs_db
def test_scn_rem_06_weekly_report_reminders(tmp_path, monkeypatch):
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    monkeypatch.setenv("EVI_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(ur, "prune_turn_log", lambda days=180: 0)
    start = ur.parse_week("2020-W20")
    end = start + timedelta(days=7)
    ids = []
    try:
        for i in range(10):
            due = start + timedelta(days=1, hours=i)
            rid = db.create_reminder(f"segredo {i}", due, None, "chat-rem06", "test")
            ids.append(rid)
            drift = 240 if i == 4 else 2 + i
            db.finish_fired(rid, due + timedelta(seconds=drift), drift)
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE reminders SET created_at = %s WHERE id = ANY(%s)", (start + timedelta(hours=1), ids))
            conn.commit()
        rep = ur.build_report(start, start + timedelta(days=8))
        assert rep["reminders"] == {"created": 10, "fired": 10, "late": 0, "p95_drift_s": 240}
        md = ur.render_markdown(rep)
        assert "disparados: 10" in md and "atrasados (>5 min): 0" in md and "240 s" in md
        assert "segredo" not in md and "segredo" not in ur.render_telegram(rep)
    finally:
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM reminder_fires WHERE reminder_id = ANY(%s)", (ids,))
                cur.execute("DELETE FROM reminders WHERE id = ANY(%s)", (ids,))
            conn.commit()
