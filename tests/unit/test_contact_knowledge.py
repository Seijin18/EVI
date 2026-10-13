"""SCN-MEM-16: structured contact knowledge in profile.md."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from services import contact_filesystem as cf
from services import contact_knowledge as ck

JID = "5511999990000@s.whatsapp.net"
NOTE = "Minha nota: ligar na sexta.\nNunca marcar de manhã — ação é só minha.  "

PROFILE = f"""# Contact memory

- **jid**: {JID}
- **label**: Fê
- **created**: 2026-09-01T10:00:00+00:00

## Fatos
- Trabalha na Unnawave (2026-10-07)
- Prefere ser chamado de Fê (2026-09-30)

## Em aberto
- Usuário vai mandar a modelagem (2026-10-11)

## Notas
{NOTE}
"""


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    return tmp_path


def _profile_path() -> Path:
    return cf.contact_dir(JID) / "profile.md"


def _seed(text: str = PROFILE) -> Path:
    cf.ensure_contact(JID, label="Fê")
    p = _profile_path()
    p.write_text(text, encoding="utf-8")
    return p


def _notes_block(text: str) -> str:
    return text.split("## Notas\n", 1)[1]


def test_scn_mem_16_update_twice(mem):
    p = _seed()
    ck.write_knowledge(JID, [("Mora em Curitiba", "2026-10-12")], [("Enviar contrato", "2026-10-12")])
    ck.write_knowledge(
        JID,
        [("Mora em Recife", "2026-10-13"), ("Gosta de café", "2026-10-13")],
        [],
        updated_at=datetime(2026, 10, 13, 3, 30, tzinfo=timezone.utc),
    )
    text = p.read_text(encoding="utf-8")
    assert text.count("## Fatos") == 1
    assert text.count("## Em aberto") == 1
    assert text.count("## Notas") == 1
    assert _notes_block(text) == NOTE + "\n"
    assert f"- **jid**: {JID}" in text and "- **created**: 2026-09-01" in text

    out = ck.read_contact_knowledge(JID)
    assert "Mora em Recife (2026-10-13)" in out and "Gosta de café" in out
    assert "Curitiba" not in out and "Unnawave" not in out
    assert "jid" not in out and "created" not in out and "# Contact memory" not in out
    assert "knowledge_updated" not in out
    assert "Minha nota: ligar na sexta." in out
    assert out.index("Fatos:") < out.index("Notas:")
    assert ck.read_knowledge(JID).knowledge_updated == datetime(2026, 10, 13, 3, 30, tzinfo=timezone.utc)


def test_legacy_synthesis_preserved(mem):
    legacy = (
        "# Contact memory\n\n- **jid**: x\n- **label**: Y\n- **created**: 2026-01-01\n\n"
        "Stable facts and preferences go here.\n\n"
        "## Síntese (2026-10-01, manual)\n\nTexto antigo com acentuação.\n"
    )
    p = _seed(legacy)
    prof = ck.parse_profile(legacy)
    assert prof.other_sections == [("Síntese (2026-10-01, manual)", "\nTexto antigo com acentuação.")]
    ck.write_knowledge(JID, [("Fato", "2026-10-02")], [])
    text = p.read_text(encoding="utf-8")
    assert "## Síntese (2026-10-01, manual)\n\nTexto antigo com acentuação.\n" in text
    assert "Stable facts and preferences go here." in text
    assert ck.parse_profile(text).other_sections == prof.other_sections
    assert text.index("## Notas") < text.index("## Síntese")
    assert ck.NOTES_PLACEHOLDER in text
    assert ck.read_contact_knowledge(JID) == "Fatos:\n- Fato (2026-10-02)"


def test_caps(mem):
    _seed()
    facts = [(f"fato {i}", f"2026-10-{i:02d}") for i in range(1, 21)]
    facts.append(("sem data", None))
    items = [(f"item {i}", f"2026-10-{i:02d}") for i in range(1, 9)]
    ck.write_knowledge(JID, facts, items)
    prof = ck.read_knowledge(JID)
    assert len(prof.facts) == 15 and len(prof.open_items) == 5
    texts = [f.text for f in prof.facts]
    assert "fato 20" in texts and "fato 6" in texts and "fato 5" not in texts and "sem data" not in texts
    assert [i.text for i in prof.open_items] == [f"item {i}" for i in range(4, 9)]


def test_roundtrip_and_stable_bytes(mem):
    prof = ck.parse_profile(PROFILE)
    rendered = ck.render_profile(prof)
    assert ck.parse_profile(rendered) == prof
    assert ck.render_profile(ck.parse_profile(rendered)) == rendered
    prof.knowledge_updated = datetime(2026, 10, 13, tzinfo=timezone.utc)
    r2 = ck.render_profile(prof)
    assert ck.parse_profile(r2) == prof
    assert ck.render_profile(ck.parse_profile(r2)) == r2
    # rewriting identical knowledge with the same timestamp is byte-identical
    _seed()
    ts = datetime(2026, 10, 13, tzinfo=timezone.utc)
    ck.write_knowledge(JID, [("A", "2026-10-01")], [], updated_at=ts)
    first = _profile_path().read_bytes()
    ck.write_knowledge(JID, [("A", "2026-10-01")], [], updated_at=ts)
    assert _profile_path().read_bytes() == first


def test_undated_lines_and_numbering():
    prof = ck.parse_profile("# H\n\n## Fatos\n- sem data\n- com data (2026-10-01)\n\n## Em aberto\n- pendente\n")
    assert [(f.text, f.date) for f in prof.facts] == [("sem data", None), ("com data", "2026-10-01")]
    facts, items = ck.numbered(prof)
    assert facts == [("F1", "sem data", None), ("F2", "com data", "2026-10-01")]
    assert items == [("A1", "pendente", None)]


def test_atomic_write_failure_leaves_file(mem, monkeypatch):
    p = _seed()
    before = p.read_bytes()

    def boom(src, dst):
        raise OSError("disk")

    monkeypatch.setattr(ck.os, "replace", boom)
    with pytest.raises(OSError):
        ck.write_knowledge(JID, [("x", "2026-10-01")], [])
    assert p.read_bytes() == before
    assert [q.name for q in p.parent.iterdir() if q.name.endswith(".tmp")] == []


def test_unicode_and_crlf(mem):
    crlf = PROFILE.replace("\n", "\r\n")
    prof = ck.parse_profile(crlf)
    assert prof.facts[0].text == "Trabalha na Unnawave"
    assert prof.notes == NOTE
    assert "\r" not in ck.render_profile(prof)
    _seed(crlf)
    ck.write_knowledge(JID, [("Prefere açaí — sem açúcar", "2026-10-13")], [])
    assert "açaí — sem açúcar" in ck.read_contact_knowledge(JID)


def test_read_truncates_on_line_boundary(mem):
    _seed()
    ck.write_knowledge(JID, [(f"fato número {i}", f"2026-10-{i:02d}") for i in range(1, 11)], [("pend", "2026-10-01")])
    out = ck.read_contact_knowledge(JID, max_chars=100)
    assert len(out) <= 100
    assert out.startswith("Fatos:")
    assert all(ln == "Fatos:" or ln.startswith("- fato número") for ln in out.split("\n"))
    assert "Em aberto:" not in out and "Notas:" not in out


def test_read_empty_cases(mem):
    assert ck.read_knowledge(JID) is None
    assert ck.read_contact_knowledge(JID) == ""
    cf.ensure_contact(JID, label="Fê")  # default template, no knowledge, no notes
    assert ck.read_contact_knowledge(JID) == ""


def test_missing_profile_created_with_standard_header(mem):
    assert not cf.contact_dir(JID).exists()
    path = ck.write_knowledge(JID, [("Fato", "2026-10-01")], [])
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Contact memory")
    assert f"- **jid**: {JID}" in text
    assert "## Fatos\n- Fato (2026-10-01)" in text and "## Notas" in text
    assert ck.NOTES_PLACEHOLDER in text


def test_disabled_memory(monkeypatch):
    monkeypatch.delenv("EVI_CONTACT_MEMORY_DIR", raising=False)
    assert ck.write_knowledge(JID, [], []) is None
    assert ck.read_contact_knowledge(JID) == ""
