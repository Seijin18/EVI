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


def test_qdrant_auth_failure_is_not_healthy(monkeypatch):
    """401/403 means reachable but unusable — RAG is broken, so not ok.

    Regression guard: `QDRANT__SERVICE__API_KEY=` (empty) makes Qdrant enable
    auth with an empty key and 401 everything, which the old `< 500` rule
    reported as healthy.
    """
    import httpx

    from services.health import _check_qdrant

    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)

    class _Resp:
        status_code = 401

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    out = _check_qdrant()
    assert out["ok"] is False
    assert "401" in out["detail"]


def test_qdrant_ok_without_auth(monkeypatch):
    import httpx

    from services.health import _check_qdrant

    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)

    class _Resp:
        status_code = 200

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    assert _check_qdrant()["ok"] is True
