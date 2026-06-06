# EVI — OpenSpec agent index (read this first)

## Cursor rules (persistent)

| Rule | When |
|------|------|
| `.cursor/rules/openspec-planning.mdc` | Propose, plan mode, roadmap |
| `.cursor/rules/openspec-workflow.mdc` | Apply, verify, archive |
| `.cursor/rules/openspec-changes.mdc` | Editing `openspec/**` |
| `.cursor/rules/codebase-memory.mdc` | Code search before grep |
| `.cursor/rules/cursor-performance.mdc` | Token/I/O limits |

## Active change

```bash
openspec list
openspec status --change <name> --json
openspec instructions apply --change <name> --json
```

Implement **one change at a time**. Read only `contextFiles` from apply instructions + current task `Files:`.

## Domain map

| Domain | Spec | Code / tests |
|--------|------|----------------|
| API | `specs/agent-api/spec.md` | `agent/main.py` |
| Productivity tools | `specs/tools-productivity/spec.md` | `agent/tools/`, `registry.py` |
| Windmill | `specs/integrations-windmill/spec.md` | `windmill/`, `agent/tools/*_tool.py` |
| RAG | `specs/data-rag/spec.md` | `agent/tools/rag_tool.py` |
| WhatsApp | `specs/messaging-whatsapp/spec.md` | `agent/services/whatsapp_processor.py` |
| Remote | `specs/remote-access/spec.md` | `agent/auth.py`, webhooks |
| Testing | `specs/testing/spec.md` | `scripts/evi-test`, `tests/` |
| Roadmap (deferred) | `specs/roadmap.md` | — |

## Verify (low token)

```bash
./scripts/evi-test smoke
./scripts/evi-test <feature> [--verbose]
PYTHONPATH=agent python3 tests/unit/test_whatsapp_processor.py
openspec validate <change>
```

## Backlog and review

- Propose queue: [`BACKLOG.md`](BACKLOG.md)
- Deferred only: [`specs/roadmap.md`](specs/roadmap.md)
- After archive: update BACKLOG status; `openspec validate --specs`

## Do not read by default

- `personal-ai-agent-server.md`, `Progress.md`, `.cursor/plans/`
- `openspec/changes/archive/`
- `agent/graph.py` when editing a single tool (use registry)

## Codebase memory

Use only when `Files:` is insufficient: `search_graph` with `file_pattern: "agent/**"`.
