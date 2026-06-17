"""Unit tests for llm.extract_llm_text (provider-specific content normalization)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from llm import extract_llm_text  # noqa: E402


def test_default_provider_plain_string():
    assert extract_llm_text("  Olá!  ", provider="ollama") == "Olá!"


def test_default_provider_does_not_parse_list_blocks():
    content = [{"type": "text", "text": "hidden"}]
    assert extract_llm_text(content, provider="ollama") == str(content)


def test_gemini_content_blocks():
    content = [
        {
            "type": "text",
            "text": "Olá! Como posso ajudar?",
            "extras": {"signature": "abc"},
        }
    ]
    assert extract_llm_text(content, provider="gemini") == "Olá! Como posso ajudar?"


def test_gemini_respects_env_provider(monkeypatch):
    monkeypatch.setenv("EVI_LLM_PROVIDER", "gemini")
    content = [{"type": "text", "text": "ok"}]
    assert extract_llm_text(content) == "ok"


def test_none_and_empty():
    assert extract_llm_text(None, provider="gemini") == ""
    assert extract_llm_text([], provider="gemini") == ""


if __name__ == "__main__":
    test_default_provider_plain_string()
    test_default_provider_does_not_parse_list_blocks()
    test_gemini_content_blocks()
    test_none_and_empty()
    print("ok")
