## Why

Around 1000 of the 2553 WhatsApp contacts show up as a bare phone number. The
cause is protocol, not a bug: Evolution/Baileys only ever receives `pushName` —
the name the *other person* chose for their own profile. The address book on the
phone never leaves it. Confirmed against the live instance: a contact record has
`pushName`, `isSaved: true` and nothing else; `findChats` has no `name` either,
and `evolution_discovery._contact_label` already tries `pushName`, `name`,
`verifiedName` and `notify`.

So the names have to come from outside, and a vCard export is the only source the
user actually has. The schema for it already exists — `whatsapp_contacts` has
`display_name` and `aliases`, and `set_whatsapp_contact_name` fills them one at a
time from chat, which is why only 3 of 1531 rows have a display name today. What
is missing is bulk import.

## What Changes

- **`agent/services/vcard_import.py` (new)** — a minimal vCard 2.1/3.0/4.0 parser
  (`FN`/`N` + `TEL`, quoted-printable and line folding handled) and an importer
  that matches each entry to an existing WhatsApp contact.
- **Matching by `DDD + last 8 digits`**, not by exact string. Measured against the
  live registry: 1104 JIDs carry 13 digits (`55` + DDD + 9) and 84 carry 12
  (`55` + DDD + 8) — the Brazilian ninth-digit split. A vCard may hold either
  form for the same person. The chosen key produced **1187 distinct keys for 1187
  Brazilian contacts, zero collisions**, and it is stable in both directions.
- **Precedence becomes address book > pushName > number.** The imported name goes
  to `display_name`; any existing `pushName` is preserved as an alias, so search
  keeps working for whichever name the user types.
- **A local job, never through the LLM** (decision recorded): `POST /jobs/import-contacts`
  with a server-side path, plus `./scripts/evi-test vcard` for a dry run. The file
  is read from disk by the agent; no contact data passes through a model to
  perform the import.
- **Dry-run by default.** The importer reports what it *would* change and only
  writes when explicitly confirmed, because it touches ~2000 rows at once.

## Impact

`agent/services/vcard_import.py` (new), `agent/main.py` (one job endpoint),
`agent/services/contact_registry.py` (precedence), `agent/testing/cli.py`,
`.env.example`.
Tests: `tests/unit/test_vcard_import.py` (new).
Specs: `data-long-memory`.

## Privacy note, recorded deliberately

The file holds names and numbers for ~2000 people who did not choose to be in an
AI system. It stays local — parsed by the agent, written to the local Postgres —
but the names then enter the LLM context whenever the user asks about a contact.
That is already true of `pushName` today; this multiplies the volume. The import
is opt-in, takes an explicit path, and nothing is uploaded.

Out of scope: importing emails, addresses or photos from the vCard (only name and
phone are read); syncing back to WhatsApp; and any automatic re-import.
