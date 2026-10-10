"""Weekly usage report (evi-usage-validation, task 2.3).

Pure KPI functions over canned turn dicts plus `generate_report`, which wires them
to the DB, writes `EVI_WORKSPACE/reports/usage-YYYY-Www.md` (conversation text —
local only, gitignored) and sends a <= 10-line Telegram summary (KPIs and turn ids,
never user text). Weeks are ISO weeks in EVI_TIMEZONE (local Mon 00:00 to next Mon 00:00). Every section soft-fails to
"indisponível" instead of failing the report.

Action rates per type (evi-reply-debts 2.4) are approximated from CURRENT state
(see db.action_rates_by_type): a debt that was answered or acknowledged after the
week still counts as acted, and a conversation with a newer inbound drops out.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Callable, Dict, List, Tuple

from llm_usage import estimate_cost
from services.usage_signals import (
    NEXT_TURN_WINDOW_S,
    prune_turn_log,
    RETENTION_DAYS,
    run_usage_signals,
    turn_succeeded,
)

logger = logging.getLogger(__name__)

UNAVAILABLE = "indisponível"
MAX_REVIEW = 5
REVIEW_TEXT_CHARS = 80
# Review priority: ruim > tool_failed > correction > rephrase (cant_do last).
ACTION_TYPES = (("reply_debt", "dívida de resposta"), ("promise", "promessa"), ("dated", "compromisso datado"))
REVIEW_PRIORITY = ("ruim", "tool_failed", "correction", "rephrase", "cant_do")


# -- weeks -------------------------------------------------------------------


def _tz() -> ZoneInfo:
    from tools.calendar_time import evi_timezone

    try:
        return ZoneInfo(evi_timezone())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("America/Sao_Paulo")


def _monday_midnight(d: date) -> datetime:
    """Aware local Monday 00:00 of the ISO week containing date `d`."""
    monday = d - timedelta(days=d.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=_tz())


def week_label(start: datetime) -> str:
    iso = start.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def parse_week(label: str) -> datetime:
    """'YYYY-Www' -> Monday 00:00 (EVI_TIMEZONE, aware) of that ISO week."""
    try:
        year, week = label.strip().upper().split("-W")
        monday = date.fromisocalendar(int(year), int(week), 1)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid week {label!r}, expected YYYY-Www") from exc
    return _monday_midnight(monday)


def default_week_start(now: datetime) -> datetime:
    """ISO week containing (local now - 6 days).

    A Monday 00:30 run (recommended schedule) reports the week that just closed;
    Sunday evening would report the week still ending, Tuesday-Saturday the previous full week.
    """
    local = now.astimezone(_tz())
    return _monday_midnight((local - timedelta(days=6)).date())


def baseline_window(first_ts: datetime | None, now: datetime) -> Tuple[datetime, datetime] | None:
    """First two FULL local ISO weeks after the first non-test turn, or None if not complete yet."""
    if first_ts is None:
        return None
    first_local = first_ts.astimezone(_tz())
    start = _monday_midnight(first_local.date())
    if first_local > start:  # first turn mid-week: the partial week is not "full"
        start = _monday_midnight(first_local.date() + timedelta(days=7))
    end = _monday_midnight(start.date() + timedelta(days=14))
    if now < end:
        return None
    return start, end


# -- pure KPIs -----------------------------------------------------------------


def percentile(values: List[float], pct: float) -> float | None:
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(-(-pct / 100 * len(s) // 1)) - 1))
    return float(s[k])


def turn_flags(turn: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    if turn.get("feedback") == "ruim":
        flags.append("ruim")
    signals = turn.get("signals") or {}
    for k in REVIEW_PRIORITY[1:]:
        if signals.get(k):
            flags.append(k)
    return flags


def compute_kpis(turns: List[Dict[str, Any]], weeks: float = 1.0) -> Dict[str, Any]:
    """KPIs over non-test turns. Count KPIs are divided by `weeks` (baseline = 2)."""
    real = [t for t in turns if not t.get("is_test")]
    n = len(real)
    by_channel: Dict[str, float] = {}
    days = set()
    failures: Dict[str, int] = {}
    ok_n = corr_n = 0
    voice_n = voice_ok = 0
    lat: List[float] = []
    llm: List[float] = []
    tok_in = tok_out = 0
    for t in real:
        ts = t.get("ts")
        if ts is not None:
            days.add(ts.astimezone(_tz()).date())
        ch = t.get("channel") or "?"
        by_channel[ch] = by_channel.get(ch, 0) + 1
        if turn_succeeded(t):
            ok_n += 1
        if t.get("input_kind") == "voice":
            voice_n += 1
            voice_ok += 1 if turn_succeeded(t) else 0
        sig = t.get("signals") or {}
        if sig.get("correction") or sig.get("rephrase"):
            corr_n += 1
        if t.get("latency_ms") is not None:
            lat.append(float(t["latency_ms"]))
        if t.get("llm_calls") is not None:
            llm.append(float(t["llm_calls"]))
        tok_in += int(t.get("tokens_in") or 0)
        tok_out += int(t.get("tokens_out") or 0)
        for tool in t.get("tools") or []:
            if isinstance(tool, dict) and tool.get("ok") is False:
                key = f"{tool.get('name') or '?'} / {tool.get('reason') or 'sem reason'}"
                failures[key] = failures.get(key, 0) + 1
    cost_usd, cost_brl = estimate_cost(tok_in, tok_out)
    return {
        "tokens": (tok_in + tok_out) / weeks,
        "cost_brl": cost_brl / weeks,
        "cost_usd": cost_usd / weeks,
        "active_days": len(days) / weeks,
        "turns": n / weeks,
        "by_channel": {k: v / weeks for k, v in by_channel.items()},
        "success_rate": (ok_n / n) if n else None,
        "correction_rate": (corr_n / n) if n else None,
        "voice_turns": voice_n / weeks,
        "voice_success_rate": (voice_ok / voice_n) if voice_n else None,
        "latency_p50": percentile(lat, 50),
        "latency_p95": percentile(lat, 95),
        "llm_calls_per_turn": (sum(llm) / len(llm)) if llm else None,
        "failures": {k: v / weeks for k, v in failures.items()},
        "failure_total": sum(failures.values()) / weeks,
    }


def probe_failure_days(probes: List[Dict[str, Any]]) -> Dict[str, int]:
    """Days with any ok=false, per check_name."""
    days: Dict[str, set] = {}
    for p in probes:
        if p.get("ok") is False:
            days.setdefault(p.get("check_name") or "?", set()).add(p.get("day"))
    return {k: len(v) for k, v in sorted(days.items())}


def review_candidates(turns: List[Dict[str, Any]], limit: int = MAX_REVIEW) -> List[Dict[str, Any]]:
    """Up to `limit` non-test turns to review, by priority then recency."""
    scored = []
    for t in turns:
        if t.get("is_test"):
            continue
        flags = turn_flags(t)
        if flags:
            scored.append((REVIEW_PRIORITY.index(flags[0]), -(t["ts"].timestamp()), t, flags))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [{"turn": t, "flags": flags} for _, _, t, flags in scored[:limit]]


# -- formatting ----------------------------------------------------------------


def _fmt(v: Any, kind: str = "num") -> str:
    if v is None:
        return "—"
    if kind == "pct":
        return f"{v * 100:.0f}%"
    if kind == "ms":
        return f"{v:.0f} ms"
    return f"{v:.1f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def _fmt_drift(v: Any) -> str:
    return "—" if v is None else f"{v:.0f} s"


def _delta(cur: Any, ref: Any, kind: str = "num") -> str:
    if cur is None or ref is None:
        return "—"
    d = cur - ref
    if kind == "pct":
        return f"{d * 100:+.0f} pp"
    if kind == "ms":
        return f"{d:+.0f} ms"
    return f"{d:+.1f}".replace(".0", "")


def _kpi_rows(cur: Dict, prev: Dict | None, base: Dict | None) -> List[Tuple[str, str, str, str, str]]:
    spec = [
        ("Dias ativos", "active_days", "num"),
        ("Turnos", "turns", "num"),
        ("Taxa de sucesso", "success_rate", "pct"),
        ("Correção/reformulação", "correction_rate", "pct"),
        ("Turnos por voz", "voice_turns", "num"),
        ("Sucesso dos turnos por voz", "voice_success_rate", "pct"),
        ("Latência p50", "latency_p50", "ms"),
        ("Latência p95", "latency_p95", "ms"),
        ("Chamadas LLM/turno", "llm_calls_per_turn", "num"),
        ("Tokens (entrada+saída)", "tokens", "num"),
        ("Custo estimado (R$)", "cost_brl", "num"),
        ("Falhas de tool", "failure_total", "num"),
    ]
    rows = []
    for label, key, kind in spec:
        rows.append(
            (
                label,
                _fmt(cur.get(key), kind),
                _delta(cur.get(key), prev.get(key) if prev else None, kind),
                _delta(cur.get(key), base.get(key) if base else None, kind),
                kind,
            )
        )
    return rows


def render_markdown(r: Dict[str, Any]) -> str:
    L: List[str] = [f"# Uso do EVI — {r['label']}", ""]
    L.append(f"Período: {r['start'].date()} a {(r['end'] - timedelta(days=1)).date()})")
    L.append("")
    base_note = (
        f"{r['baseline_range']}" if r.get("baseline_range") else "em formação"
    )
    L.append(f"Linha de base: {base_note}")
    L.append("")
    L.append("## KPIs")
    L.append("")
    if r["kpis"] is None:
        L.append(UNAVAILABLE)
    else:
        L.append("| KPI | Semana | Δ semana anterior | Δ linha de base |")
        L.append("|---|---|---|---|")
        for label, val, dp, db_, _ in _kpi_rows(r["kpis"], r["prev_kpis"], r["base_kpis"]):
            L.append(f"| {label} | {val} | {dp} | {db_} |")
        L.append("")
        ch = r["kpis"]["by_channel"]
        L.append("Turnos por canal: " + (", ".join(f"{k}={v:.0f}" for k, v in sorted(ch.items())) or "—"))
        L.append("")
        L.append("### Falhas por tool / reason")
        fails = r["kpis"]["failures"]
        if fails:
            for k, v in sorted(fails.items(), key=lambda kv: -kv[1]):
                L.append(f"- {k}: {v:.0f}")
        else:
            L.append("- nenhuma")
    L.append("")
    L.append("## Compromissos (criados na semana)")
    c = r["commitments"]
    L.append(
        UNAVAILABLE
        if c is None
        else f"confirmados: {c['confirmed']} · dispensados: {c['dismissed']} · pendentes: {c['pending']}"
    )
    L.append("")
    L.append("## Sonda (dias com falha por integração)")
    p = r["probes"]
    if p is None:
        L.append(UNAVAILABLE)
    elif not p:
        L.append("- nenhuma falha")
    else:
        for k, v in p.items():
            L.append(f"- {k}: {v} dia(s)")
    L.append("")
    L.append("## Lembretes")
    rm = r.get("reminders")
    if rm is None:
        L.append(UNAVAILABLE)
    else:
        L.append(
            f"criados: {rm['created']} · disparados: {rm['fired']} · atrasados (>5 min): {rm['late']} · "
            f"p95 do desvio: {_fmt_drift(rm['p95_drift_s'])}"
        )
    L.append("")
    L.append("## WhatsApp: ação por tipo")
    ar = r.get("action_rates")
    if ar is None:
        L.append(UNAVAILABLE)
    else:
        L.append("| tipo | mostrados | com ação | % |")
        L.append("|---|---|---|---|")
        for key, label in ACTION_TYPES:
            v = ar.get(key) or {"shown": 0, "acted": 0}
            pct = f"{v['acted'] * 100 / v['shown']:.0f}%" if v["shown"] else "—"
            L.append(f"| {label} | {v['shown']} | {v['acted']} | {pct} |")
    L.append("")
    L.append("## Formatos novos do Evolution")
    sh = r.get("shapes")
    if sh is None:
        L.append(UNAVAILABLE)
    elif not sh:
        L.append("Nenhum.")
    else:
        L.append(f"{len(sh)} assinatura(s) nova(s); virar fixture do fake Evolution:")
        for item in sh:
            L.append(f"- data/payload_shapes/{item['file']} ({item.get('event') or 'sem evento'})")
    L.append("")
    L.append("## Turnos para revisar")
    rev = r["review"]
    if rev is None:
        L.append(UNAVAILABLE)
    elif not rev:
        L.append("Nenhum.")
    else:
        L.append("Promover com `evi-sim promote <id>`.")
        L.append("")
        for item in rev:
            t = item["turn"]
            text = (t.get("user_text") or "").replace("\n", " ")[:REVIEW_TEXT_CHARS]
            L.append(
                f"- id={t['id']} · {t['ts'].isoformat(timespec='minutes')} · {t.get('channel')} · "
                f"{', '.join(item['flags'])} · \"{text}\""
            )
    L.append("")
    return "\n".join(L)


def render_telegram(r: Dict[str, Any]) -> str:
    """<= 10 lines; KPIs and turn ids only, never conversation text."""
    k = r["kpis"]
    L = [f"EVI uso {r['label']}"]
    if k is None:
        L.append(f"KPIs {UNAVAILABLE}")
    else:
        prev = r["prev_kpis"]
        cost = f" · ≈ R$ {k['cost_brl']:.2f}" if k.get("tokens") else ""
        L.append(f"Turnos {_fmt(k['turns'])} em {_fmt(k['active_days'])} dia(s) ativos{cost}")
        L.append(
            f"Sucesso {_fmt(k['success_rate'], 'pct')} "
            f"(Δ sem. {_delta(k['success_rate'], prev.get('success_rate') if prev else None, 'pct')})"
        )
        L.append(f"Correção/reformulação {_fmt(k['correction_rate'], 'pct')}")
        if k.get("voice_turns"):
            L.append(
                f"Voz: {_fmt(k['voice_turns'])} turnos · sucesso {_fmt(k['voice_success_rate'], 'pct')}"
            )
        L.append(f"Latência p50/p95 {_fmt(k['latency_p50'], 'ms')} / {_fmt(k['latency_p95'], 'ms')}")
        L.append(f"Falhas de tool {_fmt(k['failure_total'])}")
    c = r["commitments"]
    L.append(
        f"Compromissos {UNAVAILABLE}"
        if c is None
        else f"Compromissos: {c['confirmed']} conf. / {c['dismissed']} disp. / {c['pending']} pend."
    )
    p = r["probes"]
    if p is None:
        L.append(f"Sonda {UNAVAILABLE}")
    else:
        L.append("Sonda: " + (", ".join(f"{n} {d}d" for n, d in p.items()) if p else "sem falhas"))
    rm = r.get("reminders")
    if rm and (rm["created"] or rm["fired"]):
        L.append(
            f"Lembretes: {rm['created']} criados / {rm['fired']} disp. / {rm['late']} atras. "
            f"(p95 {_fmt_drift(rm['p95_drift_s'])})"
        )
    ar = r.get("action_rates")
    if ar and any((v.get("shown") or 0) > 0 for v in ar.values()):
        L.append(
            "Ação: "
            + " · ".join(
                f"{short} {(ar.get(k) or {}).get('acted', 0)}/{(ar.get(k) or {}).get('shown', 0)}"
                for k, short in (("reply_debt", "dívidas"), ("promise", "promessas"), ("dated", "datados"))
            )
        )
    rev = r["review"]
    if rev:
        L.append("Revisar ids: " + ", ".join(str(i["turn"]["id"]) for i in rev))
    if not r.get("baseline_range"):
        L.append("Linha de base: em formação")
    return "\n".join(L[:10])


# -- orchestration ---------------------------------------------------------------


def _section(name: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - soft-fail per section by design
        from services.soft_fail import soft_fail

        soft_fail(f"usage_report.{name}", exc)
        return None


def _fetch_commitments(start: datetime, end: datetime) -> Dict[str, int]:
    import db

    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, COUNT(*) FROM pending_commitments
                WHERE created_at >= %s AND created_at < %s AND source <> 'evi-test'
                GROUP BY status
                """,
                (start, end),
            )
            counts = {row[0]: int(row[1]) for row in cur.fetchall()}
    return {
        "confirmed": counts.get("scheduled", 0),
        "dismissed": counts.get("dismissed", 0),
        "pending": counts.get("pending", 0),
    }


