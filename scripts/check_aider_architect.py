#!/usr/bin/env python3
"""Verify aider architect-mode configuration and model routing.

Checks performed (offline by default):
  1. .aider.conf.yml exists and parses.
  2. architect: true is set.
  3. model, editor-model and weak-model are all set and distinct.
  4. (optional) --online: each model id exists on OpenRouter.
  5. (optional) --ping:   each model answers a 1-token completion.

Exit code 0 = all checks passed, 1 = failure.

Usage:
    python scripts/check_aider_architect.py
    python scripts/check_aider_architect.py --online
    python scripts/check_aider_architect.py --online --ping
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(".aider.conf.yml")
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

REQUIRED_KEYS = ("model", "editor-model", "weak-model")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_config(path: Path) -> dict[str, str]:
    """Load the config, preferring PyYAML but falling back to a tiny parser."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        return {str(k): str(v) for k, v in data.items()}
    except ImportError:
        pass

    # Minimal fallback: only handles flat "key: value" lines.
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = _strip_quotes(value)
    return out


def check_config(cfg: dict[str, str]) -> list[str]:
    problems: list[str] = []

    if str(cfg.get("architect", "")).lower() not in ("true", "yes", "1"):
        problems.append("architect is not enabled (expected 'architect: true')")

    for key in REQUIRED_KEYS:
        if not cfg.get(key):
            problems.append(f"missing required key: {key}")

    models = [cfg.get(k, "") for k in REQUIRED_KEYS]
    if len(set(models)) != len(models):
        problems.append("model, editor-model and weak-model must be distinct")

    return problems


def fetch_openrouter_models(api_key: str | None) -> set[str]:
    req = urllib.request.Request(OPENROUTER_MODELS_URL)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return {m["id"] for m in payload.get("data", [])}


def check_online(cfg: dict[str, str], api_key: str | None) -> list[str]:
    problems: list[str] = []
    try:
        available = fetch_openrouter_models(api_key)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [f"could not fetch OpenRouter model list: {exc}"]

    for key in REQUIRED_KEYS:
        model = cfg.get(key, "")
        if model and model not in available:
            problems.append(f"{key} '{model}' not found on OpenRouter")
    return problems


def ping_model(model: str, api_key: str) -> str | None:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
            "max_tokens": 1,
        }
    ).encode("utf-8")
    req = urllib.request.Request(OPENROUTER_CHAT_URL, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"].get("content", "")
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(CONFIG_PATH), help="path to .aider.conf.yml")
    parser.add_argument("--online", action="store_true", help="verify models exist on OpenRouter")
    parser.add_argument("--ping", action="store_true", help="send a 1-token completion to each model")
    args = parser.parse_args(argv)

    path = Path(args.config)
    if not path.exists():
        print(f"FAIL: config not found: {path}")
        return 1

    cfg = load_config(path)
    print(f"Loaded {path}:")
    for key in ("architect", *REQUIRED_KEYS):
        print(f"  {key}: {cfg.get(key, '<unset>')}")

    problems = check_config(cfg)
    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        return 1
    print("OK: config structure is valid")

    api_key = os.environ.get("OPENROUTER_API_KEY")

    if args.online:
        if not api_key:
            print("WARN: OPENROUTER_API_KEY not set; skipping --online check")
        else:
            problems = check_online(cfg, api_key)
            if problems:
                for p in problems:
                    print(f"FAIL: {p}")
                return 1
            print("OK: all models exist on OpenRouter")

    if args.ping:
        if not api_key:
            print("FAIL: --ping requires OPENROUTER_API_KEY")
            return 1
        for key in REQUIRED_KEYS:
            model = cfg.get(key, "")
            reply = ping_model(model, api_key)
            if reply is None:
                print(f"FAIL: {key} '{model}' did not respond")
                return 1
            print(f"OK: {key} '{model}' responded: {reply!r}")

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
