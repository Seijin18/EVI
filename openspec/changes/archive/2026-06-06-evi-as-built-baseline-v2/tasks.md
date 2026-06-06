## 1. Spec sync

- [x] 1.1 Merge delta specs into `openspec/specs/`
  - Files: `openspec/specs/remote-access/spec.md`, `openspec/specs/integrations-windmill/spec.md`, `openspec/specs/messaging-whatsapp/spec.md`, `openspec/specs/testing/spec.md`
  - Verify: `openspec validate --specs`

## 2. Docs

- [x] 2.1 Enxugar Progress.md
  - Files: `Progress.md`
  - Verify: `wc -l Progress.md` shows under 100 lines

- [x] 2.2 Atualizar cabeçalho personal-ai-agent-server.md
  - Files: `personal-ai-agent-server.md`
  - Verify: `grep openspec/specs personal-ai-agent-server.md`

- [x] 2.3 Atualizar openspec-planning.mdc
  - Files: `.cursor/rules/openspec-planning.mdc`
  - Verify: `grep BACKLOG.md .cursor/rules/openspec-planning.mdc`

- [x] 2.4 Map new SCNs in docs/testing.md
  - Files: `docs/testing.md`
  - Verify: `grep SCN-TG-04 docs/testing.md`

## 3. Archive prep

- [x] 3.1 Offline verify
  - Files: —
  - Verify: `./scripts/evi-test smoke && openspec validate evi-as-built-baseline-v2`
