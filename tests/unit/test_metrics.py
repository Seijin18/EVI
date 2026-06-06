from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"


def test_metrics_route_in_main_scn_ops_03():
    src = (_agent / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/metrics")' in src
    assert "PrometheusMiddleware" in src


def test_metrics_module_wiring():
    src = (_agent / "services" / "metrics.py").read_text(encoding="utf-8")
    assert "evi_http_requests_total" in src
    assert "evi_webhook_duration_seconds" in src


if __name__ == "__main__":
    test_metrics_route_in_main_scn_ops_03()
    test_metrics_module_wiring()
    print("ok")
