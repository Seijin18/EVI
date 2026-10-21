"""evi-sim --llm fill in the runner (SCN-SIM-10/11): run-start snapshot, save on pass, real vs served."""
from __future__ import annotations

from types import SimpleNamespace

from testing.sim import report, runner


class FakeCtx(runner.Ctx):
    """Ctx whose container exec is recorded instead of run; ``files`` stands in for the container."""

    def __init__(self, mode: str, **kw):
        super().__init__(llm_mode=mode, env={}, **kw)
        self.files: dict[str, str] = {}
        self.execs: list[str] = []

    def exec(self, service, *cmd, input_=None):  # noqa: ANN001
        sh = cmd[-1]
        self.execs.append(sh)
        if sh.startswith("cat > "):
            self.files[sh[len("cat > "):]] = input_
            return ""
        if sh.startswith("cat "):
            path = sh.split()[1]
            return self.files.get(path, "")
        return ""


def _scn(i: str):
    return SimpleNamespace(id=i)


def test_snapshots_read_once_at_run_start(tmp_path):
    (tmp_path / "SIM-A.jsonl").write_text('{"key": "k"}\n')
    snaps = runner.fill_snapshots([_scn("SIM-A"), _scn("SIM-NEW")], tmp_path)
    assert snaps == {"SIM-A": '{"key": "k"}\n', "SIM-NEW": ""}


def test_fill_ships_the_snapshot_not_the_host_file(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CASSETTES_HOST_DIR", tmp_path)
    (tmp_path / "SIM-A.jsonl").write_text("gravado por uma tentativa anterior\n")
    ctx = FakeCtx("fill", snapshots={"SIM-A": "original\n"})
    runner.cassette_begin(ctx, "SIM-A")
    assert ctx.files[f"{runner.CASSETTE_DIR}/SIM-A.jsonl"] == "original\n"


def test_fill_new_scenario_ships_nothing_and_does_not_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CASSETTES_HOST_DIR", tmp_path)
    ctx = FakeCtx("fill", snapshots={"SIM-NEW": ""})
    runner.cassette_begin(ctx, "SIM-NEW")  # replay would raise "no cassette"
    assert f"{runner.CASSETTE_DIR}/SIM-NEW.jsonl" not in ctx.files
    assert f"{runner.CASSETTE_DIR}/ctl" in ctx.files


def test_fill_saves_only_a_passing_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CASSETTES_HOST_DIR", tmp_path)
    ctx = FakeCtx("fill")
    ctx.files[f"{runner.CASSETTE_DIR}/SIM-A.jsonl"] = "novo\n"
    failed = runner.Result("SIM-A", failures=["step 0: x"])
    runner.cassette_end(ctx, "SIM-A", failed)
    assert not (tmp_path / "SIM-A.jsonl").exists()
    runner.cassette_end(ctx, "SIM-A", runner.Result("SIM-A"))
    assert (tmp_path / "SIM-A.jsonl").read_text() == "novo\n"


def test_cassette_stats_counts_real_and_served():
    ctx = FakeCtx("fill")
    ctx.files[runner.CASSETTE_STATS_FILE] = "served\nreal\nserved\nserved\n"
    assert runner.cassette_stats(ctx) == (1, 3)


def test_report_shows_real_and_served(tmp_path):
    res = SimpleNamespace(passed=True, failures=[], tools_called=[], steps=[], llm_calls=2, llm_served=7,
                          tokens_in=100, tokens_out=10, tokens_reasoning=0, duration_s=1.0)
    rec = report.attempt_record("SIM-A", ["critical"], 1, res)
    assert rec["llm_calls"] == 2 and rec["llm_served"] == 7
    meta = {"ts": "T", "repeat": 1, "max_llm_calls": 200, "llm_calls": 2, "budget_hit": False}
    s = report.summarize([rec], 1)
    assert "real 2 · served 7" in report.console_summary(s, meta, [rec])
    _, md = report.write_reports([rec], s, meta, tmp_path, "T")
    assert "real 2 · served 7" in md.read_text() and "| 2/7 |" in md.read_text()
