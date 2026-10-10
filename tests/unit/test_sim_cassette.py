"""evi-sim cassettes (SCN-SIM-09): key normalization, replay order, stale error, prod unaffected."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

import llm
from testing.sim import cassette as cs


@tool
def schedule_event(title: str, date: str) -> str:
    """Create an event."""
    return "ok"


def _prompt(d: date, hhmm: str = "09:15:42") -> list:
    wd = d.strftime("%A")
    return [
        SystemMessage(content=f"Today is {wd}, {d.isoformat()}. Current time: {hhmm}\n- +1 days: {(d + timedelta(1)).isoformat()}"),
        HumanMessage(content=f"marque dentistro em {(d + timedelta(1)).isoformat()} (dia 12 de outubro)"),
    ]


def test_key_stable_across_days_and_times():
    d1, d2 = date(2026, 10, 10), date(2026, 11, 3)
    k1 = cs.request_key(_prompt(d1), [schedule_event], d1)
    k2 = cs.request_key(_prompt(d2, "17:01:09"), [schedule_event], d2)
    assert k1 == k2


def test_key_changes_with_prompt_or_tools():
    d = date(2026, 10, 10)
    base = cs.request_key(_prompt(d), [schedule_event], d)
    changed = _prompt(d)
    changed[0] = SystemMessage(content=changed[0].content + " Be terse.")
    assert cs.request_key(changed, [schedule_event], d) != base
    assert cs.request_key(_prompt(d), [], d) != base


def test_key_ignores_tool_call_ids():
    d = date(2026, 10, 10)

    def conv(cid):
        return [
            HumanMessage(content="oi"),
            AIMessage(content="", tool_calls=[{"name": "schedule_event", "args": {"date": d.isoformat()}, "id": cid}]),
            ToolMessage(content="done", tool_call_id=cid, name="schedule_event"),
        ]

    assert cs.request_key(conv("a"), None, d) == cs.request_key(conv("b"), None, d)


def test_response_dates_shift_with_replay_day():
    rec = date(2026, 10, 10)
    msg = AIMessage(content="", tool_calls=[{"name": "schedule_event", "args": {"title": "x", "date": "2026-10-11"}, "id": "1"}])
    enc = cs.encode_response(msg, rec)
    assert "2026" not in json.dumps(enc)
    out = cs.decode_response(enc, date(2026, 12, 30))
    assert out.tool_calls[0]["args"]["date"] == "2026-12-31"


def test_datetime_args_shift_and_keys_stable_across_days():
    d0, d1 = date(2026, 10, 10), date(2026, 10, 11)
    msg = AIMessage(content="", tool_calls=[{"name": "schedule_event", "args": {"start": "2026-10-11T10:00:00-03:00"}, "id": "1"}])
    enc = cs.encode_response(msg, d0)
    assert "2026" not in json.dumps(enc)
    assert cs.decode_response(enc, d1).tool_calls[0]["args"]["start"] == "2026-10-12T10:00:00-03:00"

    def conv(d):
        return [HumanMessage(content=f"x {(d + timedelta(1)).isoformat()}T10:00:00"), ToolMessage(content=f"ev {d.isoformat()}T09:00:00", tool_call_id="a")]

    assert cs.request_key(conv(d0), None, d0) == cs.request_key(conv(d1), None, d1)


def test_time_and_weekday_only_normalized_in_calendar_header():
    d = date(2026, 10, 10)
    hdr = lambda t: [SystemMessage(content=f"Today is Saturday, 2026-10-10. Current time: {t}\nrule at 10:00 on Monday")]  # noqa: E731
    assert cs.request_key(hdr("09:00:01"), None, d) == cs.request_key(hdr("17:30:59"), None, d)
    edited = [SystemMessage(content="Today is Saturday, 2026-10-10. Current time: 09:00:01\nrule at 11:00 on Monday")]
    assert cs.request_key(edited, None, d) != cs.request_key(hdr("09:00:01"), None, d)


def test_replay_next_day_end_to_end(sim_dir, monkeypatch):
    d0 = date(2026, 10, 10)
    msgs = lambda d: [HumanMessage(content=f"agenda de {d.isoformat()}")]  # noqa: E731
    call = AIMessage(content="", tool_calls=[{"name": "schedule_event", "args": {"start": "2026-10-11T10:00:00"}, "id": "z"}])
    key = cs.request_key(msgs(d0), None, d0)
    (sim_dir / "SIM-X.jsonl").write_text(json.dumps({"key": key, "response": cs.encode_response(call, d0)}) + "\n")
    _announce(sim_dir)
    monkeypatch.setattr(cs, "_today", lambda: date(2026, 10, 11))
    out = cs.build_sim_llm("sim-replay").invoke(msgs(date(2026, 10, 11)))
    assert out.tool_calls[0]["args"]["start"] == "2026-10-12T10:00:00"


def test_over_asking_a_key_is_stale(sim_dir):
    msgs = [HumanMessage(content="oi")]
    _write_cassette(sim_dir, "SIM-X", [(msgs, None, "um")])
    _announce(sim_dir)
    model = cs.build_sim_llm("sim-replay")
    assert model.invoke(msgs).content == "um"
    with pytest.raises(cs.CassetteStale, match="cassette stale: regrave com --llm record"):
        model.invoke(msgs)


@pytest.fixture
def sim_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "_STATE", cs._Cassette(tmp_path))
    monkeypatch.setattr(cs, "_today", lambda: date(2026, 10, 10))
    return tmp_path


def _announce(d, scn="SIM-X", nonce="n1"):
    (d / "ctl").write_text(json.dumps({"id": scn, "nonce": nonce}))


def _write_cassette(d, scn, pairs):
    with open(d / f"{scn}.jsonl", "w") as f:
        for msgs, tools, answer in pairs:
            key = cs.request_key(msgs, tools, date(2026, 10, 10))
            f.write(json.dumps({"key": key, "response": cs.encode_response(AIMessage(content=answer), date(2026, 10, 10))}) + "\n")


def test_replay_serves_in_recorded_order(sim_dir):
    msgs = [HumanMessage(content="oi")]
    _write_cassette(sim_dir, "SIM-X", [(msgs, None, "um"), (msgs, None, "dois")])
    _announce(sim_dir)
    model = cs.build_sim_llm("sim-replay")
    assert [model.invoke(msgs).content for _ in range(2)] == ["um", "dois"]
    _announce(sim_dir, nonce="n2")  # new attempt: consumption restarts
    assert model.invoke(msgs).content == "um"


def test_replay_with_tools_and_tool_calls(sim_dir):
    msgs = [HumanMessage(content="agende")]
    call = AIMessage(content="", tool_calls=[{"name": "schedule_event", "args": {"title": "t", "date": "2026-10-11"}, "id": "z"}])
    key = cs.request_key(msgs, [schedule_event], date(2026, 10, 10))
    (sim_dir / "SIM-X.jsonl").write_text(json.dumps({"key": key, "response": cs.encode_response(call, date(2026, 10, 10))}) + "\n")
    _announce(sim_dir)
    out = cs.build_sim_llm("sim-replay").bind_tools([schedule_event]).invoke(msgs)
    assert out.tool_calls[0]["name"] == "schedule_event"
    assert out.tool_calls[0]["args"]["date"] == "2026-10-11"


def test_stale_error_message_and_log(sim_dir):
    _write_cassette(sim_dir, "SIM-X", [([HumanMessage(content="oi")], None, "x")])
    _announce(sim_dir)
    with pytest.raises(cs.CassetteStale, match="cassette stale: regrave com --llm record"):
        cs.build_sim_llm("sim-replay").invoke([HumanMessage(content="prompt mudou")])
    assert "cassette stale: regrave com --llm record" in (sim_dir / "stale.log").read_text()


def test_stale_without_announced_scenario(sim_dir):
    with pytest.raises(cs.CassetteStale, match="cassette stale"):
        cs.build_sim_llm("sim-replay").invoke([HumanMessage(content="oi")])


def test_record_roundtrip(sim_dir):
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    _announce(sim_dir, nonce="r1")
    msgs = [HumanMessage(content="oi")]
    rec = cs.SimCassetteChatModel(inner=FakeListChatModel(responses=["ola 2026-10-11"]))
    assert rec.invoke(msgs).content == "ola 2026-10-11"
    _announce(sim_dir, nonce="r2")
    assert cs.build_sim_llm("sim-replay").invoke(msgs).content == "ola 2026-10-11"


# ----------------------------------------------------------------- production unaffected
def test_sim_providers_ignored_without_evi_sim(monkeypatch):
    monkeypatch.delenv("EVI_SIM", raising=False)
    monkeypatch.setenv("EVI_BACKGROUND_LLM_PROVIDER", "sim-replay")
    assert llm.background_provider() == "ollama"
    assert not llm._is_sim_provider("sim-replay")
    assert llm.extract_llm_text(["x"], provider="sim-replay") == "['x']"  # default (non-gemini) path
    built = llm.build_llm(provider="sim-replay")
    assert type(built).__name__ == "ChatOllama"  # same as any unknown provider


def test_sim_providers_active_with_evi_sim(monkeypatch):
    monkeypatch.setenv("EVI_SIM", "1")
    monkeypatch.setenv("EVI_BACKGROUND_LLM_PROVIDER", "sim-replay")
    assert llm.background_provider() == "sim-replay"
    assert isinstance(llm.build_llm(provider="sim-replay"), cs.SimCassetteChatModel)
    assert llm.extract_llm_text([{"type": "text", "text": " oi "}], provider="sim-replay") == "oi"
