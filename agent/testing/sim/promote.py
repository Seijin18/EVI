"""Promote a real usage turn (``turn_log``) into a draft evi-sim scenario (SCN-USE-07).

    ./scripts/evi-sim promote <turn_id>

Reads the turn plus the previous and next turn of the same session (read-only),
anonymizes them and emits ``tests/sim/scenarios/from-usage/<date>-<id>.yaml`` with a
minimal ``seed``, one ``telegram:`` / ``whatsapp_control:`` step and
``expect: {todo: "preencher"}``. The expectation is a human decision, never inferred:
``testing.sim.schema`` refuses a scenario whose ``expect`` carries ``todo`` until it
is replaced by real assertions.

Anonymization (stable within one run: the same input always gets the same fake):
  * e-mails              -> ``pessoaN@exemplo.com``
  * phones / JIDs        -> ``+55 11 90000-00NN`` (JIDs keep their ``@suffix``);
    any digit run of 8+ digits, with/without ``+``, spaces, dashes, dots, parentheses
  * names                -> fictitious names. Sources, in order: the WhatsApp contact
    registry (display name / label / aliases, loaded lazily and optionally), a single
    capitalized word after a trigger ("contato", "é de", "com o/a", "para o/a"...),
    and ANY sequence of 2+ capitalized words (sentence start included: over-anonymizing
    "Marque Reunião" is cheaper than leaking a name).

Limits (so the draft ALWAYS needs human review before commit): a lone first name
that is neither in the registry nor after a trigger, lowercase names, nicknames,
street addresses, company names, free-form IDs (CPF, order numbers < 8 digits) and
anything inside tool arguments are NOT detected. Tool args are never included; only
tool names appear, as a comment hint.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[3]
FROM_USAGE_DIR = REPO_ROOT / "tests" / "sim" / "scenarios" / "from-usage"
TZ = "America/Sao_Paulo"
WARNING = (
    "evi-sim promote: DRAFT. Anonymization is best-effort (see testing.sim.promote docstring). "
    "A human MUST review the YAML for leaked names/data and fill `expect` before committing."
)

FAKE_NAMES = [
    "Ana Exemplo", "Bruno Teste", "Carla Ficticia", "Daniel Modelo", "Elisa Amostra",
    "Fabio Demo", "Gisele Padrao", "Hugo Sintetico", "Irene Simulada", "Jorge Ficticio",
]
CHANNEL_STEP = {"telegram": "telegram", "whatsapp_control": "whatsapp_control", "api": "telegram"}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_JID_RE = re.compile(r"\b(\d{8,})(@(?:s\.whatsapp\.net|c\.us|g\.us|lid))\b")
_PHONE_RE = re.compile(r"(?<![\w.])\+?\(?\d[\d\s\-().]{6,}\d(?!\w)")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CAP = r"[A-ZÀ-Ý][a-zà-ÿ]+"
_CAP_SEQ_RE = re.compile(rf"\b{_CAP}(?:\s+(?:(?:de|da|do|dos|das|e)\s+)?{_CAP})+\b")
_TRIGGER_RE = re.compile(
    rf"(?i:\b(?:contato|contatos|é de|e de|com o|com a|para o|para a|pro|pra|do|da))\s+({_CAP})\b"
)
_SENT = re.compile("\ue000(\\d+)\ue001")


class PromoteError(RuntimeError):
    pass


class Anonymizer:
    """Stable fake mapping for one promote run. Passes put sentinels so that fakes
    inserted by one pass are never re-matched by a later one."""

    def __init__(self, known_names: list[str] | None = None) -> None:
        self._fakes: list[str] = []
        self._names: dict[str, str] = {}
        self._phones: dict[str, int] = {}
        self._emails: dict[str, int] = {}
        self._known = self._expand_known(known_names or [])

    @staticmethod
    def _expand_known(names: list[str]) -> dict[str, str]:
        """lowercase full name / token -> canonical full name (tokens >= 4 chars)."""
        out: dict[str, str] = {}
        for full in sorted({n.strip() for n in names if n and n.strip()}, key=len, reverse=True):
            out.setdefault(full.lower(), full)
            for tok in re.findall(r"\w{4,}", full):
                out.setdefault(tok.lower(), full)
        return out

    def _sent(self, fake: str) -> str:
        self._fakes.append(fake)
        return f"\ue000{len(self._fakes) - 1}\ue001"

    def _fake_name(self, canon: str) -> str:
        key = canon.lower()
        if key not in self._names:
            n = len(self._names)
            self._names[key] = FAKE_NAMES[n] if n < len(FAKE_NAMES) else f"Pessoa Ficticia {n + 1}"
        return self._names[key]

    @staticmethod
    def _phone_key(raw: str) -> str:
        d = re.sub(r"\D", "", raw)
        return d[2:] if d.startswith("55") and len(d) >= 12 else d

    def _fake_phone_n(self, raw: str) -> int:
        key = self._phone_key(raw)
        if key not in self._phones:
            self._phones[key] = len(self._phones) + 1
        return self._phones[key]

    def _fake_phone(self, raw: str) -> str:
        return f"+55 11 90000-00{self._fake_phone_n(raw) % 100:02d}"

    def _email(self, m: re.Match) -> str:
        key = m.group(0).lower()
        if key not in self._emails:
            self._emails[key] = len(self._emails) + 1
        return self._sent(f"pessoa{self._emails[key]}@exemplo.com")

    def _jid(self, m: re.Match) -> str:
        n = self._fake_phone_n(m.group(1))
        return self._sent(f"55119000000{n % 100:02d}{m.group(2)}")

    def _phone(self, m: re.Match) -> str:
        raw = m.group(0)
        if len(re.sub(r"\D", "", raw)) < 8 or _ISO_DATE_RE.match(raw.strip()):
            return raw
        return self._sent(self._fake_phone(raw))

    def anonymize(self, text: str | None) -> str:
        if not text:
            return text or ""
        s = _JID_RE.sub(self._jid, text)  # before e-mails: a JID looks like one
        s = _EMAIL_RE.sub(self._email, s)
        s = _PHONE_RE.sub(self._phone, s)
        for key in sorted(self._known, key=len, reverse=True):
            s = re.sub(
                rf"(?<!\w){re.escape(key)}(?!\w)",
                lambda _m, k=key: self._sent(self._fake_name(self._known[k])),
                s,
                flags=re.I,
            )
        s = _CAP_SEQ_RE.sub(lambda m: self._sent(self._fake_name(m.group(0))), s)
        s = _TRIGGER_RE.sub(lambda m: m.group(0)[: m.start(1) - m.start(0)] + self._sent(self._fake_name(m.group(1))), s)
        return _SENT.sub(lambda m: self._fakes[int(m.group(1))], s)


# --------------------------------------------------------------------------- loaders
def default_loader(turn_id: Any) -> dict:
    """``{"turn": {...}, "previous": {...}|None, "next": {...}|None, "known_names": [...]}``.

    Lazy ``db`` import (SELECT-only functions). The contact registry is optional.
    """
    import db  # noqa: PLC0415

    turn = db.get_turn(turn_id)
    if not turn:
        raise PromoteError(f"turn {turn_id} not found")
    around = db.get_session_turns_around(turn_id)
    if isinstance(around, dict):
        prev, nxt = around.get("previous", around.get("prev")), around.get("next")
    else:
        prev, nxt = (list(around) + [None, None])[:2]
    names: list[str] = []
    try:
        for c in db.list_whatsapp_contacts_db():
            names += [c.get("display_name"), c.get("whatsapp_label"), *(c.get("aliases") or [])]
    except Exception as exc:  # registry is optional
        print(f"evi-sim promote: contact registry unavailable ({exc}); using heuristics only", file=sys.stderr)
    return {"turn": turn, "previous": prev, "next": nxt, "known_names": [n for n in names if n]}


# --------------------------------------------------------------------------- rendering
def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _one_line(s: str, limit: int = 300) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _turn_date(turn: dict) -> tuple[str, str]:
    ts = turn.get("ts")
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            ts = None
    if isinstance(ts, datetime):
        if ts.tzinfo:
            ts = ts.astimezone(ZoneInfo(TZ))
        return ts.strftime("%Y-%m-%d"), ts.strftime("%H:%M")
    return "0000-00-00", "09:00"


def build_yaml(data: dict, anon: Anonymizer | None = None) -> tuple[str, str]:
    """Returns ``(filename, yaml_text)``."""
    turn = data["turn"]
    anon = anon or Anonymizer(data.get("known_names"))
    channel = turn.get("channel") or "telegram"
    if channel not in CHANNEL_STEP:
        raise PromoteError(f"channel {channel!r} cannot be promoted (supported: {sorted(CHANNEL_STEP)})")
    step = CHANNEL_STEP[channel]
    tid = re.sub(r"[^A-Za-z0-9_-]", "", str(turn.get("id")))
    day, hhmm = _turn_date(turn)
    # anonymize in a fixed order (previous, turn, next) so fakes are deterministic
    prev, nxt = data.get("previous"), data.get("next")
    prev_u = anon.anonymize((prev or {}).get("user_text"))
    prev_r = anon.anonymize((prev or {}).get("reply_text"))
    user = anon.anonymize(turn.get("user_text"))
    reply = anon.anonymize(turn.get("reply_text"))
    note = anon.anonymize(turn.get("feedback_note"))
    next_u = anon.anonymize((nxt or {}).get("user_text"))
    tools = [str(t.get("name")) for t in (turn.get("tools") or []) if isinstance(t, dict) and t.get("name")]

    L = [
        f"# file: {day}-{tid}.yaml",
        "# DRAFT from `evi-sim promote` — anonymized best-effort; REVIEW for leaked data before commit.",
        f"id: SIM-USE-{tid}",
        f"title: {_q(f'Uso real - turno {tid}')}",
        "tags: [from-usage]",
        "source: real-usage",
        f"clock: D0 {hhmm}",
        "seed: {}",
    ]
    if channel == "api":
        L.append("# original channel was `api`; replayed as telegram")
    L.append("steps:")
    if prev:
        L.append(f"  # contexto - turno anterior (usuario): {_one_line(prev_u)}")
        L.append(f"  # contexto - turno anterior (EVI): {_one_line(prev_r)}")
    L.append(f"  - {step}: {_q(user)}")
    L.append(f"    # resposta original: {_one_line(reply)}")
    if tools:
        L.append(f"    # tools originais (so nomes): {', '.join(tools)}")
    if turn.get("feedback"):
        L.append(f"    # feedback do usuario: {_one_line(str(turn['feedback']))} {_one_line(note, 200)}".rstrip())
    if nxt:
        L.append(f"    # contexto - proximo turno (usuario): {_one_line(next_u)}")
    L.append('    expect: {todo: "preencher"}  # TODO: preencher — decisao humana, o runner recusa ate trocar')
    return f"{day}-{tid}.yaml", "\n".join(L) + "\n"


def save(yaml_text: str, out_dir: Path = FROM_USAGE_DIR) -> Path:
    m = re.match(r"# file: ([\w.-]+\.yaml)\n", yaml_text)
    if not m:
        raise PromoteError("stdin does not look like promote output (missing '# file:' header)")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / m.group(1)
    path.write_text(yaml_text, encoding="utf-8")
    return path


def promote(turn_id: Any, loader: Callable[[Any], dict] = default_loader, out_dir: Path | None = None) -> Path:
    _, text = build_yaml(loader(turn_id))
    return save(text, out_dir or FROM_USAGE_DIR)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m testing.sim.promote")
    p.add_argument("turn_id", nargs="?")
    p.add_argument("--stdout", action="store_true", help="print the YAML instead of writing a file")
    p.add_argument("--save-stdin", action="store_true", help="write the YAML read from stdin under --out-dir")
    p.add_argument("--out-dir", default=str(FROM_USAGE_DIR))
    args = p.parse_args(argv)
    try:
        if args.save_stdin:
            path = save(sys.stdin.read(), Path(args.out_dir))
        else:
            if not args.turn_id:
                p.error("turn_id required")
            name, text = build_yaml(default_loader(args.turn_id))
            if args.stdout:
                sys.stdout.write(text)
                print(WARNING, file=sys.stderr)
                return 0
            path = save(text, Path(args.out_dir))
    except PromoteError as exc:
        print(f"evi-sim promote: {exc}", file=sys.stderr)
        return 1
    print(f"evi-sim promote: wrote {path}", file=sys.stderr)
    print(WARNING, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
