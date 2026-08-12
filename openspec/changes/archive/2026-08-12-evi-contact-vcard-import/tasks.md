## 1. Implementation

- [x] 1.1 vCard parser (2.1/3.0/4.0, folding, quoted-printable, `FN`/`N`/`TEL`)
  - SCN-MEM-12
  - Files: `agent/services/vcard_import.py`
  - Verify: `pytest tests/unit/test_vcard_import.py -q`

- [x] 1.2 `match_key` — DDD + last 8 digits, stable across the ninth digit
  - SCN-MEM-13
  - Files: `agent/services/vcard_import.py`
  - Verify: validated against the live registry — 1192 individual contacts produced
    1191 keys with **zero collisions**

- [x] 1.3 Importer: dry-run by default, old label kept as alias, ambiguous skipped
  - SCN-MEM-12
  - Files: `agent/services/vcard_import.py`
  - Verify: `pytest tests/unit/test_vcard_import.py -q` (22 tests)

- [x] 1.4 Local job endpoint + offline harness command
  - SCN-MEM-12
  - Files: `agent/main.py`, `agent/testing/cli.py`
  - Verify: `./scripts/evi-test vcard`

- [x] 1.5 Spec delta
  - Files: `openspec/changes/evi-contact-vcard-import/specs/data-long-memory/spec.md`
  - Verify: `openspec validate evi-contact-vcard-import`

## 2. Close-out

- [x] 2.1 Full gate green
  - Verify: `pytest tests/unit -q && ./scripts/evi-test smoke && ruff check agent/ --select E,W,F --ignore E501 && ./scripts/evi-container-smoke.sh && openspec validate --specs`

- [x] 2.2 Update `Progress.md` + `openspec/BACKLOG.md`, then archive

- [ ] 2.3 **User step** — run the real import
  - Export the address book (Android: Contatos → Exportar `.vcf`; iPhone: iCloud.com → Contatos → Exportar vCard), copy it somewhere the container can read, then:
    `curl -s -X POST localhost:8002/jobs/import-contacts -H 'Content-Type: application/json' -d '{"path":"/workspace/agenda.vcf"}'`
    Review the dry-run summary, then repeat with `"apply": true`.
