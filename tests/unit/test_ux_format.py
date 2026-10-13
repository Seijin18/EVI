"""ux_format: pure pieces of the user-facing item line (SCN-UX-02/03)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services import ux_format as ux  # noqa: E402

TODAY = date(2026, 10, 13)


def test_short_age_day_due():
    assert ux.short_age(0.5) == "agora" and ux.short_age(30) == "ontem" and ux.short_age(130) == "5 d"
    assert ux.short_day(date(2026, 10, 14), TODAY) == "amanhã"
    assert ux.short_due(date(2026, 10, 16), TODAY) == "até sex"
    assert ux.short_due(date(2026, 10, 11), TODAY) == "venceu 11/10"


def test_who_label_never_exposes_raw_jid():
    assert ux.who_label("999000111@lid") == "contato sem nome"
    assert ux.who_label("5511999990000@s.whatsapp.net") == "+5511999990000"
    assert ux.who_label("Eliana") == "Eliana" and ux.who_label(None) == ""


def test_item_line_person_first_skips_empty():
    assert ux.item_line("Eliana", "Mandar a modelagem", "até sex", n=3) == "3. Eliana · Mandar a modelagem · até sex"
    assert ux.item_line("", "Só o assunto") == "Só o assunto"
