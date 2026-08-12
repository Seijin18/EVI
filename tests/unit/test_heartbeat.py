"""Unit tests for heartbeat stub."""

import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.daily_summary import read_heartbeat_checklist, run_heartbeat_dry  # noqa: E402


def test_heartbeat_dry_returns_checklist():
    out = run_heartbeat_dry()
    assert "ok" in out
    assert "checklist" in out
    assert "compromissos" in read_heartbeat_checklist().lower()


def _profile(tmp_path, jid: str, heading_date: str | None):
    """Write a contact profile, optionally with a synthesis heading."""
    d = tmp_path / jid.replace("@", "_at_")
    d.mkdir(parents=True, exist_ok=True)
    body = "# Contato\n"
    if heading_date:
        body += f"\n## Síntese ({heading_date}, últimos 7 dias)\nresumo\n"
    (d / "profile.md").write_text(body, encoding="utf-8")
    return d


def test_last_synthesis_date_parses_heading(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    from services import contact_filesystem as cf

    jid = "5511999@s.whatsapp.net"
    d = cf.contact_dir(jid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.md").write_text(
        "# c\n\n## Síntese (2026-06-01, últimos 7 dias)\nx\n"
        "\n## Síntese (2026-08-12, últimos 7 dias)\ny\n",
        encoding="utf-8",
    )
    # Newest wins even when it is not the last heading in the file.
    assert cf.last_synthesis_date(jid) == "2026-08-12"


def test_last_synthesis_date_empty_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    from services import contact_filesystem as cf

    jid = "5511888@s.whatsapp.net"
    d = cf.contact_dir(jid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.md").write_text("# sem sintese\n", encoding="utf-8")
    assert cf.last_synthesis_date(jid) == ""
    assert cf.last_synthesis_date("nao-existe@s.whatsapp.net") == ""


def test_synthesised_contact_is_not_flagged(tmp_path, monkeypatch):
    """SCN-MEM-11 — the old comparison ('2' > '#') flagged this contact too."""
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    from services import heartbeat as hb

    jid = "5511777@s.whatsapp.net"
    monkeypatch.setattr(
        "services.contact_filesystem.collect_known_contacts",
        lambda: [{"jid": jid, "label": "Fulano"}],
    )
    monkeypatch.setattr(
        "services.contact_filesystem.read_timeline_since",
        lambda _jid, **kw: [{"ts": "2026-08-10T10:00:00+00:00"}],
    )
    monkeypatch.setattr(
        "services.contact_filesystem.last_synthesis_date", lambda _jid: "2026-08-12"
    )
    assert hb._contacts_needing_synthesis() == []


def test_contact_with_newer_timeline_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    from services import heartbeat as hb

    jid = "5511777@s.whatsapp.net"
    monkeypatch.setattr(
        "services.contact_filesystem.collect_known_contacts",
        lambda: [{"jid": jid, "label": "Fulano"}],
    )
    monkeypatch.setattr(
        "services.contact_filesystem.read_timeline_since",
        lambda _jid, **kw: [{"ts": "2026-08-13T10:00:00+00:00"}],
    )
    monkeypatch.setattr(
        "services.contact_filesystem.last_synthesis_date", lambda _jid: "2026-08-12"
    )
    assert hb._contacts_needing_synthesis() == ["Fulano"]


def test_contact_without_synthesis_is_flagged(tmp_path, monkeypatch):
    """No heading yields "", and any date > "" — the safe direction."""
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    from services import heartbeat as hb

    monkeypatch.setattr(
        "services.contact_filesystem.collect_known_contacts",
        lambda: [{"jid": "x@s.whatsapp.net", "label": "Sem sintese"}],
    )
    monkeypatch.setattr(
        "services.contact_filesystem.read_timeline_since",
        lambda _jid, **kw: [{"ts": "2026-08-13T10:00:00+00:00"}],
    )
    monkeypatch.setattr("services.contact_filesystem.last_synthesis_date", lambda _jid: "")
    assert hb._contacts_needing_synthesis() == ["Sem sintese"]
