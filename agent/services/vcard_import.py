"""Import address-book names from a vCard export.

WhatsApp never sends the names you saved. Evolution only receives `pushName` —
the name the *other person* put on their own profile — so roughly a thousand of
this user's contacts surface as a bare number. The address book lives on the
phone, and a `.vcf` export is the only way to bring it across.

Runs locally: the file is read from disk and written to Postgres. Its contents
never pass through an LLM.
"""

from __future__ import annotations

import quopri
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

_DIGITS = re.compile(r"\D")
# Property line: NAME;PARAM=VALUE:content
_LINE = re.compile(r"^(?P<name>[A-Za-z0-9-]+)(?P<params>;[^:]*)?:(?P<value>.*)$")


@dataclass
class VCardEntry:
    name: str
    phones: list[str] = field(default_factory=list)


@dataclass
class ImportReport:
    """What an import did, or would do in dry-run."""

    parsed: int = 0
    matched: int = 0
    updated: int = 0
    unchanged: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    skipped_no_phone: int = 0
    dry_run: bool = True
    examples: list[str] = field(default_factory=list)

    def summary(self) -> str:
        mode = "simulação" if self.dry_run else "aplicado"
        lines = [
            f"Import de agenda ({mode}):",
            f"  contatos no arquivo: {self.parsed}",
            f"  casados com WhatsApp: {self.matched}",
            f"  nomes atualizados: {self.updated}",
            f"  já corretos: {self.unchanged}",
            f"  sem correspondência: {self.unmatched}",
            f"  ambíguos (ignorados): {self.ambiguous}",
            f"  sem telefone: {self.skipped_no_phone}",
        ]
        if self.examples:
            lines.append("  exemplos:")
            lines.extend(f"    {e}" for e in self.examples[:10])
        return "\n".join(lines)


def _unfold(text: str) -> list[str]:
    """vCard folds long lines with a leading space or tab on the continuation."""
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _decode_value(value: str, params: str) -> str:
    low = params.lower()
    if "quoted-printable" in low:
        try:
            value = quopri.decodestring(value.encode("utf-8", "replace")).decode(
                "utf-8", "replace"
            )
        except Exception:
            pass
    return value.replace("\\,", ",").replace("\\;", ";").strip()


def _name_from_n(value: str) -> str:
    """`N` is Family;Given;Additional;Prefix;Suffix — render it readably."""
    parts = [p.strip() for p in value.split(";")]
    family = parts[0] if parts else ""
    given = parts[1] if len(parts) > 1 else ""
    joined = " ".join(p for p in (given, family) if p)
    return joined.strip()


def parse_vcards(text: str) -> list[VCardEntry]:
    """Extract (name, phones) pairs. Tolerant: a malformed card is skipped."""
    entries: list[VCardEntry] = []
    current: VCardEntry | None = None
    fallback_name = ""

    for line in _unfold(text):
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith("BEGIN:VCARD"):
            current = VCardEntry(name="")
            fallback_name = ""
            continue
        if upper.startswith("END:VCARD"):
            if current is not None:
                if not current.name:
                    current.name = fallback_name
                # Keep anything with a name or a phone; the importer classifies
                # the incomplete ones (skipped_no_phone). A card with neither is
                # not a contact.
                if current.name or current.phones:
                    entries.append(current)
            current = None
            continue
        if current is None:
            continue

        m = _LINE.match(stripped)
        if not m:
            continue
        name = m.group("name").upper()
        params = m.group("params") or ""
        value = _decode_value(m.group("value"), params)
        if not value:
            continue

        if name == "FN":
            current.name = value
        elif name == "N" and not current.name:
            fallback_name = _name_from_n(value)
        elif name == "TEL":
            current.phones.append(value)

    return entries


def match_key(phone_or_jid: str) -> str:
    """`DDD + last 8 digits` — the only key stable across the ninth digit.

    Brazilian mobiles are stored with or without the 9 depending on when the
    record was created (1104 of the live JIDs have 13 digits, 84 have 12), and a
    vCard may hold either form. Measured on the live registry this produced 1187
    distinct keys for 1187 contacts with zero collisions.
    """
    digits = _DIGITS.sub("", phone_or_jid or "")
    if len(digits) < 8:
        return ""
    if digits.startswith("55") and len(digits) >= 12:
        digits = digits[2:]  # drop the country code
    if len(digits) < 10:
        return digits[-8:]  # no DDD available; last 8 is all we have
    ddd = digits[-11:-9] if len(digits) >= 11 else digits[:2]
    return f"{ddd}{digits[-8:]}"


def build_registry_index(rows: Iterable[dict]) -> dict[str, list[dict]]:
    """Index existing WhatsApp contacts by match key. Groups/newsletters ignored."""
    index: dict[str, list[dict]] = {}
    for row in rows:
        jid = str(row.get("jid") or "")
        if "@s.whatsapp.net" not in jid:
            continue
        key = match_key(jid)
        if key:
            index.setdefault(key, []).append(row)
    return index


def _intl_digits(phone: str) -> str:
    """Normalised international digits: explicit +/00 country code kept; a number
    without one is taken as Brazilian (the user's address book is)."""
    raw = (phone or "").strip()
    digits = _DIGITS.sub("", raw)
    if raw.startswith("+"):
        return digits
    if raw.startswith("00"):
        return digits[2:]
    if digits.startswith("55") and len(digits) >= 12:
        return digits
    return "55" + digits


