"""SCN-USE-08: unseen Evolution payload shapes are captured fully redacted."""

import copy
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services import payload_shapes as ps  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "evolution"
FIXTURES = sorted(FIX.glob("*.json"))


@pytest.fixture(autouse=True)
def _iso(monkeypatch):
    # Own mkdtemp dir (not pytest's tmp_path): concurrent pytest sessions prune each
    # other's numbered basetemp dirs, which made capture() soft-fail to None mid-run.
    shapes = tempfile.mkdtemp(prefix="evi-shapes-")
    monkeypatch.setenv("EVI_PAYLOAD_SHAPES_DIR", str(Path(shapes) / "shapes"))
    monkeypatch.delenv("EVI_PAYLOAD_SHAPES", raising=False)
    ps._known.clear()
    yield
    ps._known.clear()
    shutil.rmtree(shapes, ignore_errors=True)


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def _leaves(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from _leaves(x)
    elif isinstance(v, list):
        for x in v:
            yield from _leaves(x)
    elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
        yield v


def _mutate_text(v):
    if isinstance(v, dict):
        return {k: _mutate_text(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_mutate_text(x) for x in v]
    if isinstance(v, str):
        return "zzz " + v[::-1]
    return v


def _grow_lists(v):
    if isinstance(v, dict):
        return {k: _grow_lists(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_grow_lists(x) for x in v] * 3 if v else v
    return v


@pytest.mark.parametrize("fx", FIXTURES, ids=lambda p: p.name)
def test_signature_stable_across_text_and_list_length(fx):
    d = _load(fx)
    assert ps.signature(d) == ps.signature(_mutate_text(d))
    assert ps.signature(d) == ps.signature(_grow_lists(d))


def test_signature_changes_when_key_added_or_type_changes():
    d = _load(FIXTURES[0])
    e = copy.deepcopy(d)
    e["newKey"] = "x"
    assert ps.signature(d) != ps.signature(e)
    f = copy.deepcopy(d)
    f["event"] = 5
    assert ps.signature(d) != ps.signature(f)


def test_distinct_fixtures_have_distinct_signatures():
    sigs = {ps.signature(_load(p)) for p in FIXTURES}
    assert len(sigs) == len(FIXTURES)


@pytest.mark.parametrize("fx", FIXTURES, ids=lambda p: p.name)
def test_scn_use_08_written_file_has_no_original_values(fx):
    d = _load(fx)
    name = ps.capture(d)
    assert name
    raw = (ps.shapes_dir() / name).read_text(encoding="utf-8")
    rec = json.loads(raw)
    assert set(rec) == {"signature", "first_seen", "event", "redacted"}
    assert rec["signature"] == ps.signature(d)
    for leaf in _leaves(d):
        s = str(leaf)
        if isinstance(leaf, str):
            if s == d.get("event"):  # event name is the one structural identifier kept
                continue
            assert s not in raw or len(s) < 3, s
            for run in re.findall(r"\d{3,}", s):
                assert run not in raw, run
        else:
            if abs(leaf) >= 100:
                assert s not in raw, s
    # redacted values are only placeholders / zeros / bools / nulls
    for leaf in _leaves(rec["redacted"]):
        assert leaf == 0 or (isinstance(leaf, str) and leaf.startswith("<str:"))


def test_second_capture_writes_nothing(tmp_path):
    d = _load(FIXTURES[0])
    assert ps.capture(d)
    before = sorted(p.name for p in ps.shapes_dir().iterdir())
    assert ps.capture(_mutate_text(d)) is None
    ps._known.clear()  # even without the memory cache, the file exists
    assert ps.capture(d) is None
    assert sorted(p.name for p in ps.shapes_dir().iterdir()) == before


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("EVI_PAYLOAD_SHAPES", "0")
    assert ps.capture(_load(FIXTURES[0])) is None
    assert not ps.shapes_dir().exists()


def test_capture_never_raises_on_unwritable_dir(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("EVI_PAYLOAD_SHAPES_DIR", str(blocker / "sub"))
    assert ps.capture(_load(FIXTURES[0])) is None


def test_list_new_shapes_by_first_seen():
    for p in FIXTURES:
        ps.capture(_load(p))
    now = datetime.now(timezone.utc)
    got = ps.list_new_shapes(now - timedelta(days=1), now + timedelta(days=1))
    assert len(got) == len(FIXTURES)
    assert ps.list_new_shapes(now + timedelta(days=1)) == []


def test_webhook_unaffected_when_capture_raises(monkeypatch):
    from fastapi.testclient import TestClient

    import main

    body = _load(FIX / "messages_upsert.json")
    main.app.dependency_overrides[main.verify_api_key] = lambda: None
    try:
        client = TestClient(main.app)
        monkeypatch.setattr(ps, "capture", lambda payload: None)
        base = client.post("/webhooks/evolution", json=body)

        def boom(payload):
            raise RuntimeError("boom")

        monkeypatch.setattr(ps, "capture", boom)
        resp = client.post("/webhooks/evolution", json=body)
    finally:
        main.app.dependency_overrides.clear()
    assert resp.status_code == base.status_code
    assert resp.json() == base.json()
