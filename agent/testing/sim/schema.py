"""YAML scenario schema for the evi-sim harness.

Pure module (no network): parsing/validation, relative dates (``D0 09:12``,
``D-1``) and the *expectation evaluation* functions the runner applies to
observed state. Scenarios assert state and effects, not wording (SCN-SIM-04):
reply text is only checked through an explicit ``reply_matches`` regex.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/Sao_Paulo"
SOURCES = ("real-usage", "failure", "adversarial", "synthetic")
STEP_TYPES = (
    "telegram",
    "whatsapp_control",
    "whatsapp_contact",
    "telegram_voice",
    "telegram_tap",
    "whatsapp_control_voice",
    "whatsapp_contact_voice",
    "clock",
    "job",
    "fault",
)
VOICE_STEPS = ("telegram_voice", "whatsapp_control_voice", "whatsapp_contact_voice")
AUDIO_FIXTURE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")  # name inside tests/fixtures/audio/
JOBS = ("heartbeat", "daily-summary", "briefing", "contact-learn", "contact-names-sync", "probe")
# agent tables a scenario may inspect via expect.postgres (never free-form SQL)
PG_TABLES = ("pending_commitments", "whatsapp_contacts", "messages", "session_tool_snapshots", "turn_log", "probe_log", "reminders", "reminder_fires", "wa_conversation_state", "briefing_log")

TOP_KEYS = {"id", "title", "tags", "source", "clock", "seed", "steps", "judge", "description"}
STEP_KEYS = set(STEP_TYPES) | {"expect", "judge"}
EXPECT_KEYS = {
    "reply_within_s",
    "reply_matches",
    "reply_not_matches",
    "calendar",
    "tasks",
    "gmail",
    "tools_called_any",
    "tools_not_called",
    "outbound_to_third_parties",
    "media_requests",
    "evolution_requests",
    "postgres",
    "max_latency_s",
    "no_reply",
    "no_reply_window_s",
    "messages_min",
    "telegram_sent_count_matching",
    "telegram_message",
    "telegram_keyboard",
    "contact_profile",
    "job_response_matches",
    "judge",
}
EVOLUTION_ENDPOINTS = ("chat/findMessages", "chat/findChats", "chat/findContacts", "chat/fetchProfile", "chat/getBase64FromMediaMessage", "message/sendText")
DEFAULT_NO_REPLY_WINDOW_S = 15
TELEGRAM_MESSAGE_KEYS = {"parse_mode", "valid_html", "matches", "not_matches", "max_lines", "has_keyboard", "callback_data_matches", "callback_data_max_bytes"}
TAP_KEYS = {"item", "action", "from_chat", "briefing"}
TAP_ACTIONS = ("ok", "no", "up", "dn")
HTML_TAGS = ("b", "i", "code")  # the only tags a valid_html message may use
CALENDAR_KEYS = {"created", "count"}
TASKS_KEYS = {"created", "count"}
GMAIL_KEYS = {"deleted_count", "deleted_ids_include", "not_deleted"}
SEED_KEYS = {"calendar", "tasks", "gmail", "calendars", "evolution", "contacts"}

_REL_RE = re.compile(r"^\s*([DM])(-?\d+)(?:\s+(\d{1,2}):(\d{2}))?\s*$")
_DELTA_RE = re.compile(r"^\s*\+(\d+)\s*([smhd])\s*$")


class ScenarioError(ValueError):
    """Invalid scenario (message names file and key)."""


# --------------------------------------------------------------------------- dates
def is_relative(value: Any) -> bool:
    return isinstance(value, str) and bool(_REL_RE.match(value))


def sim_base_date() -> date | None:
    """``EVI_SIM_BASE_DATE`` (YYYY-MM-DD) pins the sim calendar; unset -> the real day."""
    raw = os.getenv("EVI_SIM_BASE_DATE")
    return date.fromisoformat(raw) if raw else None


def parse_relative(value: str, base: date, tz: str | ZoneInfo = DEFAULT_TZ) -> datetime:
    """``"D1 10:00"`` / ``"D-1"`` -> aware datetime in ``tz``.

    ``M<n>`` counts Mondays instead of days: ``M0`` is the latest Monday on or before ``base``,
    ``M1`` the next one (for weekly flows such as the Monday briefing).

    Day arithmetic is done on the calendar date and the wall-clock time is attached
    afterwards, so DST transitions never shift the wall time. ``"Dn"`` alone is 00:00.
    """
    m = _REL_RE.match(value or "")
    if not m:
        raise ValueError(f"invalid relative date {value!r} (expected 'D<n> HH:MM' or 'D<n>')")
    zone = tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)
    if m.group(1) == "M":
        day = base - timedelta(days=base.weekday()) + timedelta(weeks=int(m.group(2)))
    else:
        day = base + timedelta(days=int(m.group(2)))
    hh, mm = int(m.group(3) or 0), int(m.group(4) or 0)
    if hh > 23 or mm > 59:
        raise ValueError(f"invalid time in {value!r}")
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=zone)


def parse_delta(value: str) -> timedelta:
    m = _DELTA_RE.match(value or "")
    if not m:
        raise ValueError(f"invalid clock delta {value!r} (expected '+<n>s|m|h|d')")
    n = int(m.group(1))
    return timedelta(**{{"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[m.group(2)]: n})


def resolve_seed(seed: dict, base: date, tz: str | ZoneInfo = DEFAULT_TZ) -> dict:
    """Replace relative dates in a seed by ISO strings the fakes understand."""

    def conv(v: Any, *, date_only_ok: bool) -> Any:
        if not is_relative(v):
            return v
        dt = parse_relative(v, base, tz)
        if date_only_ok and not re.search(r"\d:\d\d", v):
            return dt.date().isoformat()
        return dt.isoformat()

    out: dict[str, Any] = {}
    for key, items in (seed or {}).items():
        if key in ("calendar", "tasks", "gmail") and isinstance(items, list):
            rows = []
            for it in items:
                it = dict(it)
                for f in ("start", "end", "due", "date"):
                    if f in it:
                        it[f] = conv(it[f], date_only_ok=True)
                rows.append(it)
            out[key] = rows
        else:
            out[key] = items
    return out


# --------------------------------------------------------------------------- model
@dataclass
class Step:
    type: str
    value: Any
    expect: dict = field(default_factory=dict)


@dataclass
class Scenario:
    id: str
    title: str
    tags: list[str]
    source: str
    clock: str | None
    seed: dict
    steps: list[Step]
    path: str = ""
    judge: Any = None  # accepted, ignored (LLM-as-judge is off)


def _err(path: str, where: str, msg: str) -> ScenarioError:
    return ScenarioError(f"{path}: {where}: {msg}")


def _check_keys(d: Any, allowed: set[str], path: str, where: str) -> None:
    if not isinstance(d, dict):
        raise _err(path, where, "must be a mapping")
    for k in d:
        if k not in allowed:
            raise _err(path, f"{where}.{k}" if where else str(k), f"unknown key (allowed: {', '.join(sorted(allowed))})")


def _validate_expect(exp: Any, path: str, where: str, step_type: str = "") -> dict:
    if exp is None:
        return {}
    _check_keys(exp, EXPECT_KEYS, path, where)
    if "no_reply_window_s" in exp and not exp.get("no_reply"):
        raise _err(path, f"{where}.no_reply_window_s", "only valid together with no_reply: true")
    if exp.get("no_reply"):
        if step_type not in ("telegram", "whatsapp_control", "telegram_voice", "telegram_tap", "whatsapp_control_voice", "clock"):
            raise _err(path, f"{where}.no_reply", "only valid on telegram(_voice|_tap)/whatsapp_control(_voice)/clock steps")
        if "reply_within_s" in exp or "reply_matches" in exp or "reply_not_matches" in exp:
            raise _err(path, where, "no_reply cannot be combined with reply_within_s/reply_matches")
    for key, allowed in (("calendar", CALENDAR_KEYS), ("tasks", TASKS_KEYS), ("gmail", GMAIL_KEYS)):
        if key in exp:
            _check_keys(exp[key], allowed, path, f"{where}.{key}")
    if "media_requests" in exp and (not isinstance(exp["media_requests"], int) or isinstance(exp["media_requests"], bool)):
        raise _err(path, f"{where}.media_requests", "must be an integer (expected count of media fetches)")
    if "evolution_requests" in exp:
        er = exp["evolution_requests"]
        if not isinstance(er, dict) or not er or not all(
            k in EVOLUTION_ENDPOINTS and isinstance(v, int) and not isinstance(v, bool) and v >= 0 for k, v in er.items()
        ):
            raise _err(path, f"{where}.evolution_requests", f"must map endpoints {EVOLUTION_ENDPOINTS} to expected request counts (>= 0) made during the step")
    if "messages_min" in exp and (not isinstance(exp["messages_min"], int) or isinstance(exp["messages_min"], bool) or exp["messages_min"] < 1):
        raise _err(path, f"{where}.messages_min", "must be a positive integer (messages to wait for in this step)")
    if "telegram_sent_count_matching" in exp:
        tm = exp["telegram_sent_count_matching"]
        _check_keys(tm, {"regex", "count"}, path, f"{where}.telegram_sent_count_matching")
        if not isinstance(tm.get("count"), int) or isinstance(tm.get("count"), bool) or "regex" not in tm:
            raise _err(path, f"{where}.telegram_sent_count_matching", "needs 'regex' and integer 'count'")
        try:
            re.compile(tm["regex"])
        except (re.error, TypeError) as exc:
            raise _err(path, f"{where}.telegram_sent_count_matching.regex", f"invalid regex: {exc}") from exc
    if "telegram_message" in exp:
        tg = exp["telegram_message"]
        _check_keys(tg, TELEGRAM_MESSAGE_KEYS, path, f"{where}.telegram_message")
        if "max_lines" in tg and (not isinstance(tg["max_lines"], int) or isinstance(tg["max_lines"], bool) or tg["max_lines"] < 1):
            raise _err(path, f"{where}.telegram_message.max_lines", "must be a positive integer")
        for rk in ("matches", "not_matches"):
            if rk in tg:
                try:
                    re.compile(tg[rk])
                except (re.error, TypeError) as exc:
                    raise _err(path, f"{where}.telegram_message.{rk}", f"invalid regex: {exc}") from exc
    if "telegram_message" in exp:
        tg = exp["telegram_message"]
        if "callback_data_matches" in tg:
            try:
                re.compile(tg["callback_data_matches"])
            except (re.error, TypeError) as exc:
                raise _err(path, f"{where}.telegram_message.callback_data_matches", f"invalid regex: {exc}") from exc
    if "telegram_keyboard" in exp:
        tk = exp["telegram_keyboard"]
        _check_keys(tk, {"contains", "not_contains"}, path, f"{where}.telegram_keyboard")
        if not tk:
            raise _err(path, f"{where}.telegram_keyboard", "needs 'contains' and/or 'not_contains'")
        for k in tk:
            try:
                re.compile(tk[k])
            except (re.error, TypeError) as exc:
                raise _err(path, f"{where}.telegram_keyboard.{k}", f"invalid regex: {exc}") from exc
    if "contact_profile" in exp:
        cp = exp["contact_profile"]
        _check_keys(cp, {"jid", "section", "matches", "not_matches"}, path, f"{where}.contact_profile")
        if not isinstance(cp.get("jid"), str) or not ({"matches", "not_matches"} & set(cp)):
            raise _err(path, f"{where}.contact_profile", "needs 'jid' and 'matches' and/or 'not_matches'")
        for k in ("matches", "not_matches"):
            if k in cp:
                try:
                    re.compile(cp[k])
                except (re.error, TypeError) as exc:
                    raise _err(path, f"{where}.contact_profile.{k}", f"invalid regex: {exc}") from exc
    for key in ("tools_called_any", "tools_not_called"):
        if key in exp and not isinstance(exp[key], list):
            raise _err(path, f"{where}.{key}", "must be a list")
    if "job_response_matches" in exp:
        if step_type != "job":
            raise _err(path, f"{where}.job_response_matches", "only valid on job steps")
        try:
            re.compile(exp["job_response_matches"])
        except (re.error, TypeError) as exc:
            raise _err(path, f"{where}.job_response_matches", f"invalid regex: {exc}") from exc
    if "reply_matches" in exp:
        try:
            re.compile(exp["reply_matches"])
        except (re.error, TypeError) as exc:
            raise _err(path, f"{where}.reply_matches", f"invalid regex: {exc}") from exc
    if "reply_not_matches" in exp:
        try:
            re.compile(exp["reply_not_matches"])
        except (re.error, TypeError) as exc:
            raise _err(path, f"{where}.reply_not_matches", f"invalid regex: {exc}") from exc
    for i, row in enumerate(exp.get("postgres") or []):
        _check_keys(row, {"table", "where", "count", "within_s"}, path, f"{where}.postgres[{i}]")
        if row.get("table") not in PG_TABLES:
            raise _err(path, f"{where}.postgres[{i}].table", f"not in allowlist {PG_TABLES}")
        if "count" not in row:
            raise _err(path, f"{where}.postgres[{i}]", "missing 'count'")
        w = row.get("where") or {}
        if not isinstance(w, dict) or not all(re.fullmatch(r"[a-z_]+", str(k)) for k in w):
            raise _err(path, f"{where}.postgres[{i}].where", "must map column names to values")
        for col, val in w.items():
            if isinstance(val, dict) and not (len(val) == 1 and ("contains" in val or "weekday" in val)):
                raise _err(path, f"{where}.postgres[{i}].where.{col}", "mapping value must be {contains: str} or {weekday: 1-7}")
            if isinstance(val, dict) and "weekday" in val and val["weekday"] not in range(1, 8):
                raise _err(path, f"{where}.postgres[{i}].where.{col}", "weekday must be 1-7 (ISO)")
        if "within_s" in row and (isinstance(row["within_s"], bool) or not isinstance(row["within_s"], (int, float)) or row["within_s"] < 0):
            raise _err(path, f"{where}.postgres[{i}].within_s", "must be a non-negative number of seconds")
    for key, rows in (("calendar", "created"), ("tasks", "created")):
        for j, item in enumerate((exp.get(key) or {}).get(rows) or []):
            allowed = {"summary_contains", "start", "end"} if key == "calendar" else {"title_contains", "due"}
            _check_keys(item, allowed, path, f"{where}.{key}.{rows}[{j}]")
    return exp


def parse_scenario(data: Any, path: str = "<memory>") -> Scenario:
    _check_keys(data, TOP_KEYS, path, "")
    for req in ("id", "steps"):
        if req not in data:
            raise _err(path, req, "required key missing")
    source = data.get("source", "synthetic")
    if source not in SOURCES:
        raise _err(path, "source", f"must be one of {SOURCES}")
    clock = data.get("clock")
    if clock is not None and not is_relative(clock):
        raise _err(path, "clock", "must be 'D<n> HH:MM'")
    seed = data.get("seed") or {}
    _check_keys(seed, SEED_KEYS, path, "seed")
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        raise _err(path, "tags", "must be a list")
    raw_steps = data["steps"]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise _err(path, "steps", "must be a non-empty list")
    steps: list[Step] = []
    for i, st in enumerate(raw_steps):
        where = f"steps[{i}]"
        _check_keys(st, STEP_KEYS, path, where)
        kinds = [k for k in STEP_TYPES if k in st]
        if len(kinds) != 1:
            raise _err(path, where, f"must have exactly one step type of {STEP_TYPES}, got {kinds or 'none'}")
        kind = kinds[0]
        value = st[kind]
        if kind == "clock":
            if not (is_relative(value) or _DELTA_RE.match(str(value))):
                raise _err(path, f"{where}.clock", "must be 'D<n> HH:MM' or '+<n>s|m|h|d'")
        elif kind == "job" and value not in JOBS:
            raise _err(path, f"{where}.job", f"must be one of {JOBS}")
        elif kind in ("telegram", "whatsapp_control") and not isinstance(value, str):
            raise _err(path, f"{where}.{kind}", "must be a string")
        elif kind == "telegram_tap":
            _check_keys(value, TAP_KEYS, path, f"{where}.{kind}")
            if value.get("action") not in TAP_ACTIONS:
                raise _err(path, f"{where}.{kind}.action", f"must be one of {TAP_ACTIONS}")
            item = value.get("item")
            if value["action"] in ("ok", "no") and (not isinstance(item, int) or isinstance(item, bool) or item < 1):
                raise _err(path, f"{where}.{kind}.item", "must be a positive integer for ok/no")
            if "from_chat" in value and (isinstance(value["from_chat"], bool) or not isinstance(value["from_chat"], (int, str))):
                raise _err(path, f"{where}.{kind}.from_chat", "must be a chat id")
            if value.get("briefing", "last") not in ("last", "first"):
                raise _err(path, f"{where}.{kind}.briefing", "must be 'last' or 'first'")
        elif kind == "whatsapp_contact":
            if isinstance(value, dict):
                _check_keys(value, {"text", "jid", "from_me", "group", "push_name"}, path, f"{where}.{kind}")
            elif not isinstance(value, str):
                raise _err(path, f"{where}.{kind}", "must be a string or mapping")
        elif kind in VOICE_STEPS:
            allowed = {"file", "duration_s"} if kind != "whatsapp_contact_voice" else {"file", "duration_s", "jid", "push_name"}
            if not isinstance(value, dict):
                raise _err(path, f"{where}.{kind}", "must be a mapping with 'file'")
            _check_keys(value, allowed, path, f"{where}.{kind}")
            if not isinstance(value.get("file"), str) or not AUDIO_FIXTURE_RE.match(value["file"]):
                raise _err(path, f"{where}.{kind}.file", "must be a file name inside tests/fixtures/audio/")
            if "duration_s" in value and (not isinstance(value["duration_s"], int) or isinstance(value["duration_s"], bool) or value["duration_s"] <= 0):
                raise _err(path, f"{where}.{kind}.duration_s", "must be a positive integer")
        elif kind == "fault":
            _check_keys(value, {"windmill", "telegram"}, path, f"{where}.fault")
        if isinstance(st.get("expect"), dict) and "todo" in st["expect"]:
            raise _err(path, f"{where}.expect", f"scenario {data['id']} has TODO expect — fill it before running")
        steps.append(Step(kind, value, _validate_expect(st.get("expect"), path, f"{where}.expect", kind)))
    return Scenario(
        id=str(data["id"]),
        title=str(data.get("title") or data["id"]),
        tags=[str(t) for t in tags],
        source=source,
        clock=clock,
        seed=seed,
        steps=steps,
        path=path,
        judge=data.get("judge"),
    )


def load_file(path: Path) -> Scenario:
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScenarioError(f"{path}: invalid YAML: {exc}") from exc
    return parse_scenario(data, str(path))


def load_scenarios(
    directory: str | Path, tags: list[str] | None = None, ids: list[str] | None = None
) -> list[Scenario]:
    out: list[Scenario] = []
    seen: dict[str, str] = {}
    for p in sorted(Path(directory).rglob("*.y*ml")):
        if p.suffix not in (".yaml", ".yml"):
            continue
        scn = load_file(p)
        if scn.id in seen:
            raise ScenarioError(f"{p}: duplicate scenario id {scn.id!r} (also in {seen[scn.id]})")
        seen[scn.id] = str(p)
        if ids and scn.id not in ids:
            continue
        if tags and not set(tags) & set(scn.tags):
            continue
        out.append(scn)
    return out


# --------------------------------------------------------------------------- evaluation
def _to_dt(value: str, tz: ZoneInfo) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def eval_calendar(exp: dict, google: dict, base: date, tz: str | ZoneInfo = DEFAULT_TZ) -> list[str]:
    zone = tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)
    fails: list[str] = []
    created = (google.get("created") or {}).get("calendar") or []
    for want in exp.get("created") or []:
        sub = str(want.get("summary_contains", "")).lower()
        cands = [e for e in created if sub in str(e.get("summary", "")).lower()]
        if not cands:
            fails.append(f"calendar.created: no event with summary containing {sub!r} (created: {[e.get('summary') for e in created]})")
            continue
        for fld in ("start", "end"):
            if fld not in want:
                continue
            exp_dt = parse_relative(want[fld], base, zone)
            ok = any(
                (g := _to_dt(e.get(fld), zone)) is not None and g == exp_dt for e in cands
            )
            if not ok:
                got = [e.get(fld) for e in cands]
                fails.append(f"calendar.created {sub!r}: {fld} expected {exp_dt.isoformat()} got {got}")
    if "count" in exp:
        n = len(google.get("calendar") or [])
        if n != exp["count"]:
            fails.append(f"calendar.count: expected {exp['count']} got {n}")
    return fails


def eval_tasks(exp: dict, google: dict, base: date, tz: str | ZoneInfo = DEFAULT_TZ) -> list[str]:
    fails: list[str] = []
    created = (google.get("created") or {}).get("tasks") or []
    for want in exp.get("created") or []:
        sub = str(want.get("title_contains", "")).lower()
        cands = [t for t in created if sub in str(t.get("title", "")).lower()]
        if not cands:
            fails.append(f"tasks.created: no task with title containing {sub!r} (created: {[t.get('title') for t in created]})")
            continue
        if "due" in want:
            exp_day = parse_relative(want["due"], base, tz).date().isoformat()
            got = [str(t.get("due", ""))[:10] for t in cands]
            if exp_day not in got:
                fails.append(f"tasks.created {sub!r}: due expected {exp_day} got {got}")
    if "count" in exp:
        n = len(google.get("tasks") or [])
        if n != exp["count"]:
            fails.append(f"tasks.count: expected {exp['count']} got {n}")
    return fails


def eval_gmail(exp: dict, google: dict) -> list[str]:
    fails: list[str] = []
    deleted = list(google.get("deleted") or [])
    if "deleted_count" in exp and len(deleted) != exp["deleted_count"]:
        fails.append(f"gmail.deleted_count: expected {exp['deleted_count']} got {len(deleted)}")
    for mid in exp.get("deleted_ids_include") or []:
        if mid not in deleted:
            fails.append(f"gmail.deleted_ids_include: {mid} not deleted (deleted: {deleted})")
    for mid in exp.get("not_deleted") or []:
        if mid in deleted:
            fails.append(f"gmail.not_deleted: {mid} was deleted")
    return fails


def count_third_party_outbound(
    evolution_sent: list[dict], telegram_sent: list[dict], control_jids: set[str], chat_id: str | int
) -> int:
    n = sum(1 for m in evolution_sent if m.get("jid") not in control_jids)
    n += sum(1 for m in telegram_sent if str(m.get("chat_id")) != str(chat_id))
    return n


def profile_section(text: str, section: str | None) -> str:
    """Body of ``## <section>`` in a profile.md (whole text when ``section`` is None)."""
    if not section:
        return text
    body: list[str] | None = None
    for line in (text or "").splitlines():
        if line.startswith("## "):
            if body is not None:
                break
            if line[3:].strip() == section:
                body = []
        elif body is not None:
            body.append(line)
    return "\n".join(body or [])


