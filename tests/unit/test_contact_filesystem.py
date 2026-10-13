import json
import os
import sys
import tempfile
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.contact_filesystem import (  # noqa: E402
    append_timeline,
    ensure_contact,
    ingest_commitment,
    sanitize_jid,
)


def test_sanitize_jid():
    assert sanitize_jid("5511999999999@s.whatsapp.net") == "5511999999999@s.whatsapp.net"
    assert " " not in sanitize_jid("bad jid!")


def test_ingest_commitment_writes_timeline():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        jid = "5511999999999@s.whatsapp.net"
        ok = ingest_commitment(
            jid=jid,
            source_id="w001",
            title="Reunião",
            raw_text="amanhã 14h",
            commitment_id=42,
            label="João",
        )
        assert ok
        root = ensure_contact(jid)
        assert (root / "profile.md").is_file()
        lines = (root / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["commitment_id"] == 42
        assert "Reunião" in row["text_preview"]


def test_append_timeline_disabled_without_env():
    old = os.environ.pop("EVI_CONTACT_MEMORY_DIR", None)
    try:
        assert append_timeline("x", source_id="1", text_preview="hi") is False
    finally:
        if old:
            os.environ["EVI_CONTACT_MEMORY_DIR"] = old


def test_scn_mem_15_ensure_contact_refuses_non_direct(tmp_path, monkeypatch):
    import pytest

    from services.contact_filesystem import (
        NotADirectContact,
        list_contact_dirs,
        update_contact_label,
    )

    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    for jid in ("1203@g.us", "1203@newsletter", "status@broadcast"):
        with pytest.raises(NotADirectContact):
            ensure_contact(jid)
        assert append_timeline(jid, source_id="1", text_preview="x") is False
        assert update_contact_label(jid, "x") is False
    assert list_contact_dirs() == []
    # pre-existing directories are left untouched and still listed
    (tmp_path / "contacts" / "old@g.us").mkdir(parents=True)
    assert [p.name for p in list_contact_dirs()] == ["old@g.us"]


if __name__ == "__main__":
    test_sanitize_jid()
    test_ingest_commitment_writes_timeline()
    test_append_timeline_disabled_without_env()
    print("ok")
