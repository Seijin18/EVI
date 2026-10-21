"""LLM and embeddings provider factory.

Select via environment variables:
  EVI_LLM_PROVIDER   = ollama (default) | gemini | openai | anthropic
  EVI_EMBED_PROVIDER = ollama (default) | google | openai
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _llm_provider() -> str:
    return os.getenv("EVI_LLM_PROVIDER", "ollama").strip().lower()


def _embed_provider() -> str:
    return os.getenv("EVI_EMBED_PROVIDER", "ollama").strip().lower()


def _gemini_thinking_kwargs() -> dict[str, Any]:
    """`thinking_budget` for Gemini 2.5 from EVI_GEMINI_THINKING_BUDGET (read at build time).

    Unset/empty -> {} (provider default, today's behaviour). Integer >= 0 -> pass it
    (0 disables thinking). Anything else is ignored with a warning.
    """
    raw = os.getenv("EVI_GEMINI_THINKING_BUDGET", "").strip()
    if not raw:
        return {}
    try:
        budget = int(raw)
        if budget < 0:
            raise ValueError(raw)
    except ValueError:
        logger.warning("EVI_GEMINI_THINKING_BUDGET=%r is not an integer >= 0; ignoring", raw)
        return {}
    return {"thinking_budget": budget}


def build_ollama_llm(*, temperature: float | None = None, num_ctx: int | None = None):
    """Always Ollama — for background tasks (extract, summaries, contact learn)."""
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434"),
        temperature=temperature if temperature is not None else 0.1,
        num_ctx=num_ctx if num_ctx is not None else 2048,
        num_gpu=-1,
    )


_SIM_PROVIDERS = ("sim-replay", "sim-record", "sim-fill")


def _is_sim_provider(provider: str) -> bool:
    """evi-sim cassette providers exist only when EVI_SIM=1 (otherwise: unknown provider)."""
    return provider in _SIM_PROVIDERS and os.getenv("EVI_SIM", "").strip() == "1"


def background_provider() -> str:
    """Provider used by cron/background work. Ollama unless explicitly overridden."""
    override = os.getenv("EVI_BACKGROUND_LLM_PROVIDER", "ollama").strip().lower()
    if _is_sim_provider(override):
        return override
    return override if override in ("gemini", "openai", "anthropic") else "ollama"


def build_background_llm(*, temperature: float | None = None, num_ctx: int | None = None):
    """Background/cron LLM — Ollama unless EVI_BACKGROUND_LLM_PROVIDER overrides it.

    Passes the provider explicitly instead of swapping EVI_LLM_PROVIDER in
    os.environ around the call, which raced with concurrent /chat turns.
    """
    provider = background_provider()
    if provider == "ollama":
        return build_ollama_llm(temperature=temperature, num_ctx=num_ctx)
    return build_llm(provider=provider, temperature=temperature, num_ctx=num_ctx)


def build_llm(
    *,
    provider: str | None = None,
    temperature: float | None = None,
    num_ctx: int | None = None,
):
    """Return a LangChain BaseChatModel. An explicit `provider` wins over env."""
    provider = (provider or "").strip().lower() or _llm_provider()

    if _is_sim_provider(provider):
        from testing.sim.cassette import build_sim_llm  # lazy: sim-only, never imported in prod

        return build_sim_llm(provider, temperature=temperature)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            google_api_key=os.getenv("GEMINI_API_KEY", ""),
            temperature=temperature if temperature is not None else 0.1,
            # Per-attempt timeout + few retries: a hung request must not block the turn
            # for minutes (seen in evi-sim; the library default is 6 retries).
            timeout=float(os.getenv("EVI_LLM_TIMEOUT_SEC", "30")),
            max_retries=int(os.getenv("EVI_LLM_MAX_RETRIES", "2")),
            **_gemini_thinking_kwargs(),
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            temperature=temperature if temperature is not None else 0.1,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=os.getenv("CLAUDE_MODEL", "claude-3-5-haiku-20241022"),
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            temperature=temperature if temperature is not None else 0.1,
        )

    return build_ollama_llm(temperature=temperature, num_ctx=num_ctx)


def build_embeddings():
    """Return a LangChain Embeddings instance for the configured provider."""
    provider = _embed_provider()

    if provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=os.getenv("GEMINI_EMBED_MODEL", "models/gemini-embedding-001"),
            google_api_key=os.getenv("GEMINI_API_KEY", ""),
        )

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )

    # Default: ollama
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(
        model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434"),
    )


def _extract_gemini_text(content: Any) -> str:
    """Gemini via LangChain returns AIMessage.content as list[{type, text, ...}]."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                text = block.strip()
            elif isinstance(block, dict):
                text = str(block.get("text") or "").strip()
            else:
                text = str(block).strip()
            if text:
                parts.append(text)
        return "\n".join(parts)
    return str(content or "").strip()


def _extract_default_text(content: Any) -> str:
    """Ollama / OpenAI / Anthropic typically return plain strings."""
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content).strip()


def extract_llm_text(content: Any, *, provider: str | None = None) -> str:
    """Normalize provider-specific AIMessage.content to user-facing plain text."""
    p = (provider or _llm_provider()).strip().lower()
    if p == "gemini" or _is_sim_provider(p):  # sim cassettes replay Gemini-shaped content
        return _extract_gemini_text(content)
    return _extract_default_text(content)