def eval_contact_profile(exp: dict, text: str | None) -> list[str]:
    """``expect.contact_profile``: regexes (case-insensitive) over the contact's profile.md or one section."""
    if text is None:
        return ["contact_profile: profile.md not found for the contact"]
    sec = profile_section(text, exp.get("section"))
    where = f"profile.md{' ## ' + exp['section'] if exp.get('section') else ''}"
    fails: list[str] = []
    if "matches" in exp and not re.search(exp["matches"], sec, re.S | re.I):
        fails.append(f"contact_profile: /{exp['matches']}/ did not match {where}")
    if "not_matches" in exp and re.search(exp["not_matches"], sec, re.S | re.I):
        fails.append(f"contact_profile: /{exp['not_matches']}/ matched {where}")
    return fails


_TAG_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)[^<>]*>")


def html_problems(text: str) -> list[str]:
    """Why ``text`` is not valid Telegram HTML limited to <b>/<i>/<code> ([] when valid)."""
    problems: list[str] = []
    stack: list[str] = []
    pos = 0
    for m in _TAG_RE.finditer(text):
        plain = text[pos : m.start()]
        pos = m.end()
        if "<" in plain or ">" in plain:
            problems.append("unescaped < or > in text")
        if re.search(r"&(?!(?:amp|lt|gt|quot);)", plain):
            problems.append("unescaped & in text")
        closing, name = m.group(1) == "/", m.group(2).lower()
        if name not in HTML_TAGS:
            problems.append(f"tag <{name}> not allowed")
        elif not closing:
            stack.append(name)
        elif not stack or stack.pop() != name:
            problems.append(f"unbalanced </{name}>")
    tail = text[pos:]
    if "<" in tail or ">" in tail:
        problems.append("unescaped < or > in text")
    if re.search(r"&(?!(?:amp|lt|gt|quot);)", tail):
        problems.append("unescaped & in text")
    if stack:
        problems.append(f"unclosed <{stack[-1]}>")
    return list(dict.fromkeys(problems))


