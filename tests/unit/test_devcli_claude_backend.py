import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))


def test_claude_backend_invokes_run_script_with_mode_and_script():
    from devcli.claude_backend import ClaudeCliBackend, _SCRIPT
    from devcli.base import DevCliResult

    backend = ClaudeCliBackend()
    fake_result = DevCliResult(exit_code=0, stdout="ok")

    with patch("devcli.claude_backend.run_script", return_value=fake_result) as run_script:
        out = backend.run(
            "apply", "fix tests", repo_root=Path("/repo"), timeout_sec=10
        )

    run_script.assert_called_once_with(
        _SCRIPT, "apply", "fix tests", repo_root=Path("/repo"), timeout_sec=10
    )
    assert out is fake_result
    assert backend.name == "claude"
