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
