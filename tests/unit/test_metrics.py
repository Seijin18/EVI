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


def test_briefing_counters_bounded_and_gated(monkeypatch):
    from services import metrics

    monkeypatch.setenv("EVI_METRICS_ENABLED", "true")
    sent = metrics.BRIEFING_SENT_TOTAL.labels(kind="evening", ok="false")._value.get()
    metrics.record_briefing_sent("evening", False)
    assert metrics.BRIEFING_SENT_TOTAL.labels(kind="evening", ok="false")._value.get() == sent + 1
    other = metrics.BRIEFING_REPLIED_TOTAL.labels(kind="other")._value.get()
    metrics.record_briefing_replied("bogus")
    assert metrics.BRIEFING_REPLIED_TOTAL.labels(kind="other")._value.get() == other + 1
    monkeypatch.setenv("EVI_METRICS_ENABLED", "false")
    metrics.record_briefing_replied("bogus")
    assert metrics.BRIEFING_REPLIED_TOTAL.labels(kind="other")._value.get() == other + 1


def test_reminder_metrics_increment_bounded_and_gated(monkeypatch):
    from services import metrics

    monkeypatch.setenv("EVI_METRICS_ENABLED", "true")
    on_time = metrics.REMINDERS_FIRED_TOTAL.labels(late="false")._value.get()
    late = metrics.REMINDERS_FIRED_TOTAL.labels(late="true")._value.get()
    count = metrics.REMINDER_DRIFT_SECONDS.collect()[0].samples
    n0 = next(x.value for x in count if x.name.endswith("_count"))
    metrics.record_reminder_fired(False, 2.0)
    metrics.record_reminder_fired(True, 400.0)
    metrics.record_reminder_fired(False, -3.0)  # clock skew clamps to 0
    assert metrics.REMINDERS_FIRED_TOTAL.labels(late="false")._value.get() == on_time + 2
    assert metrics.REMINDERS_FIRED_TOTAL.labels(late="true")._value.get() == late + 1
    samples = metrics.REMINDER_DRIFT_SECONDS.collect()[0].samples
    assert next(x.value for x in samples if x.name.endswith("_count")) == n0 + 3
    # only the two bounded label values ever exist
    labels = {s.labels.get("late") for s in metrics.REMINDERS_FIRED_TOTAL.collect()[0].samples}
    assert labels <= {"true", "false", None}
    # buckets resolve 0-3600 s: 5 min and 1 h are bucket edges
    les = {float(s.labels["le"]) for s in samples if s.name.endswith("_bucket")}
    assert {1.0, 60.0, 300.0, 3600.0} <= les
    body = metrics.metrics_response().body.decode()
    assert "evi_reminders_fired_total" in body and "evi_reminder_drift_seconds" in body
    monkeypatch.setenv("EVI_METRICS_ENABLED", "false")
    metrics.record_reminder_fired(True, 10.0)
    assert metrics.REMINDERS_FIRED_TOTAL.labels(late="true")._value.get() == late + 1


if __name__ == "__main__":
    test_metrics_route_in_main_scn_ops_03()
    test_metrics_module_wiring()
    print("ok")
