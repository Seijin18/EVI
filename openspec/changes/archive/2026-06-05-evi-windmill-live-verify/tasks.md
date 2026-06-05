# Tasks: evi-windmill-live-verify

## 1. Specs

- [x] 1.1 Delta specs integrations-windmill, tools-productivity, testing
  - SCN-EMAIL-05, SCN-TASK-05
  - Files: openspec/changes/evi-windmill-live-verify/specs/**/spec.md
  - Verify: `openspec validate evi-windmill-live-verify`

## 2. Harness

- [x] 2.1 `run_email(live_windmill)` + dispatcher flag
  - SCN-EMAIL-05
  - Files: agent/testing/cli.py
  - Verify: `./scripts/evi-test email`

- [x] 2.2 Harden `run_tasks` live assertion
  - SCN-TASK-05
  - Files: agent/testing/cli.py
  - Verify: `./scripts/evi-test tasks`

## 3. Tests and docs

- [x] 3.1 Unit test `summarize_inbox` wiring
  - SCN-EMAIL-03
  - Files: tests/unit/test_email_tool.py
  - Verify: `PYTHONPATH=agent python3 tests/unit/test_email_tool.py`

- [x] 3.2 Document gmail/gcloud resources and env
  - SCN-EMAIL-05, SCN-CAL-05
  - Files: windmill/README.md, .env.example, docs/testing.md
  - Verify: `./scripts/evi-test email`

## 4. Live verify and archive

- [x] 4.1 Live regression calendar/tasks/email
  - SCN-CAL-04, SCN-TASK-05, SCN-EMAIL-05
  - Files: (none)
  - Verify: `./scripts/evi-test calendar --live-windmill` (if stack up)

- [x] 4.2 Sync main specs and archive
  - Files: openspec/specs/integrations-windmill/spec.md, openspec/specs/tools-productivity/spec.md, openspec/specs/testing/spec.md, openspec/specs/roadmap.md
  - Verify: `openspec validate evi-windmill-live-verify && openspec validate --specs`
