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


def _val(counter, **labels):
    return counter.labels(**labels)._value.get()


def test_record_turn_increments_and_normalizes(monkeypatch):
    from services import metrics

    monkeypatch.setenv("EVI_METRICS_ENABLED", "true")
    before = _val(metrics.TURNS_TOTAL, channel="telegram", outcome="ok")
    metrics.record_turn("telegram", "ok")
    assert _val(metrics.TURNS_TOTAL, channel="telegram", outcome="ok") == before + 1
    before = _val(metrics.TURNS_TOTAL, channel="other", outcome="other")
    metrics.record_turn("carrier-pigeon", "weird")
    assert _val(metrics.TURNS_TOTAL, channel="other", outcome="other") == before + 1


def test_record_probe_failure_normalizes(monkeypatch):
    from services import metrics

    monkeypatch.setenv("EVI_METRICS_ENABLED", "true")
    before = _val(metrics.PROBE_FAILURES_TOTAL, check="gmail")
    metrics.record_probe_failure("gmail")
    assert _val(metrics.PROBE_FAILURES_TOTAL, check="gmail") == before + 1
    before = _val(metrics.PROBE_FAILURES_TOTAL, check="other")
    metrics.record_probe_failure("nope")
    assert _val(metrics.PROBE_FAILURES_TOTAL, check="other") == before + 1


def test_disabled_does_not_increment(monkeypatch):
    from services import metrics

    monkeypatch.setenv("EVI_METRICS_ENABLED", "false")
    before = _val(metrics.TURNS_TOTAL, channel="api", outcome="error")
    metrics.record_turn("api", "error")
    assert _val(metrics.TURNS_TOTAL, channel="api", outcome="error") == before


def test_exposed_text_contains_metric_names(monkeypatch):
    from services import metrics

    monkeypatch.setenv("EVI_METRICS_ENABLED", "true")
    metrics.record_turn("job", "tool_failed")
    metrics.record_probe_failure("calendar")
    body = metrics.metrics_response().body.decode()
    assert "evi_turns_total" in body
    assert "evi_probe_failures_total" in body


if __name__ == "__main__":
    test_metrics_route_in_main_scn_ops_03()
    test_metrics_module_wiring()
    print("ok")
