import os
import sys
import tempfile
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.contact_filesystem import ingest_commitment  # noqa: E402
from services.daily_summary import build_summary_markdown, run_daily_summaries  # noqa: E402


def test_build_summary_markdown():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        jid = "5511999999999@s.whatsapp.net"
        ingest_commitment(
            jid=jid,
            source_id="w002",
            title="Task test",
            raw_text="sexta",
            commitment_id=7,
        )
        md = build_summary_markdown(jid, label="Test")
        assert "# Resumo" in md
        assert "Task test" in md


def test_run_daily_summaries_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        jid = "5511888888888@s.whatsapp.net"
        ingest_commitment(
            jid=jid,
            source_id="w003",
            title="Almoço",
            raw_text="hoje",
            commitment_id=8,
        )
        n = run_daily_summaries()
        assert n >= 1
        summaries = list(Path(tmp).glob("contacts/*/summaries/*.md"))
        assert summaries


if __name__ == "__main__":
    test_build_summary_markdown()
    test_run_daily_summaries_writes_file()
    print("ok")
