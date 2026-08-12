"""SCN-MEM-12/13 — address-book import and the Brazilian ninth-digit match."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.vcard_import import (  # noqa: E402
    build_registry_index,
    import_vcard,
    match_key,
    parse_vcards,
)

_V3 = """BEGIN:VCARD
VERSION:3.0
FN:Pedro Unna
TEL;TYPE=CELL:+55 11 98765-4321
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Sara Lima
TEL;TYPE=CELL:(11) 91234-5678
TEL;TYPE=HOME:1133334444
END:VCARD
"""


# --- parsing ----------------------------------------------------------------


def test_parses_name_and_phones():
    cards = parse_vcards(_V3)
    assert [c.name for c in cards] == ["Pedro Unna", "Sara Lima"]
    assert len(cards[1].phones) == 2


def test_falls_back_to_the_n_property():
    text = "BEGIN:VCARD\nVERSION:2.1\nN:Silva;João;;;\nTEL:11999998888\nEND:VCARD\n"
    assert parse_vcards(text)[0].name == "João Silva"


def test_fn_wins_over_n():
    text = (
        "BEGIN:VCARD\nN:Silva;João;;;\nFN:Joãozinho\nTEL:11999998888\nEND:VCARD\n"
    )
    assert parse_vcards(text)[0].name == "Joãozinho"


def test_handles_folded_lines():
    text = "BEGIN:VCARD\nFN:Nome Muito\n  Comprido\nTEL:11999998888\nEND:VCARD\n"
    assert parse_vcards(text)[0].name == "Nome Muito Comprido"


def test_handles_quoted_printable():
    """Android 2.1 exports accents this way."""
    text = (
        "BEGIN:VCARD\nVERSION:2.1\n"
        "FN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:Jo=C3=A3o\n"
        "TEL:11999998888\nEND:VCARD\n"
    )
    assert parse_vcards(text)[0].name == "João"


def test_malformed_card_does_not_break_the_rest():
    """The junk card carries neither name nor phone, so it is correctly dropped;
    what matters is that the two valid cards after it still parse."""
    text = "BEGIN:VCARD\nlixo sem dois pontos\nEND:VCARD\n" + _V3
    names = [c.name for c in parse_vcards(text)]
    assert names == ["Pedro Unna", "Sara Lima"]


def test_empty_input():
    assert parse_vcards("") == []


# --- the ninth-digit match --------------------------------------------------


def test_same_key_with_and_without_the_ninth_digit():
    """The whole reason this is not a string comparison."""
    assert match_key("5511987654321") == match_key("551187654321")


def test_formatting_is_irrelevant():
    assert match_key("+55 (11) 98765-4321") == match_key("5511987654321")


def test_country_code_optional():
    assert match_key("11987654321") == match_key("+5511987654321")


def test_key_includes_the_ddd():
    """Two people can share the last 8 digits in different area codes."""
    assert match_key("5511987654321") != match_key("5521987654321")


def test_too_short_is_rejected():
    assert match_key("1234") == ""
    assert match_key("") == ""


def test_jid_and_phone_agree():
    assert match_key("5511987654321@s.whatsapp.net") == match_key("(11) 98765-4321")


# --- registry index ---------------------------------------------------------


def test_index_ignores_groups_and_newsletters():
    rows = [
        {"jid": "5511987654321@s.whatsapp.net"},
        {"jid": "120363@g.us"},
        {"jid": "12345@newsletter"},
        {"jid": "999@lid"},
    ]
    index = build_registry_index(rows)
    assert len(index) == 1


# --- import -----------------------------------------------------------------


@pytest.fixture
def vcf(tmp_path):
    p = tmp_path / "agenda.vcf"
    p.write_text(_V3, encoding="utf-8")
    return p


_REGISTRY = [
    {
        "jid": "5511987654321@s.whatsapp.net",
        "display_name": None,
        "whatsapp_label": "PNFagundes",
    },
    {
        "jid": "5511912345678@s.whatsapp.net",
        "display_name": None,
        "whatsapp_label": "Sara~",
    },
]


def _run(vcf, registry=_REGISTRY, **kw):
    with patch("db.list_whatsapp_contacts_db", return_value=registry), patch(
        "db.upsert_whatsapp_contact"
    ) as up:
        report = import_vcard(vcf, **kw)
    return report, up


def test_dry_run_writes_nothing(vcf):
    report, up = _run(vcf, dry_run=True)
    assert report.matched == 2 and report.updated == 2
    up.assert_not_called()
    assert "simulação" in report.summary()


def test_apply_writes_and_keeps_the_old_label_as_alias(vcf):
    report, up = _run(vcf, dry_run=False)
    assert report.updated == 2 and up.call_count == 2
    kwargs = up.call_args_list[0].kwargs
    assert kwargs["display_name"] == "Pedro Unna"
    assert kwargs["aliases"] == ["PNFagundes"], "search by the old name must keep working"


def test_matches_across_the_ninth_digit(tmp_path):
    """The registry holds 13 digits; the vCard holds the 8-digit form."""
    p = tmp_path / "a.vcf"
    p.write_text(
        "BEGIN:VCARD\nFN:Pedro Unna\nTEL:(11) 8765-4321\nEND:VCARD\n", encoding="utf-8"
    )
    report, up = _run(p, dry_run=False)
    assert report.matched == 1 and up.call_count == 1


def test_unmatched_contacts_are_counted_not_invented(tmp_path):
    p = tmp_path / "a.vcf"
    p.write_text("BEGIN:VCARD\nFN:Desconhecido\nTEL:11900000000\nEND:VCARD\n")
    report, up = _run(p, dry_run=False)
    assert report.unmatched == 1 and report.matched == 0
    up.assert_not_called()


def test_ambiguous_match_is_skipped(tmp_path):
    """Two JIDs on one key: label neither rather than guess."""
    registry = [
        {"jid": "5511987654321@s.whatsapp.net", "display_name": None},
        {"jid": "551187654321@s.whatsapp.net", "display_name": None},
    ]
    p = tmp_path / "a.vcf"
    p.write_text("BEGIN:VCARD\nFN:Alguém\nTEL:11987654321\nEND:VCARD\n")
    report, up = _run(p, registry=registry, dry_run=False)
    assert report.ambiguous == 1
    up.assert_not_called()


def test_already_correct_name_is_not_rewritten(tmp_path):
    registry = [
        {
            "jid": "5511987654321@s.whatsapp.net",
            "display_name": "Pedro Unna",
            "whatsapp_label": "PNFagundes",
        }
    ]
    p = tmp_path / "a.vcf"
    p.write_text("BEGIN:VCARD\nFN:Pedro Unna\nTEL:11987654321\nEND:VCARD\n")
    report, up = _run(p, registry=registry, dry_run=False)
    assert report.unchanged == 1 and report.updated == 0
    up.assert_not_called()


def test_entry_without_a_phone_is_skipped(tmp_path):
    p = tmp_path / "a.vcf"
    p.write_text("BEGIN:VCARD\nFN:Só Nome\nEND:VCARD\n")
    report, _ = _run(p)
    assert report.skipped_no_phone == 1


def test_missing_file_is_reported_not_raised(tmp_path):
    report, up = _run(tmp_path / "nao-existe.vcf")
    assert report.parsed == 0
    up.assert_not_called()
    assert "não encontrado" in report.summary()
