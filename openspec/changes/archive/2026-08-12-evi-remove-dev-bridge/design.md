## Design

### Removal order

Call sites first, then the modules, then the tests — so at no point does an
import dangle. `agent/tools/registry.py` is the pinch point: `main.py` does
`AVAILABLE_TOOLS = get_all_tools()` at module scope, so a stale import there
takes the whole app down at startup rather than failing lazily.

### `dev:` messages after removal

`try_dev_command` returned `str | None`, and `None` meant "not a dev command,
carry on". Deleting the branch is therefore behaviour-preserving for every
message except the four it claimed: `dev: <desc>`, `dev approve <id>`,
`dev status`/`dev jobs`, `dev mode …`. Those now reach the LLM as ordinary text.
That is the honest outcome — the agent will say it cannot do it, instead of
registering a job that could never run.

### Database

`init_db()` stops creating `dev_jobs` and `dev_bridge_state`; `create_dev_job`,
`get_dev_job`, `update_dev_job`, `list_dev_jobs`, `get_dev_bridge_setting` and
`set_dev_bridge_setting` are deleted. Existing databases keep the two tables,
empty and unreferenced.

Not dropping them is deliberate: a `DROP TABLE` inside `_run_migrations()` runs
on every startup of every install, and the only thing it buys is tidiness. After
what a careless data operation cost this repo on 2026-08-12, the bar for putting
a destructive statement in an automatic migration is high, and "two empty tables
look untidy" does not clear it. A one-line `DROP` is noted in the archive for
whoever wants it.

### Smoke count

`run_smoke` computes `len(tests)`, so the code needs no change — but "14/14"
appears verbatim in four docs including `openspec/specs/testing/spec.md`, whose
scenario asserts the number. All four move to 13/13 together; leaving the spec
saying 14 would make it wrong on the next `openspec validate` read-through even
though the validator does not execute it.

### Container smoke exemption

`run_in_image_checks` currently filters out `services.dev_bridge.*` and
`devcli.claude_backend.*` with a `[KNOWN]` note pointing at #33. With the modules
gone the filter has nothing to match, so it is removed entirely rather than left
as dead configuration — a stale exemption list is exactly how a real defect gets
silently excused later.

### What stays

`agent/messaging/`, `agent/integrations/` and `agent/llm.py` keep their
Protocol+factory shape. The dev bridge borrowed that pattern; it did not
introduce it, and the three surviving users are unaffected.

### Deleting the spec, not deltaing it

`openspec archive` applies a delta on top of the existing spec. A delta that
removes all four requirements rebuilds `dev-bridge` with zero requirements, which
`openspec validate` rejects — the tool has no "delete this spec" operation. So
`openspec/specs/dev-bridge/` is deleted as a plain file removal, and the REMOVED
requirements live in `removed-spec-dev-bridge.md` inside this change as the
record. `openspec validate --specs` goes from 10 specs to 9.

## Out of scope

- **Dropping `dev_jobs` / `dev_bridge_state`**, per above.
- **A replacement for remote code execution.** Nothing is being migrated; the
  capability goes away. `ssh` covers it.
- **The archived changes.** `2026-06-03-dev-assistant-bridge` and
  `2026-08-01-evi-dev-bridge-multi-cli` stay in `openspec/changes/archive/` as
  the historical record, including the design of the backend Protocol, in case
  the decision is ever revisited.
- **`agent/devcli`-shaped extension for other purposes.** If a pluggable
  subprocess backend is wanted later, it should be designed for its actual use
  case rather than resurrected from this one.
