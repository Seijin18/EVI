"""evi-sim scenario runner (task 3.1).

    PYTHONPATH=agent python -m testing.sim.runner run [--tag a,b] [--id X] [--repeat N]
                                                      [--llm live|record|replay] [--max-llm-calls N]
                                                      [--scenarios-dir DIR]

Per scenario: reset (fakes + agent tables + session memory + audit logs), set clock,
seed, then run the steps. The runner never calls /chat: Telegram steps are enqueued in
the fake Bot API and picked up by the agent's real poller (SCN-SIM-02); WhatsApp steps
POST a payload built from the real Evolution fixture to the agent's real
``/webhooks/evolution``.

LLM calls: counted INSIDE the agent container by ``testing.sim.llm_counter`` (a global
LangChain callback installed by the sim image's entrypoint, appending a line per chat-model
call to ``/tmp/evi-sim-llm-calls``). The agent has no metrics counter for LLM calls
(``EVI_METRICS_ENABLED`` only exposes HTTP/webhook metrics), and Gemini traffic leaves the
container directly, so this hook is the one signal that sees every call (turns, background
extractors, summaries). Per attempt = line-count delta; the budget is checked between
attempts (see ``testing.sim.report``).

Tools called (union, per scenario since reset):
  1. ``telegram.jsonl`` audit log in the agent container (every tool call of a Telegram
     turn, kind == "call");
  2. ``session_tool_snapshots`` rows (only a handful of tools are snapshotted);
  3. fake-Windmill ``/_sim/calls`` ops (op name == script name, used as a fallback so
     WhatsApp-control turns, which are not audited, still show their Google tools).
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from testing.sim import report, schema, workspace_seed
from testing.sim.schema import Scenario, Step

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIOS_DIR = REPO_ROOT / "tests" / "sim" / "scenarios"
SIM_ENV = REPO_ROOT / "tests" / "sim" / "sim.env"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "evolution" / "messages_upsert.json"
AUDIO_DIR = REPO_ROOT / "tests" / "fixtures" / "audio"
DEFAULT_VOICE_SECONDS = 3
COMPOSE = ["docker", "compose", "-p", "evi-sim", "--env-file", "/dev/null", "-f", str(REPO_ROOT / "docker-compose.sim.yml")]
AUDIT_LOG = "/tmp/evi-sim-logs"
LLM_COUNT_FILE = "/tmp/evi-sim-llm-calls"  # written by testing.sim.llm_counter in the container
LLM_USAGE_FILE = "/tmp/evi-sim-llm-usage"  # JSON lines {in,out,reasoning} per real model call
DEFAULT_MAX_LLM_CALLS = 200
CASSETTE_DIR = "/tmp/evi-sim-cassettes"  # inside the agent container (see testing.sim.cassette)
CASSETTES_HOST_DIR = REPO_ROOT / "tests" / "sim" / "cassettes"
LLM_MODES = ("live", "record", "replay")
SIM_LOG_DIR = REPO_ROOT / "logs" / "sim"
DEFAULT_REPLY_TIMEOUT_S = 120
SETTLE_S = 2.0
DEFAULT_CONTACT_JID = "5511999999999@s.whatsapp.net"
GROUP_JID = "120363000000000001@g.us"


def read_env(path: Path = SIM_ENV) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


@dataclass
class Ctx:
    fakes_url: str = "http://127.0.0.1:18080"
    agent_url: str = "http://127.0.0.1:18000"
    env: dict = field(default_factory=read_env)
    llm_mode: str = "live"

    @property
    def tz(self) -> str:
        return self.env.get("EVI_TIMEZONE", schema.DEFAULT_TZ)

    @property
    def chat_id(self) -> str:
        return self.env["TELEGRAM_CHAT_ID"]

    @property
    def control_jids(self) -> set[str]:
        return {j.strip() for j in self.env.get("EVI_WHATSAPP_CONTROL_JIDS", "").split(",") if j.strip()}

    def today(self) -> "datetime.date":
        return datetime.now(ZoneInfo(self.tz)).date()

    # ------------------------------------------------------------------ http
    def _http(self, method: str, url: str, body: dict | None = None, timeout: float = 30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {exc.read()[:300]!r}") from exc
        return json.loads(raw) if raw else None

    def fakes(self, method: str, path: str, body: dict | None = None):
        return self._http(method, self.fakes_url + path, body)

    def agent(self, method: str, path: str, body: dict | None = None, timeout: float = 300):
        return self._http(method, self.agent_url + path, body, timeout)

    # ---------------------------------------------------------------- docker
    def exec(self, service: str, *cmd: str, input_: str | None = None) -> str:
        proc = subprocess.run(
            [*COMPOSE, "exec", "-T", service, *cmd], input=input_, capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:
            raise RuntimeError(f"exec {service} {cmd[0]} failed: {proc.stderr.strip()[:300]}")
        return proc.stdout

    def psql(self, sql: str) -> str:
        return self.exec("postgres", "psql", "-U", "evisim", "-d", "evisim", "-At", "-c", sql)

    def set_clock(self, dt: datetime) -> None:
        """Write ``@YYYY-MM-DD HH:MM:SS`` (container-local TZ) atomically: libfaketime
        aborts on an empty/missing file, so write to a temp file and mv."""
        stamp = dt.astimezone(ZoneInfo(self.tz)).strftime("@%Y-%m-%d %H:%M:%S")
        self.exec("fakes", "sh", "-c", f"printf '%s' '{stamp}' > /sim/clock.tmp && mv /sim/clock.tmp /sim/clock")
        self._sim_clock = (dt, time.monotonic())

    def sim_now(self) -> datetime:
        """Current sim time (last set_clock + elapsed real time, as libfaketime ticks)."""
        if getattr(self, "_sim_clock", None) is None:
            return self.now()
        dt, mono = self._sim_clock
        return dt + timedelta(seconds=time.monotonic() - mono)

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(self.tz))


# --------------------------------------------------------------------------- result
@dataclass
class StepResult:
    index: int
    type: str
    latency_s: float | None = None
    reply: str | None = None
    failures: list[str] = field(default_factory=list)


@dataclass
class Result:
    scenario_id: str
    passed: bool = False
    failures: list[str] = field(default_factory=list)
    steps: list[StepResult] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    outbound: dict = field(default_factory=dict)
    duration_s: float = 0.0
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_reasoning: int = 0


# --------------------------------------------------------------------------- reset
def seed_workspace(ctx: Ctx, ws: str) -> None:
    """Copy the versioned bootstrap files (+ fictitious USER.md) into the sim workspace."""
    data = workspace_seed.build_tar(REPO_ROOT, REPO_ROOT / "tests" / "sim" / "workspace")
    proc = subprocess.run(
        [*COMPOSE, "exec", "-T", "agent-api", "tar", "-x", "-C", ws], input=data, capture_output=True, timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(f"workspace seed failed: {proc.stderr.decode(errors='replace').strip()[:300]}")


def reset_world(ctx: Ctx) -> None:
    ctx.fakes("POST", "/_sim/reset")
    tables = [t for t in ctx.psql("SELECT tablename FROM pg_tables WHERE schemaname='public'").split() if t]
    if tables:
        ctx.psql("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE")
    ctx.exec("agent-api", "sh", "-c", f"mkdir -p {AUDIT_LOG} && find {AUDIT_LOG} -type f -delete")
    for d in (ctx.env.get("EVI_WORKSPACE"), ctx.env.get("EVI_CONTACT_MEMORY_DIR")):
        if d and d.startswith("/tmp/evi-sim-"):  # only the sim container's own dirs
            ctx.exec("agent-api", "sh", "-c", f"mkdir -p '{d}' && find '{d}' -mindepth 1 -delete")
    ws = ctx.env.get("EVI_WORKSPACE")
    if ws and ws.startswith("/tmp/evi-sim-"):
        seed_workspace(ctx, ws)
    sessions = [f"telegram-{ctx.chat_id}"] + [f"whatsapp-{j}" for j in sorted(ctx.control_jids)]
    for sid in sessions:
        ctx.agent("POST", "/reset", {"session_id": sid}, timeout=30)


# --------------------------------------------------------------------------- observations
def tools_called(ctx: Ctx) -> list[str]:
    names: set[str] = set()
    try:
        raw = ctx.exec("agent-api", "sh", "-c", f"cat {AUDIT_LOG}/telegram.jsonl 2>/dev/null || true")
    except RuntimeError:
        raw = ""
    for line in raw.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        for t in entry.get("tools") or []:
            if t.get("kind") == "call" and t.get("tool"):
                names.add(t["tool"])
    names.update(n for n in ctx.psql("SELECT DISTINCT tool_name FROM session_tool_snapshots").split() if n)
    names.update(c["op"] for c in ctx.fakes("GET", "/_sim/calls") or [] if c.get("op"))
    return sorted(names)


def pg_count(ctx: Ctx, row: dict) -> int:
    table = row["table"]
    if table not in schema.PG_TABLES:
        raise RuntimeError(f"table {table!r} not allowed")
    clauses = []
    for col, val in (row.get("where") or {}).items():
        if val is None:
            clauses.append(f"{col} IS NULL")
        elif isinstance(val, bool):
            clauses.append(f"{col} = {'TRUE' if val else 'FALSE'}")
        elif isinstance(val, (int, float)):
            clauses.append(f"{col} = {val}")
        else:
            clauses.append(f"{col}::text = '{str(val).replace(chr(39), chr(39) * 2)}'")
    sql = f"SELECT count(*) FROM {table}" + (" WHERE " + " AND ".join(clauses) if clauses else "")
    return int(ctx.psql(sql).strip() or 0)


def observe(ctx: Ctx, step_obs: dict, exp: dict) -> dict:
    state = ctx.fakes("GET", "/_sim/state")
    obs = {
        "google": state["google"],
        "evolution_sent": state["evolution_sent"],
        "telegram_sent": state["telegram_sent"],
        "media_requests": state.get("media_requests") or [],
        "control_jids": ctx.control_jids,
        "chat_id": ctx.chat_id,
        "base": ctx.today(),
        "tz": ctx.tz,
        "tools_called": tools_called(ctx) if ("tools_called_any" in exp or "tools_not_called" in exp) else [],
        "postgres": [pg_count(ctx, r) for r in exp.get("postgres") or []],
    }
    obs.update(step_obs)
    return obs


# --------------------------------------------------------------------------- steps
def _wait_reply(ctx: Ctx, fetch, baseline: int, timeout_s: float) -> tuple[str | None, float | None]:
    """Poll ``fetch()`` (list of reply texts, in order) until a new one shows up."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        msgs = fetch()
        if len(msgs) > baseline:
            time.sleep(SETTLE_S)  # let multi-part replies land
            msgs = fetch()
            return "\n".join(msgs[baseline:]), time.monotonic() - t0
        time.sleep(0.5)
    return None, None


