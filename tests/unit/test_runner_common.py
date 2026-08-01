import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))


def test_run_script_missing_script_returns_exit_1(tmp_path):
    from devcli.runner_common import run_script

    missing = tmp_path / "nope.sh"
    result = run_script(
        missing, "plan", "desc", repo_root=tmp_path, timeout_sec=5
    )
    assert result.exit_code == 1
    assert "missing" in result.stderr


def test_run_script_timeout_returns_124(tmp_path):
    import subprocess

    from devcli.runner_common import run_script

    script = tmp_path / "fake.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)

    with patch(
        "devcli.runner_common.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="fake", timeout=1),
    ):
        result = run_script(
            script, "apply", "desc", repo_root=tmp_path, timeout_sec=1
        )
    assert result.exit_code == 124


def test_run_script_parses_apply_markers(tmp_path):
    from devcli.runner_common import run_script

    script = tmp_path / "fake.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)

    fake_proc = MagicMock(
        returncode=0,
        stdout="did the thing\nEVI_DEV_BRANCH=dev/job-1\nEVI_DEV_DIFFSTAT=1 file changed\n",
        stderr="",
    )
    with patch("devcli.runner_common.subprocess.run", return_value=fake_proc):
        result = run_script(
            script, "apply", "desc", repo_root=tmp_path, timeout_sec=5
        )
    assert result.branch == "dev/job-1"
    assert result.diff_stat == "1 file changed"


def test_run_script_no_markers_in_plan_mode(tmp_path):
    from devcli.runner_common import run_script

    script = tmp_path / "fake.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)

    fake_proc = MagicMock(returncode=0, stdout="just a plan, no markers", stderr="")
    with patch("devcli.runner_common.subprocess.run", return_value=fake_proc):
        result = run_script(
            script, "plan", "desc", repo_root=tmp_path, timeout_sec=5
        )
    assert result.branch == ""
    assert result.diff_stat == ""
