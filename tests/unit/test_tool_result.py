"""SCN-TOOL-01 — structured tool outcomes replace substring sniffing."""

import json
import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services import tool_result as tr  # noqa: E402
from services.tool_result import ToolResult, parse_windmill_result  # noqa: E402


# --- the dataclass contract -------------------------------------------------


def test_truthiness_and_str_keep_call_sites_working():
    ok = ToolResult.success("Evento criado.")
    bad = ToolResult.failure("Falha ao agendar.")
    assert bool(ok) is True and bool(bad) is False
    assert str(ok) == "Evento criado."
    assert f"{bad}" == "Falha ao agendar."
    # `if result:` is the shape existing code uses
    assert (ok and "sim") == "sim"


def test_failure_truncates_detail():
    out = ToolResult.failure("x", detail="y" * 900)
    assert len(out.detail) == 500


# --- the sentinels that used to escape --------------------------------------


def test_missing_env_var_is_a_configuration_failure():
    """`Missing WINDMILL_*` contains no "failed" — it slipped through every check."""
    out = parse_windmill_result("Missing WINDMILL_WEBHOOK_CALENDAR", action="agendar")
    assert out.ok is False
    assert out.reason == tr.NOT_CONFIGURED


def test_unknown_operation_is_a_configuration_failure():
    out = parse_windmill_result("Unknown Windmill operation: frobnicate", action="agendar")
    assert out.ok is False
    assert out.reason == tr.NOT_CONFIGURED


def test_transport_failure_is_classified():
    out = parse_windmill_result(
        "Windmill request failed: 500 Server Error", action="listar eventos"
    )
    assert out.ok is False and out.reason == tr.HTTP_ERROR


# --- the four envelopes the scripts actually emit ---------------------------


def test_created_counts_as_success():
    """schedule_event and create_task say "created", not "ok"."""
    raw = json.dumps({"status": "created", "action": "schedule_event", "event_id": "e1"})
    out = parse_windmill_result(raw, action="agendar")
    assert out.ok is True
    assert out.data["event_id"] == "e1"


def test_ok_counts_as_success():
    raw = json.dumps({"status": "ok", "action": "list_tasks", "count": 2, "tasks": []})
    out = parse_windmill_result(raw, action="listar tarefas")
    assert out.ok is True and out.data["count"] == 2


def test_error_with_http_status():
    raw = json.dumps({"status": "error", "http_status": 403, "detail": "forbidden"})
    out = parse_windmill_result(raw, action="agendar")
    assert out.ok is False
    assert out.reason == tr.UPSTREAM_ERROR
    assert "403" in out.message and "forbidden" in out.message


def test_error_with_http_key_from_the_cron_scripts():
    """daily_summary/heartbeat/contact_learn use `http`, not `http_status`."""
    raw = json.dumps({"status": "error", "http": 502, "detail": "bad gateway"})
    out = parse_windmill_result(raw, action="rodar heartbeat")
    assert out.ok is False and "502" in out.message


def test_envelope_without_action_key():
    """list_calendars omits `action` entirely."""
    raw = json.dumps({"status": "ok", "calendars": [{"id": "primary"}]})
    out = parse_windmill_result(raw, action="listar calendários")
    assert out.ok is True and out.data["calendars"][0]["id"] == "primary"


def test_unrecognised_status_is_not_silently_successful():
    """The cron trio's `**body` splat can overwrite status with anything."""
    raw = json.dumps({"status": "failed_partially", "detail": "x"})
    out = parse_windmill_result(raw, action="rodar cron")
    assert out.ok is False and out.reason == tr.UNPARSEABLE


# --- ambiguity that used to reach the model ---------------------------------


def test_unparseable_body_is_a_failure_not_a_shrug():
    out = parse_windmill_result("<html>502 Bad Gateway</html>", action="listar eventos")
    assert out.ok is False
    assert out.reason == tr.UNPARSEABLE


def test_truncated_json_is_unparseable():
    """windmill.py caps the body at 500/2000 chars, which can cut mid-object."""
    raw = json.dumps({"status": "ok", "events": [{"summary": "x" * 100}]})[:120]
    out = parse_windmill_result(raw, action="listar eventos")
    assert out.ok is False and out.reason == tr.UNPARSEABLE


def test_empty_body_is_a_failure():
    assert parse_windmill_result("   ", action="agendar").ok is False


def test_literal_ok_from_empty_2xx_is_success():
    out = parse_windmill_result("ok", action="agendar", fallback_message="Feito.")
    assert out.ok is True and out.message == "Feito."


# --- OAuth hints ------------------------------------------------------------


def test_oauth_hint_wins_over_generic_error(monkeypatch):
    monkeypatch.setenv("WINDMILL_GCAL_RESOURCE", "u/me/gcal")
    out = parse_windmill_result(
        "Windmill failed: error refreshing token",
        action="agendar",
        resource_env="WINDMILL_GCAL_RESOURCE",
    )
    assert out.ok is False
    assert out.reason == tr.OAUTH
    assert "OAuth" in out.message or "credencial" in out.message.lower()


def test_oauth_hint_from_inside_an_error_envelope(monkeypatch):
    monkeypatch.setenv("WINDMILL_GMAIL_RESOURCE", "u/me/gmail")
    raw = json.dumps(
        {"status": "error", "detail": "Resource u/me/gmail not found", "http_status": 404}
    )
    out = parse_windmill_result(
        raw, action="acessar o Gmail", resource_env="WINDMILL_GMAIL_RESOURCE"
    )
    assert out.reason == tr.OAUTH
    assert "Windmill" in out.message


def test_no_resource_env_means_no_oauth_special_casing():
    out = parse_windmill_result(
        json.dumps({"status": "error", "detail": "error refreshing token"}),
        action="agendar",
    )
    assert out.reason == tr.UPSTREAM_ERROR


# --- the regression this whole change exists for ----------------------------


def test_error_detail_mentioning_criada_is_still_a_failure():
    """The `"criad"` substring gated a DB write marking a commitment scheduled."""
    raw = json.dumps(
        {
            "status": "error",
            "http_status": 500,
            "detail": "A tarefa não pôde ser criada: quota exceeded",
        }
    )
    out = parse_windmill_result(raw, action="criar tarefa")
    assert out.ok is False, "an error whose detail says 'criada' must not read as success"
    assert "criad" in out.message.lower()  # the prose still contains the trap word