def _telegram_replies(ctx: Ctx) -> list[str]:
    sent = ctx.fakes("GET", "/_sim/telegram/sent") or []
    return [m.get("text", "") for m in sent if str(m.get("chat_id")) == str(ctx.chat_id)]


def _control_replies(ctx: Ctx) -> list[str]:
    sent = ctx.fakes("GET", "/_sim/evolution/sent") or []
    return [m.get("text", "") for m in sent if m.get("jid") in ctx.control_jids]


def build_webhook_payload(
    text: str,
    jid: str,
    *,
    from_me: bool = False,
    group: bool = False,
    push_name: str = "Sim",
    ts: int | None = None,
    audio_seconds: int | None = None,
) -> dict:
    payload = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
    msg = payload["data"]["messages"][0]
    msg["key"] = {"id": f"SIM{uuid.uuid4().hex[:16].upper()}", "remoteJid": GROUP_JID if group else jid, "fromMe": from_me}
    if group:
        msg["key"]["participant"] = jid
    msg["messageTimestamp"] = int(ts if ts is not None else time.time())
    if audio_seconds is not None:  # voice note: audioMessage instead of text
        msg["message"] = {"audioMessage": {"mimetype": "audio/ogg; codecs=opus", "seconds": int(audio_seconds), "ptt": True}}
    else:
        msg["message"] = {"conversation": text}
    msg["pushName"] = push_name
    return payload


