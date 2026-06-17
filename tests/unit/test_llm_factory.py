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


if __name__ == "__main__":
    test_build_llm_provider_env_read()
    test_build_embeddings_provider_env_read()
    print("ok")
