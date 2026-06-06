## 1. Cleanup

- [x] 1.1 Remove orphan `openspec/changes/evi-as-built-baseline-v2/`
  - Files: `openspec/changes/evi-as-built-baseline-v2/`
  - Verify: `test ! -d openspec/changes/evi-as-built-baseline-v2`

## 2. Rules and index

- [x] 2.1 Update openspec-planning.mdc
  - Files: `.cursor/rules/openspec-planning.mdc`
  - Verify: `grep Etapa openspec-planning.mdc` in .cursor/rules

- [x] 2.2 Update Progress.md active series
  - Files: `Progress.md`
  - Verify: `grep llm-extract Progress.md`

## 3. BACKLOG finalize

- [x] 3.1 Mark série completa + note #2–6
  - Files: `openspec/BACKLOG.md`
  - Verify: `grep "sem archive" openspec/BACKLOG.md`

## 4. Validate

- [x] 4.1 Offline verify
  - Files: —
  - Verify: `./scripts/evi-test smoke && openspec validate --specs`