def _audio_b64(name: str) -> str:
    import base64

    path = AUDIO_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"audio fixture not found: {path}")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _voice_webhook(ctx: Ctx, jid: str, v: dict, *, push_name: str = "Sim") -> None:
    """Register the audio in the fake Evolution under a fresh message id and POST the audioMessage webhook."""
    seconds = int(v.get("duration_s") or DEFAULT_VOICE_SECONDS)
    payload = build_webhook_payload("", jid, push_name=push_name, ts=ctx.sim_now().timestamp(), audio_seconds=seconds)
    mid = payload["data"]["messages"][0]["key"]["id"]
    ctx.fakes("POST", "/_sim/evolution/media", {"id": mid, "audio_b64": _audio_b64(v["file"])})
    ctx.agent("POST", "/webhooks/evolution", payload)


def run_step(ctx: Ctx, scn: Scenario, idx: int, step: Step) -> StepResult:
    sr = StepResult(idx, step.type)
    exp = step.expect
    step_obs: dict = {}
    timeout = float(exp.get("reply_within_s") or DEFAULT_REPLY_TIMEOUT_S)
    if exp.get("no_reply"):
        timeout = float(exp.get("no_reply_window_s") or schema.DEFAULT_NO_REPLY_WINDOW_S)
    t0 = time.monotonic()
    if step.type == "telegram":
        base = len(_telegram_replies(ctx))
        ctx.fakes("POST", "/_sim/telegram/updates", {"text": step.value})
        sr.reply, sr.latency_s = _wait_reply(ctx, lambda: _telegram_replies(ctx), base, timeout)
    elif step.type == "telegram_voice":
        base = len(_telegram_replies(ctx))
        body = {"audio_b64": _audio_b64(step.value["file"]), "duration_s": int(step.value.get("duration_s") or DEFAULT_VOICE_SECONDS)}
        ctx.fakes("POST", "/_sim/telegram/voice", body)
        sr.reply, sr.latency_s = _wait_reply(ctx, lambda: _telegram_replies(ctx), base, timeout)
    elif step.type in ("whatsapp_control_voice", "whatsapp_contact_voice"):
        base = len(_control_replies(ctx))
        if step.type == "whatsapp_control_voice":
            _voice_webhook(ctx, sorted(ctx.control_jids)[0], step.value)
        else:
            _voice_webhook(ctx, step.value.get("jid", DEFAULT_CONTACT_JID), step.value, push_name=step.value.get("push_name", "Sim"))
        waits = step.type == "whatsapp_control_voice" and bool({"reply_within_s", "reply_matches", "reply_not_matches", "no_reply"} & set(exp))
        if waits:
            sr.reply, sr.latency_s = _wait_reply(ctx, lambda: _control_replies(ctx), base, timeout)
        else:
            time.sleep(SETTLE_S)
            sr.latency_s = time.monotonic() - t0
    elif step.type in ("whatsapp_control", "whatsapp_contact"):
        if step.type == "whatsapp_control":
            jid, kw, text = sorted(ctx.control_jids)[0], {}, step.value
        else:
            v = step.value if isinstance(step.value, dict) else {"text": step.value}
            jid, text = v.get("jid", DEFAULT_CONTACT_JID), v["text"]
            kw = {"from_me": bool(v.get("from_me")), "group": bool(v.get("group")), "push_name": v.get("push_name", "Sim")}
        base = len(_control_replies(ctx))
        ctx.agent("POST", "/webhooks/evolution", build_webhook_payload(text, jid, ts=ctx.sim_now().timestamp(), **kw))
        if step.type == "whatsapp_control" and ("reply_within_s" in exp or exp.get("no_reply")):
            sr.reply, sr.latency_s = _wait_reply(ctx, lambda: _control_replies(ctx), base, timeout)
        else:
            time.sleep(SETTLE_S)
            sr.latency_s = time.monotonic() - t0
    elif step.type == "clock":
        v = str(step.value)
        base = len(_telegram_replies(ctx))
        if schema.is_relative(v):
            ctx.set_clock(schema.parse_relative(v, ctx.today(), ctx.tz))
        else:
            ctx.set_clock(ctx.now() + schema.parse_delta(v))
        if "reply_within_s" in exp or exp.get("no_reply"):
            # proactive output (e.g. the reminder loop): messages sent to the user after the jump
            t0 = time.monotonic()
            sr.reply, sr.latency_s = _wait_reply(ctx, lambda: _telegram_replies(ctx), base, timeout)
    elif step.type == "job":
        base = len(_telegram_replies(ctx))
        ctx.agent("POST", f"/jobs/{step.value}", {})
        sr.latency_s = time.monotonic() - t0
        # a job's observable output is what it sent to the user's Telegram chat
        # (so reply_matches/reply_within_s can assert the delivered text)
        sent = _telegram_replies(ctx)[base:]
        sr.reply = "\n".join(sent) if sent else None
    elif step.type == "fault":
        if "windmill" in step.value:
            f = step.value["windmill"]
            if f == "clear":
                ctx.fakes("DELETE", "/_sim/faults")
            else:
                ctx.fakes("POST", "/_sim/faults", f)
        if "telegram" in step.value:
            ctx.fakes("POST", "/_sim/telegram/faults", step.value["telegram"])
    if exp:
        step_obs = {"reply": sr.reply, "latency_s": sr.latency_s}
        sr.failures = schema.eval_expect(exp, observe(ctx, step_obs, exp))
    return sr


