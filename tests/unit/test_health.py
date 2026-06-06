import os
import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.health import run_health_checks  # noqa: E402


def test_health_all_skipped_ok():
    with patch.dict(os.environ, {}, clear=True):
        with patch("services.health._check_ollama", return_value={"ok": True, "detail": "skipped"}):
            out = run_health_checks(graph_ready=True)
    assert out["status"] == "ok"
    assert out["checks"]["graph"]["ok"] is True


def test_health_degraded_when_one_fails():
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}, clear=True):
        with patch("services.health._check_postgres", return_value={"ok": False, "detail": "fail"}):
            with patch("services.health._check_ollama", return_value={"ok": True, "detail": "tags ok"}):
                out = run_health_checks(graph_ready=True)
    assert out["status"] == "degraded"


def test_health_route_scn_api_02():
    main_py = _agent / "main.py"
    src = main_py.read_text(encoding="utf-8")
    assert '@app.get("/health")' in src
    assert "run_health_checks" in src


if __name__ == "__main__":
    test_health_all_skipped_ok()
    test_health_degraded_when_one_fails()
    test_health_route_scn_api_02()
    print("ok")
