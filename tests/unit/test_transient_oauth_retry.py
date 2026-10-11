"""A Google token can expire seconds before Windmill refreshes it: retry once."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services.tool_result import ToolResult  # noqa: E402


def test_probe_retries_a_failed_check_once():
    from services import probe

    calls = []

    def flaky(day):
        calls.append(day)
        if len(calls) == 1:
            return ToolResult.failure("401", reason="upstream_error", detail="401")
        return ToolResult.success("ok")

    with patch.object(probe, "_CHECKS", [("gmail", flaky)]), patch.object(
        probe.db, "insert_probe"
    ), patch.object(probe, "_notify", return_value=False) as notify:
        out = probe.run_probe()
    assert len(calls) == 2
    assert out["checks"]["gmail"]["ok"] is True
    notify.assert_not_called()


def test_briefing_source_retries_once_on_upstream_error():
    from services import briefing

    bad = json.dumps({"status": "error", "error": "401 invalid credentials"})
    good = json.dumps({"status": "ok", "messages": []})
    integ = MagicMock()
    integ.post.side_effect = [bad, good]
    outs = [
        ToolResult.failure("x", reason="upstream_error", detail="401"),
        ToolResult.success("ok", data={"messages": []}),
    ]
    with patch.object(briefing, "get_integration", return_value=integ), patch.object(
        briefing, "parse_windmill_result", side_effect=outs
    ):
        data = briefing._call("summarize_inbox", {}, action="a", env="E", timeout=1)
    assert integ.post.call_count == 2
    assert data == {"messages": []}


def test_windmill_wait_result_body_is_not_cut_at_2000_chars():
    from integrations import windmill

    body = json.dumps({"status": "ok", "messages": [{"id": str(i), "subject": "x" * 200} for i in range(30)]})
    assert len(body) > 2000
    resp = MagicMock(text=body)
    resp.raise_for_status = MagicMock()
    with patch.object(windmill.requests, "post", return_value=resp), patch.dict(
        os.environ, {"WINDMILL_WEBHOOK_EMAIL": "http://w/api/w/evi/jobs/run/p/f/integrations/summarize_inbox"}
    ):
        out = windmill._windmill_post("WINDMILL_WEBHOOK_EMAIL", {}, "", timeout=1, wait_result=True)
    assert json.loads(out)["messages"][-1]["id"] == "29"
