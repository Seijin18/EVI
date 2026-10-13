"""contact_learn_cron: daily knowledge batch over contact dirs (SCN-MEM-19)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from services import contact_filesystem as cf
from services import contact_knowledge as ck
from services import contact_learn_cron as cron

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _mem(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("EVI_CONTACT_LEARN_LIMIT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def jid_of(i):
    return f"55110000{i:04d}@s.whatsapp.net"


def timeline(jid, ts):
    cf.append_timeline(jid, source_id=f"s{ts.timestamp()}", text_preview="oi", ts=ts.isoformat())


def stamp(jid, ts):
    ck.write_knowledge(jid, [], [], updated_at=ts)


def spy(monkeypatch, results=None):
    calls = []

    def fake(jid):
        calls.append(jid)
        r = (results or {}).get(jid, {"status": "ok"})
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(ck, "update_contact_knowledge", fake)
    return calls


def test_scn_mem_19_top_15_of_20_and_untouched_rest(monkeypatch):
    active = []
    for i in range(20):  # i larger = more recent
        j = jid_of(i)
        timeline(j, NOW - timedelta(hours=100 - i))
        stamp(j, NOW - timedelta(days=30))
        active.append(j)
    quiet = []
    for i in range(20, 25):
        j = jid_of(i)
        timeline(j, NOW - timedelta(days=3))
        stamp(j, NOW)
        quiet.append(j)
    calls = spy(monkeypatch)
    out = cron.run_contact_learn_batch()
    assert out["updated"] == 15 and out["errors"] == 0
    assert calls == list(reversed(active))[:15]
    assert not set(calls) & set(quiet)


def test_absent_knowledge_counts_and_limit_env(monkeypatch):
    j = jid_of(1)
    timeline(j, NOW)
    monkeypatch.setenv("EVI_CONTACT_LEARN_LIMIT", "1")
    timeline(jid_of(2), NOW - timedelta(days=1))
    calls = spy(monkeypatch)
    assert cron.run_contact_learn_batch()["updated"] == 1
    assert calls == [j]


def test_groups_merged_and_no_timeline_skipped(monkeypatch, tmp_path):
    (tmp_path / "contacts" / "5511@g.us").mkdir(parents=True)
    (tmp_path / "contacts" / "5511@g.us" / "timeline.jsonl").write_text(
        json.dumps({"ts": NOW.isoformat()}) + "\n"
    )
    merged = tmp_path / "contacts" / "x@lid.merged-1"
    merged.mkdir(parents=True)
    (merged / "timeline.jsonl").write_text(json.dumps({"ts": NOW.isoformat()}) + "\n")
    cf.ensure_contact(jid_of(3))  # dir without timeline
    calls = spy(monkeypatch)
    out = cron.run_contact_learn_batch()
    assert calls == [] and out["updated"] == 0


def test_soft_fail_and_counts_no_retry(monkeypatch):
    ids = [jid_of(i) for i in range(4)]
    for i, j in enumerate(ids):
        timeline(j, NOW - timedelta(hours=i))
    calls = spy(
        monkeypatch,
        {ids[0]: RuntimeError("boom"), ids[1]: {"status": "no-answer"}, ids[2]: {"status": "no-messages"}},
    )
    out = cron.run_contact_learn_batch()
    assert out["errors"] == 1 and out["no_answer"] == 1 and out["skipped"] == 1 and out["updated"] == 1
    assert sorted(calls) == sorted(ids)  # each attempted exactly once


def test_disabled_without_memory_dir(monkeypatch):
    monkeypatch.delenv("EVI_CONTACT_MEMORY_DIR")
    assert cron.run_contact_learn_batch()["skipped"] is True
