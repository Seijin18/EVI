"""evi-sim scenario schema: validation, relative dates, expectation evaluation."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from testing.sim import schema
from testing.sim.schema import ScenarioError, parse_relative, parse_scenario

TZ = "America/Sao_Paulo"
BASE = date(2026, 3, 10)


def _scn(**over):
    d = {"id": "SIM-X", "steps": [{"telegram": "oi", "expect": {"reply_within_s": 5}}]}
    d.update(over)
    return d


def test_relative_dates():
    assert parse_relative("D0 09:12", BASE, TZ) == datetime(2026, 3, 10, 9, 12, tzinfo=ZoneInfo(TZ))
    assert parse_relative("D1 10:00", BASE, TZ).day == 11
    assert parse_relative("D-1", BASE, TZ) == datetime(2026, 3, 9, 0, 0, tzinfo=ZoneInfo(TZ))
    assert parse_relative("D-12 23:59", date(2026, 3, 5), TZ).date() == date(2026, 2, 21)
    with pytest.raises(ValueError):
        parse_relative("tomorrow", BASE, TZ)
    with pytest.raises(ValueError):
        parse_relative("D0 25:00", BASE, TZ)


def test_relative_dates_dst_safe():
    # New York DST starts 2026-03-08: wall-clock time must not shift across it
    dt = parse_relative("D1 10:00", date(2026, 3, 7), "America/New_York")
    assert (dt.hour, dt.utcoffset().total_seconds()) == (10, -4 * 3600)
    assert parse_relative("D0 10:00", date(2026, 3, 7), "America/New_York").utcoffset().total_seconds() == -5 * 3600


def test_parse_valid_scenario():
    s = parse_scenario(_scn(tags=["a"], source="real-usage", clock="D0 09:12", judge={"rubric": "x"}))
    assert s.id == "SIM-X" and s.steps[0].type == "telegram" and s.judge is not None


@pytest.mark.parametrize(
    "bad,needle",
    [
        (_scn(bogus=1), "bogus"),
        (_scn(steps=[{"telegram": "a", "expect": {"nope": 1}}]), "steps[0].expect.nope"),
        (_scn(steps=[{"telegram": "a", "job": "heartbeat"}]), "exactly one"),
        (_scn(steps=[{"expect": {}}]), "exactly one"),
        (_scn(steps=[{"job": "other"}]), "job"),
        (_scn(source="weird"), "source"),
        (_scn(clock="tomorrow"), "clock"),
        (_scn(steps=[{"telegram": "a", "expect": {"postgres": [{"table": "pg_user", "count": 1}]}}]), "allowlist"),
        (_scn(steps=[{"telegram": "a", "expect": {"reply_matches": "("}}]), "regex"),
        (_scn(steps=[{"telegram": "a", "expect": {"calendar": {"x": 1}}}]), "calendar.x"),
        ({"steps": [{"telegram": "a"}]}, "id"),
    ],
)
def test_validation_errors_name_file_and_key(bad, needle):
    with pytest.raises(ScenarioError) as ei:
        parse_scenario(bad, "tests/sim/scenarios/x.yaml")
    assert "tests/sim/scenarios/x.yaml" in str(ei.value) and needle in str(ei.value)


def test_load_scenarios_filters(tmp_path):
    (tmp_path / "a.yaml").write_text("id: A\ntags: [critical]\nsteps:\n  - telegram: oi\n")
    (tmp_path / "b.yaml").write_text("id: B\ntags: [smoke]\nsteps:\n  - clock: '+1h'\n")
    assert {s.id for s in schema.load_scenarios(tmp_path)} == {"A", "B"}
    assert [s.id for s in schema.load_scenarios(tmp_path, tags=["smoke"])] == ["B"]
    assert [s.id for s in schema.load_scenarios(tmp_path, ids=["A"])] == ["A"]
    (tmp_path / "c.yaml").write_text("id: A\nsteps:\n  - telegram: x\n")
    with pytest.raises(ScenarioError, match="duplicate"):
        schema.load_scenarios(tmp_path)


def test_resolve_seed():
    seed = schema.resolve_seed(
        {"calendar": [{"summary": "D", "start": "D0 15:00", "end": "D0 16:00"}], "tasks": [{"title": "t", "due": "D1"}]},
        BASE,
        TZ,
    )
    assert seed["calendar"][0]["start"] == "2026-03-10T15:00:00-03:00"
    assert seed["tasks"][0]["due"] == "2026-03-11"


GOOGLE = {
    "created": {
        "calendar": [{"summary": "Reunião Aymo", "start": "2026-03-11T10:00:00-03:00", "end": "2026-03-11T11:00:00-03:00"}],
        "tasks": [{"title": "Pagar boleto", "due": "2026-03-12T00:00:00.000Z"}],
    },
    "calendar": [{"summary": "Dentista"}],
    "tasks": [],
    "deleted": ["m1", "m2"],
}


def test_eval_calendar_and_tasks():
    ok = {"calendar": {"created": [{"summary_contains": "reunião aymo", "start": "D1 10:00"}], "count": 1},
          "tasks": {"created": [{"title_contains": "boleto", "due": "D2"}]}}
    assert schema.eval_expect(ok, {"google": GOOGLE, "base": BASE, "tz": TZ}) == []
    bad = {"calendar": {"created": [{"summary_contains": "aymo", "start": "D1 11:00"}, {"summary_contains": "zzz"}], "count": 2},
           "tasks": {"created": [{"title_contains": "boleto", "due": "D5"}]}}
    fails = schema.eval_expect(bad, {"google": GOOGLE, "base": BASE, "tz": TZ})
    assert len(fails) == 4


def test_eval_gmail_tools_outbound_reply_postgres():
    obs = {
        "google": GOOGLE, "reply": "Feito! Agendei.", "latency_s": 12.0,
        "tools_called": ["schedule_event"],
        "evolution_sent": [{"jid": "5500000000001@s.whatsapp.net"}, {"jid": "5511@s.whatsapp.net"}],
        "telegram_sent": [{"chat_id": 900000001}, {"chat_id": 5}],
        "control_jids": {"5500000000001@s.whatsapp.net"}, "chat_id": "900000001",
        "postgres": [2],
    }
    exp = {
        "reply_within_s": 90, "reply_matches": "agend", "tools_called_any": ["schedule_event"],
        "tools_not_called": ["delete_emails"], "outbound_to_third_parties": 2,
        "gmail": {"deleted_count": 2, "deleted_ids_include": ["m1"], "not_deleted": ["m9"]},
        "postgres": [{"table": "pending_commitments", "count": 2}],
    }
    assert schema.eval_expect(exp, obs) == []
    exp2 = {**exp, "reply_within_s": 5, "tools_not_called": ["schedule_event"], "outbound_to_third_parties": 0,
            "gmail": {"deleted_count": 1, "not_deleted": ["m1"]}, "postgres": [{"table": "messages", "count": 9}],
            "tools_called_any": ["x"], "reply_matches": "^nope$"}
    assert len(schema.eval_expect(exp2, obs)) == 8
    assert "no reply" in schema.eval_expect({"reply_within_s": 5}, {"reply": None})[0]


def test_clock_step_accepts_reply_and_no_reply_expectations():
    s = parse_scenario(_scn(steps=[
        {"clock": "D0 18:00", "expect": {"reply_within_s": 30, "reply_matches": "(?i)boleto"}},
        {"clock": "+10m", "expect": {"no_reply": True}},
    ]))
    assert s.steps[0].expect["reply_within_s"] == 30 and s.steps[1].expect["no_reply"] is True


def test_no_reply_still_rejected_on_job_step():
    with pytest.raises(ScenarioError):
        parse_scenario(_scn(steps=[{"job": "heartbeat", "expect": {"no_reply": True}}]))


def test_reminders_tables_are_in_postgres_allowlist():
    s = parse_scenario(_scn(steps=[{"telegram": "a", "expect": {"postgres": [
        {"table": "reminders", "where": {"status": "sent"}, "count": 1},
        {"table": "reminder_fires", "count": 1},
    ]}}]))
    assert len(s.steps[0].expect["postgres"]) == 2


def test_wa_conversation_state_in_postgres_allowlist():
    s = parse_scenario(_scn(steps=[{"telegram": "a", "expect": {"postgres": [
        {"table": "wa_conversation_state", "where": {"acknowledged_at": None}, "count": 0},
    ]}}]))
    assert s.steps[0].expect["postgres"][0]["table"] == "wa_conversation_state"


def test_reply_not_matches_eval_and_validation():
    exp = {"reply_not_matches": "Esperando sua resposta"}
    assert schema.eval_expect(exp, {"reply": "Bom dia\n1. Standup"}) == []
    assert schema.eval_expect(exp, {"reply": "Esperando sua resposta\n1. Ana"})
    assert schema.eval_expect(exp, {"reply": None})
    with pytest.raises(ScenarioError):
        parse_scenario(_scn(steps=[{"telegram": "a", "expect": {"reply_not_matches": "("}}]))
    with pytest.raises(ScenarioError):
        parse_scenario(_scn(steps=[{"telegram": "a", "expect": {"no_reply": True, "reply_not_matches": "x"}}]))


# ------------------------------------------------------------------ voice steps (evi-voice-input)
def _voice_scn(step, expect=None):
    st = dict(step)
    if expect:
        st["expect"] = expect
    return {"id": "X", "steps": [st]}


def test_voice_steps_parse():
    scn = schema.parse_scenario(
        {
            "id": "X",
            "steps": [
                {"telegram_voice": {"file": "marca_dentista.ogg", "duration_s": 900}, "expect": {"reply_matches": "x"}},
                {"whatsapp_control_voice": {"file": "compromissos.ogg"}, "expect": {"reply_within_s": 60}},
                {"whatsapp_contact_voice": {"file": "compromissos.ogg", "jid": "5511@s.whatsapp.net"}, "expect": {"media_requests": 0, "outbound_to_third_parties": 0}},
            ],
        }
    )
    assert [s.type for s in scn.steps] == ["telegram_voice", "whatsapp_control_voice", "whatsapp_contact_voice"]
    assert scn.steps[0].value["duration_s"] == 900


@pytest.mark.parametrize(
    "step, needle",
    [
        ({"telegram_voice": "a.ogg"}, "mapping"),
        ({"telegram_voice": {"duration_s": 3}}, "file"),
        ({"telegram_voice": {"file": "../x.ogg"}}, "file"),
        ({"telegram_voice": {"file": "a.ogg", "duration_s": 0}}, "duration_s"),
        ({"telegram_voice": {"file": "a.ogg", "jid": "x"}}, "jid"),
        ({"whatsapp_control_voice": {"file": "a.ogg", "jid": "x"}}, "jid"),
        ({"whatsapp_contact_voice": {"file": "a.ogg", "bogus": 1}}, "bogus"),
    ],
)
def test_voice_step_validation(step, needle):
    with pytest.raises(schema.ScenarioError) as ei:
        schema.parse_scenario(_voice_scn(step))
    assert needle in str(ei.value)


def test_media_requests_expectation():
    assert schema.eval_expect({"media_requests": 0}, {"media_requests": []}) == []
    fails = schema.eval_expect({"media_requests": 0}, {"media_requests": [{"id": "A"}]})
    assert fails and "media_requests" in fails[0]
    with pytest.raises(schema.ScenarioError):
        schema.parse_scenario(_voice_scn({"telegram": "oi"}, {"media_requests": "0"}))


def test_no_reply_allowed_on_voice_steps_only_where_replies_exist():
    schema.parse_scenario(_voice_scn({"whatsapp_control_voice": {"file": "a.ogg"}}, {"no_reply": True}))
    with pytest.raises(schema.ScenarioError):
        schema.parse_scenario(_voice_scn({"whatsapp_contact_voice": {"file": "a.ogg"}}, {"no_reply": True}))