def llm_call_count(ctx: Ctx) -> int:
    try:
        out = ctx.exec("agent-api", "sh", "-c", f"cat {LLM_COUNT_FILE} 2>/dev/null | wc -l")
        return int(out.strip() or 0)
    except (RuntimeError, ValueError):
        return 0


def llm_usage_totals(ctx: Ctx) -> tuple[int, int, int]:
    """Cumulative (in, out, reasoning) tokens recorded by the in-container counter."""
    tin = tout = treason = 0
    try:
        raw = ctx.exec("agent-api", "sh", "-c", f"cat {LLM_USAGE_FILE} 2>/dev/null")
    except RuntimeError:
        return 0, 0, 0
    for line in raw.splitlines():
        try:
            d = json.loads(line)
            tin += int(d.get("in") or 0)
            tout += int(d.get("out") or 0)
            treason += int(d.get("reasoning") or 0)
        except (ValueError, TypeError, AttributeError):
            continue
    return tin, tout, treason


def cassette_begin(ctx: Ctx, scn_id: str) -> None:
    """Tell the agent which cassette is active (new nonce per attempt); in replay, ship the file in."""
    if ctx.llm_mode == "live":
        return
    ctx.exec("agent-api", "sh", "-c", f"mkdir -p {CASSETTE_DIR} && rm -f {CASSETTE_DIR}/stale.log {CASSETTE_DIR}/ctl {CASSETTE_DIR}/{scn_id}.jsonl")
    if ctx.llm_mode == "replay":
        host = CASSETTES_HOST_DIR / f"{scn_id}.jsonl"
        if not host.exists():
            raise RuntimeError(f"cassette stale: regrave com --llm record (no cassette for {scn_id})")
        ctx.exec("agent-api", "sh", "-c", f"cat > {CASSETTE_DIR}/{scn_id}.jsonl", input_=host.read_text(encoding="utf-8"))
    ctl = json.dumps({"id": scn_id, "nonce": uuid.uuid4().hex})
    ctx.exec("agent-api", "sh", "-c", f"cat > {CASSETTE_DIR}/ctl", input_=ctl)


