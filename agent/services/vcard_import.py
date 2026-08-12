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


def import_vcard(
    path: str | Path,
    *,
    dry_run: bool = True,
    limit: int = 5000,
) -> ImportReport:
    """Parse a .vcf and set `display_name` on matching WhatsApp contacts."""
    from db import list_whatsapp_contacts_db, upsert_whatsapp_contact

    report = ImportReport(dry_run=dry_run)
    p = Path(path)
    if not p.is_file():
        report.examples.append(f"arquivo não encontrado: {p}")
        return report

    entries = parse_vcards(p.read_text(encoding="utf-8", errors="replace"))
    report.parsed = len(entries)
    index = build_registry_index(list_whatsapp_contacts_db(limit=limit))

    for entry in entries:
        if not entry.phones or not entry.name:
            report.skipped_no_phone += 1
            continue

        hits: list[dict] = []
        for phone in entry.phones:
            key = match_key(phone)
            if not key:
                continue
            for row in index.get(key, []):
                if row not in hits:
                    hits.append(row)

        if not hits:
            report.unmatched += 1
            continue
        if len(hits) > 1:
            # Better to leave it than to label the wrong person.
            report.ambiguous += 1
            report.examples.append(
                f"ambíguo: «{entry.name}» casa {len(hits)} contatos"
            )
            continue

        row = hits[0]
        report.matched += 1
        if (row.get("display_name") or "") == entry.name:
            report.unchanged += 1
            continue

        previous = (row.get("display_name") or row.get("whatsapp_label") or "").strip()
        aliases = [previous] if previous and previous != entry.name else []
        report.updated += 1
        if len(report.examples) < 10:
            report.examples.append(f"{previous or row['jid']} → {entry.name}")
        if not dry_run:
            upsert_whatsapp_contact(
                row["jid"], display_name=entry.name, aliases=aliases
            )

    return report
