import os
import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))


def test_resolve_dev_cli_default_is_claude():
    from devcli.factory import resolve_dev_cli

    backend = resolve_dev_cli("claude")
    assert backend.name == "claude"


def test_resolve_dev_cli_unknown_raises():
    from devcli.factory import resolve_dev_cli

    try:
        resolve_dev_cli("nonexistent")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "nonexistent" in str(exc)


def test_get_dev_cli_reads_env_default():
    import devcli.factory as factory

    factory.get_dev_cli.cache_clear()
    with patch.dict(os.environ, {"EVI_DEV_CLI": "claude"}):
        backend = factory.get_dev_cli()
    assert backend.name == "claude"
    factory.get_dev_cli.cache_clear()


def test_resolve_dev_cli_bypasses_cache():
    from devcli.factory import resolve_dev_cli

    a = resolve_dev_cli("claude")
    b = resolve_dev_cli("claude")
    assert a is not b
