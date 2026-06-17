import os
import sys
import tempfile
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

    with tempfile.TemporaryDirectory() as tmp:
        # skip real postgres — mock db layer
        with patch("services.dev_bridge.create_dev_job") as create:
            with patch.dict(os.environ, {"EVI_DEV_BRIDGE_ENABLED": "true"}):
                create.return_value = None
                out = propose_dev_task("run evi-test smoke")
        assert out.get("ok") is True
        assert out.get("job_id")

        with patch("db.list_dev_jobs", return_value=[]):
            assert "Nenhum" in status_dev_jobs()
