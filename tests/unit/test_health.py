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


def _wa_env(**extra):
    return patch.dict(os.environ, {"EVOLUTION_API_KEY": "k", **extra}, clear=True)


def _health_with_state(state, **extra):
    with _wa_env(**extra):
        with patch("services.health._check_ollama", return_value={"ok": True, "detail": "tags ok"}):
            with patch("messaging.evolution.EvolutionClient.connection_state", return_value=state):
                return run_health_checks(graph_ready=True)


def test_scn_rel_04_whatsapp_close_is_degraded():
    out = _health_with_state("close")
    assert out["checks"]["whatsapp"] == {"ok": False, "detail": "close"}
    assert out["status"] == "degraded"


def test_whatsapp_open_is_ok():
    out = _health_with_state("open")
    assert out["checks"]["whatsapp"]["ok"] is True
    assert out["status"] == "ok"


def test_whatsapp_unreachable_is_not_ok_but_never_down():
    out = _health_with_state(None)
    assert out["checks"]["whatsapp"] == {"ok": False, "detail": "unreachable"}
    assert out["status"] == "degraded"


def test_whatsapp_skipped_when_flag_off_or_unconfigured():
    out = _health_with_state("close", EVI_SOURCE_ALERTS_ENABLED="false")
    assert out["checks"]["whatsapp"]["detail"].startswith("skipped")
    assert out["status"] == "ok"
    with patch.dict(os.environ, {}, clear=True):
        with patch("services.health._check_ollama", return_value={"ok": True, "detail": "tags ok"}):
            out = run_health_checks(graph_ready=True)
    assert out["checks"]["whatsapp"]["detail"].startswith("skipped")


def test_whatsapp_records_source_status():
    rec = []
    with patch("db.record_source", lambda *a, **k: rec.append(a)):
        _health_with_state("close", DATABASE_URL="postgresql://x")
    assert rec == [("whatsapp", False, "disconnected")]


def test_connection_state_parses_and_never_raises():
    import io
    from messaging.evolution import EvolutionClient

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=R(b'{"instance":{"instanceName":"evi","state":"Open"}}')):
        assert EvolutionClient().connection_state() == "open"
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        assert EvolutionClient().connection_state() is None
    with patch("urllib.request.urlopen", return_value=R(b"not json")):
        assert EvolutionClient().connection_state() is None


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
