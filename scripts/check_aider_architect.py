"""Validate the aider architect configuration.

Checks that an architect model and an editor model are configured, and that
they are not the same model. Values are read from the environment first
(``ARCHITECT_MODEL`` / ``EDITOR_MODEL``) and fall back to ``.aider.conf.yml``
in the repository root.

Exit codes:
    0 - configuration looks valid
    1 - configuration is missing or invalid
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - yaml is optional
    yaml = None  # type: ignore[assignment]


CONFIG_FILENAME = ".aider.conf.yml"


def _load_yaml_config(repo_root: Path) -> dict:
    """Return the parsed aider config, or an empty dict if unavailable."""
    if yaml is None:
        return {}
    path = repo_root / CONFIG_FILENAME
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:  # type: ignore[attr-defined]
        print(f"warning: could not read {path}: {exc}", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def _resolve(name: str, config: dict) -> str | None:
    """Resolve a model name from env var ``name`` or config key ``name.lower()``."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    raw = config.get(name.lower())
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    repo_root = Path(argv[0]).resolve() if argv else Path.cwd()

    config = _load_yaml_config(repo_root)
    architect = _resolve("ARCHITECT_MODEL", config)
    editor = _resolve("EDITOR_MODEL", config)

    problems: list[str] = []
    if not architect:
        problems.append("ARCHITECT_MODEL is not set (env or .aider.conf.yml)")
    if not editor:
        problems.append("EDITOR_MODEL is not set (env or .aider.conf.yml)")
    if architect and editor and architect == editor:
        problems.append(
            f"ARCHITECT_MODEL and EDITOR_MODEL are the same ({architect!r}); "
            "the architect should differ from the editor"
        )

    if problems:
        print("aider architect check: FAILED", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("aider architect check: OK")
    print(f"  architect: {architect}")
    print(f"  editor:    {editor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
