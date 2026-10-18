"""Message timeline: SCN-MEM-14 (fromMe), SCN-MEM-15 (no dirs for channels)."""

import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.contact_filesystem import read_timeline_tail  # noqa: E402
from services.message_sources import IncomingMessage  # noqa: E402
from services.message_timeline import record_whatsapp_message  # noqa: E402

DIRECT = "5511988887777@s.whatsapp.net"


def _msg(jid=DIRECT, text="oi", from_me=False, mid="m1", **kw):
    return IncomingMessage(id=mid, sender=jid, text=text, ts="2026-06-03T10:00:00+00:00",
                           from_me=from_me, **kw)


def test_from_me_preview_and_dedupe(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    m = _msg(from_me=True, text="te mando a modelagem")
    assert record_whatsapp_message(m) is True
    assert record_whatsapp_message(m) is False
    rows = read_timeline_tail(DIRECT, limit=10)
    assert [r["text_preview"] for r in rows] == ["[eu] te mando a modelagem"]


def test_evi_echo_not_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    assert record_whatsapp_message(_msg(from_me=True, text="[EVI] ok")) is False
    assert read_timeline_tail(DIRECT, limit=10) == []


def test_scn_mem_15_newsletter_creates_no_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    assert record_whatsapp_message(_msg(jid="120363@newsletter", text="novidade")) is False
    assert record_whatsapp_message(_msg(jid="status@broadcast", text="x")) is False
    assert not (tmp_path / "contacts").exists() or not list((tmp_path / "contacts").iterdir())


# --- recent_rows (SCN-WA-RECENT-01) ------------------------------------------------------

import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


def _write_tl(root, jid, rows):
    d = root / "contacts" / jid
    d.mkdir(parents=True)
    (d / "timeline.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def _ago(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def test_recent_rows_shape_period_dedupe_and_coverage(tmp_path, monkeypatch):
    from services.message_timeline import recent_rows

    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    a, b, old = "5511900000001@s.whatsapp.net", "5511900000002@s.whatsapp.net", "5511900000003@s.whatsapp.net"
    _write_tl(tmp_path, a, [
        {"ts": _ago(days=9), "source_id": "o1", "text_preview": "[Ana] antiga"},
        {"ts": _ago(hours=3), "source_id": "m1", "text_preview": "[Ana] oi tudo bem"},
        {"ts": _ago(hours=2), "source_id": "m2", "text_preview": "[eu] tudo sim"},
        {"ts": _ago(hours=1), "source_id": "m2", "commitment_id": 7, "text_preview": "Tarefa: tudo sim"},
        {"ts": _ago(hours=1), "source_id": "m9", "text_preview": "[grupo] [Ana] msg de grupo"},
    ])
    _write_tl(tmp_path, b, [{"ts": _ago(minutes=30), "source_id": "b1", "text_preview": "[Beto] e aí"}])
    _write_tl(tmp_path, old, [{"ts": _ago(days=5), "source_id": "x", "text_preview": "[Cris] velha"}])
    (tmp_path / "contacts" / "5511900000004@s.whatsapp.net.merged-1").mkdir()

    covered: set[str] = set()
    rows = recent_rows(1, 50, covered=covered)
    assert covered == {a, b}
    assert [r["message_id"] for r in rows] == ["b1", "m2", "m1"]  # newest first, no dup, no group
    me = rows[1]
    assert me["from_me"] is True and me["text"] == "tudo sim" and me["preview"].startswith("[eu] ")
    assert rows[0]["from_me"] is False and rows[0]["text"] == "e aí"
    assert rows[0]["chat_jid"] == b and rows[0]["chat_label"] == "Beto"
    assert {"ts", "ts_dt", "chat_phone", "participant", "sender_label"} <= set(rows[0])
    assert len(recent_rows(1, 2)) == 2
    assert {r["chat_jid"] for r in recent_rows(7, 50)} == {a, b, old}


def test_recent_rows_reads_backwards_and_survives_backfill(tmp_path, monkeypatch):
    from services.message_timeline import recent_rows

    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    jid = "5511900000009@s.whatsapp.net"
    filler = [{"ts": _ago(days=20, minutes=i), "source_id": f"f{i}", "text_preview": "x" * 400}
              for i in range(400)]  # > 64 KB of old rows
    rows = filler + [
        {"ts": _ago(hours=2), "source_id": "n1", "text_preview": "[Zé] nova"},
        {"ts": _ago(days=15), "source_id": "bf", "text_preview": "[Zé] backfill", "backfill": True},
        {"ts": _ago(hours=1), "source_id": "n2", "text_preview": "[Zé] mais nova"},
    ]
    _write_tl(tmp_path, jid, rows)
    out = recent_rows(1, 10)
    assert [r["message_id"] for r in out] == ["n2", "n1"]


def test_recent_rows_empty_store(tmp_path, monkeypatch):
    from services.message_timeline import recent_rows

    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    covered: set[str] = set()
    assert recent_rows(1, 10, covered=covered) == [] and covered == set()