def cassette_end(ctx: Ctx, scn_id: str, res: "Result") -> None:
    """Surface stale-cassette errors as the failure reason; in record, save a passing attempt."""
    if ctx.llm_mode == "live":
        return
    stale = ctx.exec("agent-api", "sh", "-c", f"cat {CASSETTE_DIR}/stale.log 2>/dev/null || true").strip()
    if stale:
        first = stale.splitlines()[0]
        n = len(stale.splitlines())
        res.failures.insert(0, first + (f" (+{n - 1} more)" if n > 1 else ""))
    elif ctx.llm_mode == "record" and not res.failures:
        data = ctx.exec("agent-api", "sh", "-c", f"cat {CASSETTE_DIR}/{scn_id}.jsonl 2>/dev/null || true")
        # deterministic scenarios (e.g. a briefing-only flow) make no LLM calls: keep an empty
        # cassette so replay still has a file to ship (any unexpected call is then stale)
        CASSETTES_HOST_DIR.mkdir(parents=True, exist_ok=True)
        (CASSETTES_HOST_DIR / f"{scn_id}.jsonl").write_text(data, encoding="utf-8")


def run_scenario(scn: Scenario, ctx: Ctx) -> Result:
    res = Result(scn.id)
    t0 = time.monotonic()
    calls0 = llm_call_count(ctx)
    usage0 = llm_usage_totals(ctx)
    try:
        cassette_begin(ctx, scn.id)
        reset_world(ctx)
        base = ctx.today()
        ctx.set_clock(schema.parse_relative(scn.clock, base, ctx.tz) if scn.clock else ctx.now())
        seed = schema.resolve_seed(scn.seed, base, ctx.tz)
        if seed:
            ctx.fakes("POST", "/_sim/seed", {"google": {k: v for k, v in seed.items() if k != "evolution"}, **({"evolution": seed["evolution"]} if "evolution" in seed else {})})
        for i, step in enumerate(scn.steps):
            sr = run_step(ctx, scn, i, step)
            res.steps.append(sr)
            res.failures += [f"step {i} ({step.type}): {f}" for f in sr.failures]
        state = ctx.fakes("GET", "/_sim/state")
        res.outbound = {
            "evolution_sent": len(state["evolution_sent"]),
            "telegram_sent": len(state["telegram_sent"]),
            "third_parties": schema.count_third_party_outbound(
                state["evolution_sent"], state["telegram_sent"], ctx.control_jids, ctx.chat_id
            ),
        }
        res.tools_called = tools_called(ctx)
    except Exception as exc:  # infra error = failure with the reason, not a crash
        res.failures.append(f"runner error: {type(exc).__name__}: {exc}")
    try:
        cassette_end(ctx, scn.id, res)
    except Exception as exc:
        res.failures.append(f"runner error (cassette): {type(exc).__name__}: {exc}")
    res.duration_s = time.monotonic() - t0
    res.llm_calls = max(0, llm_call_count(ctx) - calls0)
    usage1 = llm_usage_totals(ctx)
    res.tokens_in, res.tokens_out, res.tokens_reasoning = (max(0, b - a) for a, b in zip(usage0, usage1))
    res.passed = not res.failures
    return res


