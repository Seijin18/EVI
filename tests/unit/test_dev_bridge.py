import os
import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))


def test_propose_dev_task_disabled():
    from services.dev_bridge import propose_dev_task

    os.environ.pop("EVI_DEV_BRIDGE_ENABLED", None)
    out = propose_dev_task("fix test")
    assert out.get("ok") is False


def test_propose_and_status_with_db():
    from services.dev_bridge import propose_dev_task, status_dev_jobs

    with patch("db.create_dev_job") as create, patch(
        "db.get_dev_bridge_setting", return_value="default"
    ):
        with patch.dict(os.environ, {"EVI_DEV_BRIDGE_ENABLED": "true"}):
            create.return_value = None
            out = propose_dev_task("run evi-test smoke")
    assert out.get("ok") is True
    assert out.get("job_id")
    assert create.call_args.kwargs.get("backend") == "claude"

    with patch("db.list_dev_jobs", return_value=[]):
        assert "Nenhum" in status_dev_jobs()


def test_try_dev_command_backward_compat():
    """The 3 original chat-command shapes must keep working unchanged."""
    from services import dev_bridge

    with patch.dict(os.environ, {"EVI_DEV_BRIDGE_ENABLED": "true"}):
        with patch.object(
            dev_bridge, "status_dev_jobs", return_value="Jobs dev:\n- x"
        ):
            assert dev_bridge.try_dev_command("dev status") == "Jobs dev:\n- x"
            assert dev_bridge.try_dev_command("dev jobs") == "Jobs dev:\n- x"

        with patch.object(
            dev_bridge,
            "propose_dev_task",
            return_value={"message": "registrado", "ok": True},
        ) as propose:
            out = dev_bridge.try_dev_command("dev: fix the tests")
            assert out == "registrado"
            assert propose.call_args.args[0] == "fix the tests"
            assert propose.call_args.kwargs.get("backend") == ""

        with patch.object(
            dev_bridge,
            "approve_dev_task",
            return_value={"ok": True, "backend": "claude", "stdout": "ok"},
        ) as approve:
            dev_bridge.try_dev_command("dev approve abc123")
            approve.assert_called_once_with("abc123", backend_override=None)

    # Not a dev command at all -> None, so callers fall through to normal chat.
    with patch.dict(os.environ, {"EVI_DEV_BRIDGE_ENABLED": "true"}):
        assert dev_bridge.try_dev_command("oi, tudo bem?") is None


def test_try_dev_command_cli_override_parsing():
    from services import dev_bridge

    with patch.dict(os.environ, {"EVI_DEV_BRIDGE_ENABLED": "true"}):
        with patch.object(
            dev_bridge,
            "approve_dev_task",
            return_value={"ok": True, "backend": "claude", "stdout": "ok"},
        ) as approve:
            dev_bridge.try_dev_command("dev approve abc123 --cli=claude")
            approve.assert_called_once_with("abc123", backend_override="claude")

        with patch.object(
            dev_bridge,
            "propose_dev_task",
            return_value={"message": "registrado", "ok": True},
        ) as propose:
            dev_bridge.try_dev_command("dev: fix the tests --cli=claude")
            assert propose.call_args.args[0] == "fix the tests"
            assert propose.call_args.kwargs.get("backend") == "claude"


def test_propose_dev_task_mode_toggle():
    from services import dev_bridge

    with patch.dict(os.environ, {"EVI_DEV_BRIDGE_ENABLED": "true"}):
        with patch.object(dev_bridge, "_set_propose_mode") as set_mode:
            assert "default" in dev_bridge.try_dev_command("dev mode default")
            set_mode.assert_called_once_with("default")

        with patch.object(dev_bridge, "_set_propose_mode") as set_mode:
            assert "plan" in dev_bridge.try_dev_command("dev mode plan")
            set_mode.assert_called_once_with("plan")

        with patch.object(dev_bridge, "_propose_mode", return_value="eager"):
            assert "eager" in dev_bridge.try_dev_command("dev mode")


def test_approve_dev_task_uses_apply_mode():
    """Regression guard for the original bug: approve must run 'apply', not 'plan'."""
    from services.dev_bridge import approve_dev_task

    fake_job = {
        "job_id": "abc123",
        "description": "fix the tests",
        "status": "pending",
        "backend": "claude",
    }

    class FakeResult:
        exit_code = 0
        stdout = "done"
        stderr = ""
        log_path = "/tmp/log"
        branch = "dev/job-1"
        diff_stat = "1 file changed"

    class FakeBackend:
        name = "claude"
        calls = []

        def run(self, mode, description, *, repo_root, timeout_sec):
            FakeBackend.calls.append(mode)
            return FakeResult()

    with patch.dict(os.environ, {"EVI_DEV_BRIDGE_ENABLED": "true"}):
        with patch("db.get_dev_job", return_value=fake_job), patch(
            "db.update_dev_job"
        ) as update_dev_job, patch(
            "devcli.factory.resolve_dev_cli", return_value=FakeBackend()
        ):
            out = approve_dev_task("abc123")

    assert FakeBackend.calls == ["apply"]
    assert out["ok"] is True
    assert out["branch"] == "dev/job-1"
    assert update_dev_job.call_count == 2
    final_call = update_dev_job.call_args
    assert final_call.kwargs.get("mode") == "apply"
    assert final_call.kwargs.get("branch") == "dev/job-1"
    assert final_call.kwargs.get("status") == "done"


def test_approve_dev_task_rejects_running_job():
    from services.dev_bridge import approve_dev_task

    with patch.dict(os.environ, {"EVI_DEV_BRIDGE_ENABLED": "true"}):
        with patch(
            "db.get_dev_job",
            return_value={"job_id": "abc123", "status": "running"},
        ):
            out = approve_dev_task("abc123")
    assert out["ok"] is False
