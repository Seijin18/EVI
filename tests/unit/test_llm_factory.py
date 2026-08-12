"""Unit tests for agent/llm.py factory functions."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))


def test_build_llm_provider_env_read():
    """build_llm() reads EVI_LLM_PROVIDER correctly."""
    import llm as llm_mod
    assert llm_mod._llm_provider() == "ollama"  # default
    with patch.dict(os.environ, {"EVI_LLM_PROVIDER": "gemini"}):
        assert llm_mod._llm_provider() == "gemini"


def test_build_embeddings_provider_env_read():
    """build_embeddings() reads EVI_EMBED_PROVIDER correctly."""
    import llm as llm_mod
    assert llm_mod._embed_provider() == "ollama"  # default
    with patch.dict(os.environ, {"EVI_EMBED_PROVIDER": "google"}):
        assert llm_mod._embed_provider() == "google"


def test_build_llm_ollama_constructs():
    """build_llm() with ollama provider instantiates ChatOllama."""
    os.environ.pop("EVI_LLM_PROVIDER", None)
    fake_ollama = MagicMock()
    fake_module = MagicMock()
    fake_module.ChatOllama = fake_ollama
    with patch.dict("sys.modules", {"langchain_ollama": fake_module}):
        import importlib
        import llm as llm_mod
        importlib.reload(llm_mod)
        llm_mod.build_llm()
    fake_ollama.assert_called_once()


def test_build_embeddings_ollama_constructs():
    """build_embeddings() with ollama provider instantiates OllamaEmbeddings."""
    os.environ.pop("EVI_EMBED_PROVIDER", None)
    fake_embed = MagicMock()
    fake_module = MagicMock()
    fake_module.OllamaEmbeddings = fake_embed
    with patch.dict("sys.modules", {"langchain_ollama": fake_module}):
        import importlib
        import llm as llm_mod
        importlib.reload(llm_mod)
        llm_mod.build_embeddings()
    fake_embed.assert_called_once()


def test_build_background_llm_defaults_ollama():
    """build_background_llm() uses Ollama even when EVI_LLM_PROVIDER=gemini."""
    fake_ollama = MagicMock()
    fake_module = MagicMock()
    fake_module.ChatOllama = fake_ollama
    with patch.dict(os.environ, {"EVI_LLM_PROVIDER": "gemini", "EVI_BACKGROUND_LLM_PROVIDER": "ollama"}):
        with patch.dict("sys.modules", {"langchain_ollama": fake_module}):
            import importlib
            import llm as llm_mod
            importlib.reload(llm_mod)
            llm_mod.build_background_llm()
    fake_ollama.assert_called_once()


def test_build_background_llm_does_not_mutate_env():
    """SCN-PROV-04 — a background build must be invisible to a concurrent /chat."""
    fake_gemini = MagicMock()
    fake_module = MagicMock()
    fake_module.ChatGoogleGenerativeAI = fake_gemini
    env = {"EVI_LLM_PROVIDER": "ollama", "EVI_BACKGROUND_LLM_PROVIDER": "gemini"}

    with patch.dict(os.environ, env):
        with patch.dict("sys.modules", {"langchain_google_genai": fake_module}):
            import importlib
            import llm as llm_mod
            importlib.reload(llm_mod)

            seen = []
            original = llm_mod._llm_provider

            def _spy():
                value = original()
                seen.append(value)
                return value

            llm_mod._llm_provider = _spy
            try:
                llm_mod.build_background_llm()
                during = os.environ["EVI_LLM_PROVIDER"]
            finally:
                llm_mod._llm_provider = original

    fake_gemini.assert_called_once()
    assert during == "ollama"
    assert os.environ.get("EVI_LLM_PROVIDER") != "gemini"
    # The chat provider must never have been consulted for a background build.
    assert seen == []


def test_build_llm_explicit_provider_beats_env():
    fake_gemini = MagicMock()
    fake_module = MagicMock()
    fake_module.ChatGoogleGenerativeAI = fake_gemini
    with patch.dict(os.environ, {"EVI_LLM_PROVIDER": "ollama"}):
        with patch.dict("sys.modules", {"langchain_google_genai": fake_module}):
            import importlib
            import llm as llm_mod
            importlib.reload(llm_mod)
            llm_mod.build_llm(provider="gemini")
    fake_gemini.assert_called_once()


def test_background_provider_resolution():
    import llm as llm_mod

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EVI_BACKGROUND_LLM_PROVIDER", None)
        assert llm_mod.background_provider() == "ollama"
    with patch.dict(os.environ, {"EVI_BACKGROUND_LLM_PROVIDER": "gemini"}):
        assert llm_mod.background_provider() == "gemini"
    # Unknown values fall back to Ollama rather than exploding at call time.
    with patch.dict(os.environ, {"EVI_BACKGROUND_LLM_PROVIDER": "nonsense"}):
        assert llm_mod.background_provider() == "ollama"


if __name__ == "__main__":
    test_build_llm_provider_env_read()
    test_build_embeddings_provider_env_read()
    print("ok")
