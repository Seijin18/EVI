"""transcribe(): content-part shape, text cleanup, every failure reason (SCN-VOICE-03/04)."""

import base64
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

import llm
from services import transcribe as tr


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EVI_VOICE_ENABLED", "true")
    monkeypatch.setenv("EVI_LLM_PROVIDER", "gemini")
    monkeypatch.delenv("EVI_VOICE_MAX_SECONDS", raising=False)
    monkeypatch.delenv("EVI_SIM", raising=False)


def _fake_llm(monkeypatch, content="olá"):
    model = MagicMock()
    model.invoke.return_value = AIMessage(content=content)
    build = MagicMock(return_value=model)
    monkeypatch.setattr(llm, "build_llm", build)
    return build, model


def test_ok_sends_text_and_media_parts(monkeypatch):
    build, model = _fake_llm(monkeypatch, "marcar dentista amanhã")
    res = tr.transcribe(b"\x00\x01audio", "audio/ogg", duration_s=12)
    assert res == tr.TranscriptionResult(ok=True, text="marcar dentista amanhã", reason="")
    build.assert_called_once_with()
    (messages,), _ = model.invoke.call_args
    assert len(messages) == 1
    parts = messages[0].content
    assert parts[0]["type"] == "text" and "português" in parts[0]["text"]
    assert parts[1] == {
        "type": "media",
        "mime_type": "audio/ogg",
        "data": base64.b64encode(b"\x00\x01audio").decode(),
    }


def test_text_collapsed_stripped_and_capped(monkeypatch):
    _fake_llm(monkeypatch, [{"type": "text", "text": "  oi \n\n  tudo   bem?  "}])
    assert tr.transcribe(b"x", "audio/ogg").text == "oi tudo bem?"
    _fake_llm(monkeypatch, "a" * 5000)
    assert len(tr.transcribe(b"x", "audio/ogg").text) == 2000


def test_disabled(monkeypatch):
    monkeypatch.setenv("EVI_VOICE_ENABLED", "false")
    build, _ = _fake_llm(monkeypatch)
    res = tr.transcribe(b"x", "audio/ogg")
    assert (res.ok, res.reason) == (False, "disabled")
    assert tr.user_message(res) == "Mensagens de voz estão desativadas."
    build.assert_not_called()


def test_voice_flag_default_off(monkeypatch):
    monkeypatch.delenv("EVI_VOICE_ENABLED")
    assert tr.voice_enabled() is False


def test_ollama_refused_without_llm_construction(monkeypatch):
    monkeypatch.setenv("EVI_LLM_PROVIDER", "ollama")
    build, _ = _fake_llm(monkeypatch)
    res = tr.transcribe(b"x", "audio/ogg", duration_s=5)
    assert (res.ok, res.reason) == (False, "unsupported_provider")
    assert tr.user_message(res) == "Áudio não é suportado neste modo."
    build.assert_not_called()


def test_sim_provider_allowed_only_with_evi_sim(monkeypatch):
    monkeypatch.setenv("EVI_LLM_PROVIDER", "sim-replay")
    _fake_llm(monkeypatch)
    assert tr.transcribe(b"x", "audio/ogg").reason == "unsupported_provider"
    monkeypatch.setenv("EVI_SIM", "1")
    assert tr.transcribe(b"x", "audio/ogg").ok


def test_too_long_refused_before_any_call(monkeypatch):
    build, model = _fake_llm(monkeypatch)
    res = tr.transcribe(b"x", "audio/ogg", duration_s=600)
    assert (res.ok, res.reason) == (False, "too_long")
    assert tr.user_message(res) == "O áudio passa de 5 min; mande um mais curto ou escreva."
    build.assert_not_called()
    model.invoke.assert_not_called()


def test_max_seconds_env(monkeypatch):
    monkeypatch.setenv("EVI_VOICE_MAX_SECONDS", "60")
    assert tr.max_seconds() == 60
    _fake_llm(monkeypatch)
    assert tr.transcribe(b"x", "audio/ogg", duration_s=61).reason == "too_long"
    assert tr.transcribe(b"x", "audio/ogg", duration_s=60).ok


def test_too_big(monkeypatch):
    build, _ = _fake_llm(monkeypatch)
    res = tr.transcribe(b"\0" * (20 * 1024 * 1024 + 1), "audio/ogg")
    assert (res.ok, res.reason) == (False, "too_big")
    build.assert_not_called()


@pytest.mark.parametrize("content", ["", "   \n ", []])
def test_empty_transcription(monkeypatch, content):
    _fake_llm(monkeypatch, content)
    res = tr.transcribe(b"x", "audio/ogg")
    assert (res.ok, res.reason) == (False, "empty")
    assert tr.user_message(res) == "Não consegui entender o áudio, pode repetir?"


def test_llm_error_is_failed(monkeypatch):
    _, model = _fake_llm(monkeypatch)
    model.invoke.side_effect = RuntimeError("boom")
    res = tr.transcribe(b"x", "audio/ogg")
    assert (res.ok, res.reason) == (False, "failed")
    assert tr.user_message(res) == "Não consegui ouvir o áudio agora."


def test_build_error_is_failed(monkeypatch):
    monkeypatch.setattr(llm, "build_llm", MagicMock(side_effect=RuntimeError("no key")))
    assert tr.transcribe(b"x", "audio/ogg").reason == "failed"


def test_media_part_accepted_by_gemini_converter_and_cassette_key_is_stable():
    from datetime import date

    from langchain_core.messages import HumanMessage

    from testing.sim.cassette import request_key

    audio = b"OggS\x00fake"
    parts = [
        {"type": "text", "text": "t"},
        {"type": "media", "mime_type": "audio/ogg", "data": base64.b64encode(audio).decode()},
    ]
    msgs = [HumanMessage(content=parts)]
    d = date(2026, 1, 1)
    assert request_key(msgs, None, d) == request_key([HumanMessage(content=list(parts))], None, d)
    try:
        from langchain_google_genai.chat_models import _convert_to_parts
    except ImportError:  # pragma: no cover
        pytest.skip("langchain_google_genai not installed")
    converted = _convert_to_parts(parts)
    assert converted[1].inline_data.data == audio
    assert converted[1].inline_data.mime_type == "audio/ogg"