def eval_telegram_message(exp: dict, sent: list[dict], chat_id: str | int) -> list[str]:
    """``expect.telegram_message`` over the messages sent to the user's chat during the step.

    ``parse_mode``/``valid_html``/``not_matches``/``max_lines`` (non-blank lines) must hold for every
    message; ``matches`` for at least one."""
    mine = [m for m in sent if str(m.get("chat_id")) == str(chat_id)]
    if not mine:
        return ["telegram_message: no message sent to the user in this step"]
    fails: list[str] = []
    for m in mine:
        text = str(m.get("text", ""))
        head = text[:60]
        if "parse_mode" in exp and (m.get("params") or {}).get("parse_mode") != exp["parse_mode"]:
            fails.append(f"telegram_message.parse_mode: expected {exp['parse_mode']!r} got {(m.get('params') or {}).get('parse_mode')!r} ({head!r})")
        if exp.get("valid_html"):
            fails += [f"telegram_message.valid_html: {p} ({head!r})" for p in html_problems(text)]
        if "not_matches" in exp and re.search(exp["not_matches"], text, re.S | re.I):
            fails.append(f"telegram_message.not_matches: /{exp['not_matches']}/ matched ({head!r})")
        if "max_lines" in exp:
            n = sum(1 for ln in text.splitlines() if ln.strip())
            if n > exp["max_lines"]:
                fails.append(f"telegram_message.max_lines: {n} non-blank lines > {exp['max_lines']} ({head!r})")
    if "matches" in exp and not any(re.search(exp["matches"], str(m.get("text", "")), re.S | re.I) for m in mine):
        fails.append(f"telegram_message.matches: /{exp['matches']}/ matched no message")
    if "has_keyboard" in exp and any(bool(_markup_data(m)) != bool(exp["has_keyboard"]) for m in mine):
        fails.append(f"telegram_message.has_keyboard: expected {exp['has_keyboard']} on every message")
    for m in mine:
        for d in _markup_data(m):
            if "callback_data_matches" in exp and not re.fullmatch(exp["callback_data_matches"], d):
                fails.append(f"telegram_message.callback_data_matches: /{exp['callback_data_matches']}/ did not match {d!r}")
            if "callback_data_max_bytes" in exp and len(d.encode("utf-8")) > exp["callback_data_max_bytes"]:
                fails.append(f"telegram_message.callback_data_max_bytes: {d!r} is {len(d.encode('utf-8'))} bytes > {exp['callback_data_max_bytes']}")
    return fails


