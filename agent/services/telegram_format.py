"""Format assistant text for Telegram (plain URLs, no broken markdown)."""

from __future__ import annotations

import re

_MD_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
_BARE_MD = re.compile(r"\[([^\]]*)\]\(\s*\)")


def format_for_telegram(text: str) -> str:
    """Convert [label](url) to 'label: url' and drop empty markdown links."""
    out = _MD_LINK.sub(r"\1: \2", text)
    out = _BARE_MD.sub(r"\1", out)
    return out.strip()
