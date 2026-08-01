import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.message_sources import IncomingMessage  # noqa: E402
from services.whatsapp_llm_extract import (  # noqa: E402
    extract_commitment_with_fallback,
    llm_extract_enabled,
    try_llm_extract,
)
from services.whatsapp_processor import extract_commitment  # noqa: E402

W005 = IncomingMessage(
    id="w005",
    sender="Ana",
    text="Preciso marcar consulta com dentista dia 12 às 10h",
    ts="2026-06-03T11:00:00",
)

# Heuristic date/time patterns improved after this test was written (W005 is
# now caught by the heuristic itself — see test_llm_extract_w005_scn_wa_16).
# This message has no date/time cues at all, so it still defeats the
# heuristic and exercises the LLM-fallback path.
W006_NO_DATE_CUES = IncomingMessage(
    id="w006",
    sender="Ana",
    text="Aquele assunto que a gente comentou ontem ainda está de pé?",
    ts="2026-06-03T11:00:00",
)


def test_heuristic_misses_w006():
    assert extract_commitment(W006_NO_DATE_CUES) is None


def test_llm_extract_w005_scn_wa_16():
    mock_json = json.dumps(
        {
            "type": "event",
            "title": "Consulta com dentista",
            "date": "2026-06-12",
            "time": "10:00",
            "due": None,
            "confidence": 0.85,
        }
    )

    with patch.dict(os.environ, {"EVI_WHATSAPP_LLM_EXTRACT": "true"}):
        c = try_llm_extract(W005, invoke=lambda _p: mock_json)

    assert c is not None
    assert c.type == "event"
    assert "dentista" in c.title.lower()
    assert c.date == "2026-06-12"
    assert c.time == "10:00"


def test_fallback_uses_llm_when_heuristic_fails():
    mock_json = json.dumps(
        {
            "type": "task",
            "title": "Assunto pendente com Ana",
            "date": None,
            "time": None,
            "confidence": 0.7,
        }
    )

    with patch.dict(os.environ, {"EVI_WHATSAPP_LLM_EXTRACT": "true"}):
        c, method = extract_commitment_with_fallback(
            W006_NO_DATE_CUES, invoke=lambda _p: mock_json
        )

    assert method == "llm"
    assert c is not None
    assert c.source_id == "w006"


def test_llm_disabled_by_default():
    assert not llm_extract_enabled()
    assert try_llm_extract(W005, invoke=lambda _p: "{}") is None


if __name__ == "__main__":
    test_heuristic_misses_w006()
    test_llm_extract_w005_scn_wa_16()
    test_fallback_uses_llm_when_heuristic_fails()
    test_llm_disabled_by_default()
    print("ok")
