"""SCN-CI-02/03 — the container smoke's assertions, verified without Docker."""

import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from testing.container_checks import (  # noqa: E402
    check_boot_logs,
    check_health_payload,
    check_path_constants,
    check_port_bindings,
    check_tools_payload,
)

# --- the two regressions this exists for ------------------------------------


def test_rejects_repo_root_of_slash():
    """dev_bridge._REPO_ROOT resolved to "/" in the image for six weeks."""
    problems = check_path_constants({"services.dev_bridge._REPO_ROOT": Path("/")})
    assert problems
    assert "overshot" in problems[0]


def test_rejects_failing_check_even_when_aggregate_is_ok():
    """The Qdrant 401 read as `"status": "ok"` because the rule was `< 500`."""
    payload = {
        "status": "ok",
        "checks": {
            "postgres": {"ok": True, "detail": "connected"},
            "qdrant": {"ok": False, "detail": "http 401 (auth required...)"},
        },
    }
    problems = check_health_payload(payload)
    assert problems
    assert any("qdrant" in p for p in problems)


# --- health -----------------------------------------------------------------


def test_healthy_payload_has_no_problems():
    payload = {
        "status": "ok",
        "checks": {
            "graph": {"ok": True, "detail": "initialized"},
            "postgres": {"ok": True, "detail": "connected"},
            "windmill": {"ok": True, "detail": "skipped (no windmill url)"},
        },
    }
    assert check_health_payload(payload) == []


def test_skipped_checks_are_tolerated():
    payload = {
        "status": "ok",
        "checks": {"ollama": {"ok": False, "detail": "skipped (EVI_*_PROVIDER not ollama)"}},
    }
    assert check_health_payload(payload) == []


def test_down_aggregate_is_a_problem():
    payload = {"status": "down", "checks": {"postgres": {"ok": False, "detail": "refused"}}}
    problems = check_health_payload(payload)
    assert any("down" in p for p in problems)


def test_missing_checks_is_a_problem():
    assert check_health_payload({"status": "ok"})


# --- tools ------------------------------------------------------------------


def test_missing_tool_is_reported():
    payload = {"tools": ["schedule_event", "summarize_inbox"]}
    problems = check_tools_payload(payload, expected=["schedule_event", "list_tasks"])
    assert problems and "list_tasks" in problems[0]


def test_full_registry_passes():
    payload = {"tools": ["a", "b", "c"]}
    assert check_tools_payload(payload, expected=["a", "b"]) == []


def test_non_list_tools_is_reported():
    assert check_tools_payload({"tools": None}, expected=[])


# --- ports ------------------------------------------------------------------


def test_data_service_on_all_interfaces_is_rejected():
    config = {
        "services": {
            "postgres": {"ports": [{"published": "5433", "host_ip": "0.0.0.0"}]},
        }
    }
    problems = check_port_bindings(config, data_services=["postgres"])
    assert problems and "5433" in problems[0]


def test_missing_host_ip_is_rejected():
    config = {"services": {"qdrant": {"ports": [{"published": "6333"}]}}}
    assert check_port_bindings(config, data_services=["qdrant"])


def test_localhost_bound_service_passes():
    config = {
        "services": {
            "postgres": {"ports": [{"published": "5433", "host_ip": "127.0.0.1"}]},
            "qdrant": {"ports": [{"published": "6333", "host_ip": "127.0.0.1"}]},
        }
    }
    assert check_port_bindings(config, data_services=["postgres", "qdrant"]) == []


def test_absent_service_is_not_asserted():
    """neo4j lives behind a profile — absence is not a failure."""
    assert check_port_bindings({"services": {}}, data_services=["neo4j"]) == []


# --- path constants ---------------------------------------------------------


def test_existing_path_passes(tmp_path):
    assert check_path_constants({"mod._APP_DIR": tmp_path}) == []


def test_nonexistent_path_is_reported(tmp_path):
    problems = check_path_constants({"mod._X_DIR": tmp_path / "nope"})
    assert problems and "does not exist" in problems[0]


def test_reports_every_offender(tmp_path):
    problems = check_path_constants(
        {"a._ROOT": Path("/"), "b._DIR": tmp_path / "missing", "c._DIR": tmp_path}
    )
    assert len(problems) == 2


# --- boot logs --------------------------------------------------------------


def test_soft_fail_during_boot_is_reported():
    logs = "INFO started\nWARNING soft-fail main.lifespan.init_db: OperationalError: x\n"
    problems = check_boot_logs(logs)
    assert problems and "init_db" in problems[0]


def test_traceback_during_boot_is_reported():
    assert check_boot_logs("Traceback (most recent call last):\n  File ...\n")


def test_clean_boot_has_no_problems():
    assert check_boot_logs("INFO: Application startup complete.\nINFO: Uvicorn running\n") == []


def test_not_started_dependency_is_reported_not_fatal(capsys):
    """Windmill/Ollama are deliberately absent from the smoke stack."""
    payload = {
        "status": "degraded",
        "checks": {
            "postgres": {"ok": True, "detail": "connected"},
            "windmill": {"ok": False, "detail": "name resolution failed"},
        },
    }
    assert check_health_payload(payload, not_started=("windmill",)) == []
    assert "windmill" in capsys.readouterr().out


def test_not_started_does_not_excuse_other_checks():
    payload = {
        "status": "degraded",
        "checks": {
            "qdrant": {"ok": False, "detail": "http 401"},
            "windmill": {"ok": False, "detail": "down"},
        },
    }
    problems = check_health_payload(payload, not_started=("windmill",))
    assert len(problems) == 1 and "qdrant" in problems[0]