# --------------------------------------------------------------------------- CLI
def _csv(v: str | None) -> list[str] | None:
    return [x.strip() for x in v.split(",") if x.strip()] if v else None


def cmd_run(args: argparse.Namespace) -> int:
    if args.llm not in LLM_MODES:
        print(f"evi-sim: --llm must be one of {', '.join(LLM_MODES)}", file=sys.stderr)
        return 2
    if args.repeat < 1:
        print("evi-sim: --repeat must be >= 1", file=sys.stderr)
        return 2
    try:
        scenarios = schema.load_scenarios(args.scenarios_dir, tags=_csv(args.tag), ids=_csv(args.id))
    except schema.ScenarioError as exc:
        print(f"evi-sim: {exc}", file=sys.stderr)
        return 2
    if not scenarios:
        print("evi-sim: no scenarios matched", file=sys.stderr)
        return 2
    ctx = Ctx(llm_mode=args.llm)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    records: list[dict] = []
    total_calls = 0
    budget_hit = False
    for scn in scenarios:
        for n in range(1, args.repeat + 1):
            label = f"{scn.id}" + (f" #{n}" if args.repeat > 1 else "")
            if args.max_llm_calls and total_calls >= args.max_llm_calls:
                budget_hit = True
                records.append(report.skipped_record(scn.id, scn.tags, n))
                print(f"SKIP {label} (budget: {total_calls}/{args.max_llm_calls} LLM calls)")
                continue
            res = run_scenario(scn, ctx)
            total_calls += res.llm_calls
            records.append(report.attempt_record(scn.id, scn.tags, n, res))
            print(f"{'PASS' if res.passed else 'FAIL'} {label} ({res.duration_s:.1f}s, {res.llm_calls} LLM calls, {res.tokens_in} in / {res.tokens_out} out tok)")
            for f in res.failures:
                print(f"    - {f}")
    summary = report.summarize(records, args.repeat)
    meta = {"ts": ts, "repeat": args.repeat, "max_llm_calls": args.max_llm_calls, "llm_calls": total_calls, "budget_hit": budget_hit}
    jsonl, md = report.write_reports(records, summary, meta, SIM_LOG_DIR, ts)
    print(report.console_summary(summary, meta, records))
    print(f"report: {jsonl}\n        {md}")
    return 0 if summary["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m testing.sim.runner")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--tag")
    r.add_argument("--id")
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--llm", default="live")
    r.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS)
    r.add_argument("--scenarios-dir", default=str(DEFAULT_SCENARIOS_DIR))
    rp = sub.add_parser("report")
    rp.add_argument("path", nargs="?")
    args = p.parse_args(argv)
    if args.cmd == "report":
        return report.cmd_report(args.path, SIM_LOG_DIR)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