def _country_compatible(phone: str, jid: str) -> bool:
    """match_key drops the country code, so +351 912345678 would collide with a
    Brazilian 5551912345678-like jid. Brazilian numbers only match 55… jids; any other
    country must equal the jid's number exactly."""
    intl = _intl_digits(phone)
    jid_digits = _DIGITS.sub("", jid.split("@", 1)[0])
    if intl.startswith("55"):
        return jid_digits.startswith("55")
    return intl == jid_digits


def apply_entries(
    entries: Iterable[dict],
    *,
    source: str,
    dry_run: bool = True,
    limit: int = 5000,
) -> dict:
    """Apply `{"name", "phones"}` entries to the WhatsApp registry.

    Producer-agnostic core shared by the vCard import (`source="vcard"`) and the
    Google address-book sync (`source="agenda"`). Rules:

    - match by `match_key`; a phone claimed by two DIFFERENT names, or one entry
      hitting several WhatsApp rows, is skipped and counted `ambiguous`;
    - writes only where `name_source` is empty/`agenda`/`vcard`; a row named by the
      user (`user`) is never overwritten (`protected_user`);
    - the previous label becomes an alias; contacts absent from the entries keep
      their name; nothing is written when `dry_run`.
    """
    from db import list_whatsapp_contacts_db, upsert_whatsapp_contact

    items = [
        (str(e.get("name") or "").strip(), [str(p) for p in (e.get("phones") or [])])
        for e in entries
    ]
    rep = {
        "parsed": len(items),
        "matched": 0,
        "new_names": 0,
        "changed": 0,
        "unchanged": 0,
        "ambiguous": 0,
        "no_whatsapp": 0,
        "skipped_foreign": 0,
        "protected_user": 0,
        "skipped_no_phone": 0,
        "dry_run": dry_run,
        "examples": [],
    }

    # Names claimed per phone key across the whole batch.
    names_by_key: dict[str, set[str]] = {}
    for name, phones in items:
        if not name:
            continue
        for phone in phones:
            key = match_key(phone)
            if key:
                names_by_key.setdefault(key, set()).add(name.casefold())

    index = build_registry_index(list_whatsapp_contacts_db(limit=limit))
    seen_pairs: set[tuple[str, str]] = set()  # (phone key, casefolded name) already handled

    for name, phones in items:
        if not phones or not name:
            rep["skipped_no_phone"] += 1
            continue

        keys = [k for k in (match_key(p) for p in phones) if k]
        if any(len(names_by_key.get(k, ())) > 1 for k in keys):
            rep["ambiguous"] += 1
            rep["examples"].append(f"ambíguo: «{name}» divide telefone com outro nome")
            continue
        pairs = {(k, name.casefold()) for k in keys}
        if pairs and pairs <= seen_pairs:
            continue  # same contact listed twice (e.g. "Ana"/"ana"): one write only
        seen_pairs |= pairs

        hits: list[dict] = []
        foreign = False
        for phone in phones:
            for row in index.get(match_key(phone), []):
                if not _country_compatible(phone, str(row.get("jid") or "")):
                    foreign = True
                elif row not in hits:
                    hits.append(row)

        if not hits:
            rep["skipped_foreign" if foreign else "no_whatsapp"] += 1
            continue
        if len(hits) > 1:
            # Better to leave it than to label the wrong person.
            rep["ambiguous"] += 1
            rep["examples"].append(f"ambíguo: «{name}» casa {len(hits)} contatos")
            continue

        row = hits[0]
        rep["matched"] += 1
        current = (row.get("display_name") or "").strip()
        if current == name:
            rep["unchanged"] += 1
            continue
        if (row.get("name_source") or "") == "user":
            rep["protected_user"] += 1
            continue

        previous = (current or row.get("whatsapp_label") or "").strip()
        aliases = [previous] if previous and previous != name else []
        if not dry_run:
            # The guard is re-checked under the row lock: the user may have named this
            # contact in chat since the snapshot above was read.
            written = upsert_whatsapp_contact(
                row["jid"],
                display_name=name,
                aliases=aliases,
                name_source=source,
                only_if_name_source_in=(None, "agenda", "vcard"),
            )
            if written is False:
                rep["protected_user"] += 1
                continue
        rep["changed" if current else "new_names"] += 1
        if len(rep["examples"]) < 10:
            rep["examples"].append(f"{previous or row['jid']} → {name}")

    return rep


def import_vcard(
    path: str | Path,
    *,
    dry_run: bool = True,
    limit: int = 5000,
) -> ImportReport:
    """Parse a .vcf and set `display_name` on matching WhatsApp contacts."""
    report = ImportReport(dry_run=dry_run)
    p = Path(path)
    if not p.is_file():
        report.examples.append(f"arquivo não encontrado: {p}")
        return report

    entries = parse_vcards(p.read_text(encoding="utf-8", errors="replace"))
    r = apply_entries(
        [{"name": e.name, "phones": e.phones} for e in entries],
        source="vcard",
        dry_run=dry_run,
        limit=limit,
    )
    report.parsed = r["parsed"]
    report.matched = r["matched"]
    report.updated = r["new_names"] + r["changed"]
    report.unchanged = r["unchanged"]
    report.unmatched = r["no_whatsapp"] + r["skipped_foreign"]
    report.ambiguous = r["ambiguous"]
    report.skipped_no_phone = r["skipped_no_phone"]
    report.examples = list(r["examples"])
    return report
