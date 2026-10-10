"""Token accounting: usage extraction, cost estimate, TurnCollector, KPIs, sim report."""

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, LLMResult  # noqa: E402

import llm_usage  # noqa: E402
from services import turn_log, usage_report  # noqa: E402
from testing.sim import report  # noqa: E402


def _result(tin, tout, reasoning=0):
    details = {"reasoning": reasoning} if reasoning else {}
    msg = AIMessage(
        content="x",
        usage_metadata={"input_tokens": tin, "output_tokens": tout, "total_tokens": tin + tout, "output_token_details": details},
    )
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


def test_extract_usage_with_and_without_metadata():
    assert llm_usage.extract_usage(_result(100, 50, 30)) == (100, 50, 30)
    plain = LLMResult(generations=[[ChatGeneration(message=AIMessage(content="x"))]])
    assert llm_usage.extract_usage(plain) == (0, 0, 0)


def test_estimate_cost_defaults_and_env():
    with patch.dict(os.environ, {}, clear=False):
        for k in ("EVI_LLM_PRICE_IN_USD", "EVI_LLM_PRICE_OUT_USD", "EVI_LLM_USD_BRL"):
            os.environ.pop(k, None)
        usd, brl = llm_usage.estimate_cost(1_000_000, 1_000_000)
    assert usd == pytest.approx(2.80) and brl == pytest.approx(15.4)
    with patch.dict(os.environ, {"EVI_LLM_PRICE_OUT_USD": "1", "EVI_LLM_PRICE_IN_USD": "0", "EVI_LLM_USD_BRL": "2"}):
        assert llm_usage.estimate_cost(10, 1_000_000) == (pytest.approx(1.0), pytest.approx(2.0))


def test_turn_collector_sums_usage():
    c = turn_log.TurnCollector()
    c.on_llm_end(_result(100, 20, 5))
    c.on_llm_end(_result(150, 30))
    assert (c.tokens_in, c.tokens_out) == (250, 50)


def test_turn_logged_with_tokens():
    c = turn_log.TurnCollector()
    c.on_llm_end(_result(7, 3))
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}), patch("db.insert_turn") as ins:
        turn_log.record_turn(session_id="s", channel="api", user_text="u", reply_text="r", collector=c, latency_ms=1)
    assert ins.call_args.kwargs["tokens_in"] == 7 and ins.call_args.kwargs["tokens_out"] == 3


def test_kpis_tokens_and_cost():
    turns = [
        {"is_test": False, "channel": "api", "tokens_in": 1_000_000, "tokens_out": 0, "tools": []},
        {"is_test": False, "channel": "api", "tokens_in": None, "tokens_out": 1_000_000, "tools": []},
        {"is_test": True, "channel": "api", "tokens_in": 9_000_000, "tokens_out": 9_000_000, "tools": []},
    ]
    with patch.dict(os.environ, {}, clear=False):
        for k in ("EVI_LLM_PRICE_IN_USD", "EVI_LLM_PRICE_OUT_USD", "EVI_LLM_USD_BRL"):
            os.environ.pop(k, None)
        k = usage_report.compute_kpis(turns)
    assert k["tokens"] == 2_000_000
    assert k["cost_usd"] == pytest.approx(2.80) and k["cost_brl"] == pytest.approx(15.4)


def test_sim_report_tokens_and_cost(tmp_path):
    res = SimpleNamespace(
        passed=True, failures=[], tools_called=[], steps=[], llm_calls=2, duration_s=1.0,
        tokens_in=1_000_000, tokens_out=100_000, tokens_reasoning=0,
    )
    with patch.dict(os.environ, {}, clear=False):
        for k in ("EVI_SIM_PRICE_IN_USD", "EVI_SIM_PRICE_OUT_USD", "EVI_SIM_USD_BRL"):
            os.environ.pop(k, None)
        rec = report.attempt_record("SIM-X", [], 1, res)
        assert rec["tokens_in"] == 1_000_000 and rec["cost_usd"] == pytest.approx(0.55)
        assert rec["cost_brl"] == pytest.approx(0.55 * 5.5)
        s = report.summarize([rec], 1)
        meta = {"ts": "T", "repeat": 1, "max_llm_calls": 200, "llm_calls": 2, "budget_hit": False}
        assert "LLM: 2 calls, 1000000 in / 100000 out tok" in report.console_summary(s, meta, [rec])
        _, md = report.write_reports([rec], s, meta, tmp_path, "T")
    assert "estimated cost: R$ 3.0" in md.read_text()


PG = os.getenv("DATABASE_URL", "")


@pytest.mark.ephemeral_db
def test_insert_turn_stores_tokens():
    pytest.importorskip("psycopg2")
    import db

    with patch.object(db, "DATABASE_URL", PG):
        db.init_db()
        tid = db.insert_turn(session_id=f"tok-{uuid.uuid4().hex[:6]}", channel="api", user_text="u", tokens_in=11, tokens_out=22)
        row = db.get_turn(tid)
    assert (row["tokens_in"], row["tokens_out"]) == (11, 22)
