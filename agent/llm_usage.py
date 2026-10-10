"""Token usage extraction and cost estimation, shared by production turn logging and evi-sim.

langchain_google_genai puts usage on ``AIMessage.usage_metadata``:
``{input_tokens, output_tokens, total_tokens, output_token_details: {reasoning}}`` where
``output_tokens`` already INCLUDES the reasoning (thinking) tokens, which Google bills as output.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_PRICE_IN_USD = 0.30  # gemini-2.5-flash, per 1M input tokens
DEFAULT_PRICE_OUT_USD = 2.50  # per 1M output tokens (thinking included)
DEFAULT_USD_BRL = 5.5


def extract_usage(response: Any) -> tuple[int, int, int]:
    """(input, output, reasoning) tokens of an LLMResult; zeros when the provider reports none."""
    tin = tout = treason = 0
    try:
        for gens in getattr(response, "generations", None) or []:
            for gen in gens:
                meta = getattr(getattr(gen, "message", None), "usage_metadata", None)
                if not meta:
                    continue
                tin += int(meta.get("input_tokens") or 0)
                tout += int(meta.get("output_tokens") or 0)
                treason += int((meta.get("output_token_details") or {}).get("reasoning") or 0)
    except (AttributeError, TypeError, ValueError):
        pass
    return tin, tout, treason


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def estimate_cost(tokens_in: int, tokens_out: int, *, prefix: str = "EVI_LLM") -> tuple[float, float]:
    """(USD, BRL) estimate. Prices from ``<prefix>_PRICE_IN_USD`` / ``_PRICE_OUT_USD`` / ``_USD_BRL``."""
    usd = (
        tokens_in * _env_float(f"{prefix}_PRICE_IN_USD", DEFAULT_PRICE_IN_USD)
        + tokens_out * _env_float(f"{prefix}_PRICE_OUT_USD", DEFAULT_PRICE_OUT_USD)
    ) / 1_000_000
    return usd, usd * _env_float(f"{prefix}_USD_BRL", DEFAULT_USD_BRL)