def _first_real_turn_ts() -> datetime | None:
    import db

    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MIN(ts) FROM turn_log WHERE NOT is_test")
            row = cur.fetchone()
    return row[0] if row else None


def baseline_path() -> Path:
    from services.workspace import workspace_root

    return workspace_root() / "reports" / "baseline.json"


def _load_baseline() -> Dict[str, Any] | None:
    import json

    try:
        data = json.loads(baseline_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("kpis"), dict) else None


def _store_baseline(data: Dict[str, Any]) -> None:
    import json

    path = baseline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_signals_job(now: datetime | None = None) -> Dict[str, Any]:
    """Nightly job body: signals for the last 2 days + retention prune. Idempotent."""
    summary = run_usage_signals()
    summary["pruned"] = prune_turn_log(RETENTION_DAYS)
    return summary


def build_report(week_start: datetime, now: datetime | None = None) -> Dict[str, Any]:
    import db

    now = now or datetime.now(timezone.utc)
    end = _monday_midnight(week_start.date() + timedelta(days=7))
    prev_start = _monday_midnight(week_start.date() - timedelta(days=7))
    r: Dict[str, Any] = {"start": week_start, "end": end, "label": week_label(week_start)}

    _section(
        "signals",
        lambda: run_usage_signals(since=week_start, until=end + timedelta(seconds=NEXT_TURN_WINDOW_S)),
    )
    _section("prune", lambda: prune_turn_log(RETENTION_DAYS))

    turns = _section("turns", lambda: db.list_turns(week_start, end))
    r["kpis"] = None if turns is None else compute_kpis(turns)
    r["review"] = None if turns is None else review_candidates(turns)

    def _prev():
        return compute_kpis(db.list_turns(prev_start, week_start))

    prev = _section("prev", _prev)
    r["prev_kpis"] = prev if prev and prev["turns"] else None

    def _base():
        stored = _load_baseline()
        if stored:
            return stored
        win = baseline_window(_first_real_turn_ts(), now)
        if not win:
            return None
        kpis = compute_kpis(db.list_turns(*win), weeks=2.0)
        last_day = (win[1] - timedelta(days=1)).date()
        data = {
            "start_week": week_label(win[0]),
            "end_week": week_label(win[1] - timedelta(days=1)),
            "start": win[0].date().isoformat(),
            "end": last_day.isoformat(),
            "computed_at": now.isoformat(),
            "kpis": kpis,
        }
        _store_baseline(data)  # frozen: never recomputed (turn_log is pruned at 180 days)
        return data

    base = _section("baseline", _base)
    r["base_kpis"] = base["kpis"] if base else None
    r["baseline_range"] = f"{base['start']} a {base['end']}" if base else None

    r["commitments"] = _section("commitments", lambda: _fetch_commitments(week_start, end))
    r["probes"] = _section(
        "probes",
        lambda: probe_failure_days(
            db.list_probes(week_start.date(), (end - timedelta(days=1)).date())
        ),
    )

    def _reminders():
        st = db.reminder_stats(week_start, end)
        return {k: st[k] for k in ("created", "fired", "late", "p95_drift_s")}  # counts only, no text

    r["reminders"] = _section("reminders", _reminders)

    def _action_rates():
        import os

        return db.action_rates_by_type(
            week_start, end, float(os.getenv("EVI_REPLY_DEBT_HOURS", "4") or 4)
        )

    r["action_rates"] = _section("action_rates", _action_rates)

    def _shapes():
        from services.payload_shapes import list_new_shapes

        return list_new_shapes(week_start, end)

    r["shapes"] = _section("payload_shapes", _shapes)
    return r


def generate_report(week: str | None = None, now: datetime | None = None, notify: bool = True) -> Dict[str, Any]:
    from services.workspace import workspace_root

    from tools.calendar_time import now_local

    now = now or now_local()
    week_start = parse_week(week) if week else default_week_start(now)
    report = build_report(week_start, now)
    md = render_markdown(report)
    path: Path = workspace_root() / "reports" / f"usage-{report['label']}.md"

    def _write() -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
        return str(path)

    written = _section("write_markdown", _write)

    summary = render_telegram(report)
    sent = False
    if notify:
        from services.telegram_notify import send_telegram_message

        try:
            sent = bool(send_telegram_message(summary))
        except Exception as exc:  # noqa: BLE001
            logger.warning("usage_report telegram failed: %s", exc)
    return {
        "ok": True,
        "week": report["label"],
        "path": written,
        "local_report": written or "relatório local indisponível",
        "telegram_sent": sent,
        "summary": summary,
        "kpis": report["kpis"],
    }
