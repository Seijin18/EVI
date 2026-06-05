import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services.telegram_format import format_for_telegram  # noqa: E402


def test_markdown_link_to_plain():
    text = "Veja [Aqui](https://calendar.google.com/event?eid=abc)"
    out = format_for_telegram(text)
    assert "https://calendar.google.com" in out
    assert "[Aqui]" not in out


if __name__ == "__main__":
    test_markdown_link_to_plain()
    print("ok")
