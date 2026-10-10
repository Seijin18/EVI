"""Isolation guard for the evi-sim stack (SCN-SIM-01).

Runs over the RENDERED compose config (``docker compose ... config --format json``),
so a leak via env_file, interpolation or an override is caught, not just what the
YAML text says. ``check_config`` is a pure function; ``main`` shells out to compose.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT = "evi-sim"
SIM_TOKEN = "sim-token"
FORBIDDEN_HOSTS = ("api.telegram.org", "googleapis.com", "evolution-api")
FORBIDDEN_BIND_DIRS = ("data", "logs")
ALLOWED_GOOGLE_ENV = {"GEMINI_API_KEY"}  # the key itself is the only forwarded secret

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "docker-compose.sim.yml"


def _environment(service: dict[str, Any]) -> dict[str, str]:
    env = service.get("environment") or {}
    if isinstance(env, list):
        out: dict[str, str] = {}
        for item in env:
            key, _, value = str(item).partition("=")
            out[key] = value
        return out
    return {str(k): "" if v is None else str(v) for k, v in env.items()}


def _is_forbidden_bind(source: str, repo_root: Path) -> bool:
    src = Path(source)
    if not src.is_absolute():
        return False
    for name in FORBIDDEN_BIND_DIRS:
        banned = repo_root / name
        if src == banned or banned in src.parents:
            return True
    return False


def check_config(config: dict[str, Any], repo_root: Path = REPO_ROOT) -> list[str]:
    """Return a list of violations (empty means the config is isolated)."""
    problems: list[str] = []
    if config.get("name") != PROJECT:
        problems.append(f"project name is {config.get('name')!r}, expected {PROJECT!r}")

    for svc_name, svc in (config.get("services") or {}).items():
        for vol in svc.get("volumes") or []:
            if isinstance(vol, dict) and vol.get("type") == "bind":
                source = str(vol.get("source", ""))
                if _is_forbidden_bind(source, repo_root):
                    problems.append(f"service {svc_name}: bind mount of {source} (data/logs are off limits)")
        env = _environment(svc)
        token = env.get("TELEGRAM_BOT_TOKEN")
        if token is not None and token != SIM_TOKEN:
            problems.append(f"service {svc_name}: TELEGRAM_BOT_TOKEN is not {SIM_TOKEN!r}")
        for key, value in env.items():
            if key in ALLOWED_GOOGLE_ENV:
                continue
            for host in FORBIDDEN_HOSTS:
                if host in value:
                    problems.append(f"service {svc_name}: env {key} references forbidden host {host}")
    return problems


def render_config() -> dict[str, Any]:
    cmd = [
        "docker", "compose", "-p", PROJECT, "-f", str(COMPOSE_FILE),
        "--env-file", "/dev/null", "config", "--format", "json",
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=REPO_ROOT)
    return json.loads(out.stdout)


def main(argv: list[str] | None = None) -> int:
    try:
        config = render_config()
    except (subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        print(f"evi-sim guard: cannot render compose config: {detail}", file=sys.stderr)
        return 2
    problems = check_config(config)
    if problems:
        for p in problems:
            print(f"evi-sim guard: ABORT: {p}", file=sys.stderr)
        return 1
    print("evi-sim guard: OK (isolated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