def _markup_data(m: dict) -> list[str]:
    """``callback_data`` of every button of a recorded message's inline keyboard."""
    rows = ((m.get("reply_markup") or {}).get("inline_keyboard")) or []
    return [str(b.get("callback_data")) for row in rows for b in row if b.get("callback_data") is not None]


def eval_expect(exp: dict, obs: dict) -> list[str]:
    """Pure: apply one ``expect`` block to observations; returns failure reasons.

    ``obs`` keys: ``reply`` (str|None), ``latency_s``, ``google`` (fake Google state),
    ``tools_called`` (iterable), ``evolution_sent``, ``telegram_sent``,
    ``media_requests``, ``control_jids``, ``chat_id``, ``base`` (date), ``tz``, ``postgres`` (counts,
    parallel to ``exp['postgres']``).
    """
    fails: list[str] = []
    if exp.get("no_reply") and obs.get("reply") is not None:
        fails.append(f"no_reply: agent replied ({str(obs['reply'])[:120]!r})")
    base, tz = obs.get("base") or date.today(), obs.get("tz") or DEFAULT_TZ
    google = obs.get("google") or {}
    if "reply_within_s" in exp:
        lat = obs.get("latency_s")
        if obs.get("reply") is None:
            fails.append(f"reply_within_s: no reply within {exp['reply_within_s']}s")
        elif lat is not None and lat > exp["reply_within_s"]:
            fails.append(f"reply_within_s: reply took {lat:.1f}s > {exp['reply_within_s']}s")
    if "max_latency_s" in exp and obs.get("latency_s") is not None and obs["latency_s"] > exp["max_latency_s"]:
        fails.append(f"max_latency_s: {obs['latency_s']:.1f}s > {exp['max_latency_s']}s")
    if "reply_matches" in exp:
        reply = obs.get("reply")
        if reply is None or not re.search(exp["reply_matches"], reply, re.S | re.I):
            fails.append(f"reply_matches: /{exp['reply_matches']}/ did not match reply {str(reply)[:120]!r}")
    if "reply_not_matches" in exp:
        reply = obs.get("reply")
        if reply is None:
            fails.append("reply_not_matches: no reply to check")
        elif re.search(exp["reply_not_matches"], reply, re.S | re.I):
            fails.append(f"reply_not_matches: /{exp['reply_not_matches']}/ matched reply {str(reply)[:120]!r}")
    if "calendar" in exp:
        fails += eval_calendar(exp["calendar"], google, base, tz)
    if "tasks" in exp:
        fails += eval_tasks(exp["tasks"], google, base, tz)
    if "gmail" in exp:
        fails += eval_gmail(exp["gmail"], google)
    called = set(obs.get("tools_called") or [])
    if exp.get("tools_called_any") and not called & set(exp["tools_called_any"]):
        fails.append(f"tools_called_any: none of {exp['tools_called_any']} called (called: {sorted(called)})")
    bad = called & set(exp.get("tools_not_called") or [])
    if bad:
        fails.append(f"tools_not_called: forbidden tools called: {sorted(bad)}")
    if "media_requests" in exp:
        n_media = len(obs.get("media_requests") or [])
        if n_media != exp["media_requests"]:
            fails.append(f"media_requests: expected {exp['media_requests']} got {n_media}")
    if "evolution_requests" in exp:
        got = obs.get("evolution_requests") or {}
        for endpoint, want in exp["evolution_requests"].items():
            if got.get(endpoint, 0) != want:
                fails.append(f"evolution_requests {endpoint}: expected {want} got {got.get(endpoint, 0)} during the step")
    if "outbound_to_third_parties" in exp:
        n = count_third_party_outbound(
            obs.get("evolution_sent") or [],
            obs.get("telegram_sent") or [],
            set(obs.get("control_jids") or []),
            obs.get("chat_id", ""),
        )
        if n != exp["outbound_to_third_parties"]:
            fails.append(f"outbound_to_third_parties: expected {exp['outbound_to_third_parties']} got {n}")
    if "telegram_sent_count_matching" in exp:
        tm = exp["telegram_sent_count_matching"]
        n = sum(
            1
            for m in obs.get("telegram_sent") or []
            if str(m.get("chat_id")) == str(obs.get("chat_id", "")) and re.search(tm["regex"], str(m.get("text", "")), re.S | re.I)
        )
        if n != tm["count"]:
            fails.append(f"telegram_sent_count_matching: /{tm['regex']}/ expected {tm['count']} user-bound messages got {n}")
    if "telegram_message" in exp:
        fails += eval_telegram_message(exp["telegram_message"], obs.get("telegram_step_sent") or [], obs.get("chat_id", ""))
    if "telegram_keyboard" in exp:
        labels = obs.get("telegram_keyboard")
        tk = exp["telegram_keyboard"]
        if labels is None:
            fails.append("telegram_keyboard: no tapped briefing message to inspect")
        else:
            if "contains" in tk and not re.search(tk["contains"], labels, re.S):
                fails.append(f"telegram_keyboard.contains: /{tk['contains']}/ not in keyboard {labels!r}")
            if "not_contains" in tk and re.search(tk["not_contains"], labels, re.S):
                fails.append(f"telegram_keyboard.not_contains: /{tk['not_contains']}/ found in keyboard {labels!r}")
    if "contact_profile" in exp:
        fails += eval_contact_profile(exp["contact_profile"], obs.get("contact_profile"))
    if "job_response_matches" in exp:
        resp = obs.get("job_response")
        if resp is None or not re.search(exp["job_response_matches"], resp, re.S | re.I):
            fails.append(f"job_response_matches: /{exp['job_response_matches']}/ did not match job response {str(resp)[:160]!r}")
    for row, got in zip(exp.get("postgres") or [], obs.get("postgres") or []):
        if got != row["count"]:
            fails.append(f"postgres {row['table']} {row.get('where') or ''}: expected count {row['count']} got {got}")
    return fails
