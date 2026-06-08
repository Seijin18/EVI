"""LLM and embeddings provider factory.

Select via environment variables:
  EVI_LLM_PROVIDER   = ollama (default) | gemini | openai | anthropic
  EVI_EMBED_PROVIDER = ollama (default) | google | openai
"""

from __future__ import annotations

import os


def _llm_provider() -> str:
    return os.getenv("EVI_LLM_PROVIDER", "ollama").strip().lower()


def _embed_provider() -> str:
    return os.getenv("EVI_EMBED_PROVIDER", "ollama").strip().lower()


def build_llm(*, temperature: float | None = None, num_ctx: int | None = None):
    """Return a LangChain BaseChatModel for the configured provider."""
    provider = _llm_provider()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            google_api_key=os.getenv("GEMINI_API_KEY", ""),
            temperature=temperature if temperature is not None else 0.1,
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

    # Default: ollama
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434"),
        temperature=temperature if temperature is not None else 0.1,
        num_ctx=num_ctx if num_ctx is not None else 2048,
        num_gpu=-1,
    )


def build_embeddings():
    """Return a LangChain Embeddings instance for the configured provider."""
    provider = _embed_provider()

    if provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=os.getenv("GEMINI_EMBED_MODEL", "models/text-embedding-004"),
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
