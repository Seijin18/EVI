## Design

- Resolve contacts via FS + Postgres merge (`collect_known_contacts`, `search_contacts`).
- Backfill: Evolution `POST /chat/findMessages/{instance}` → `timeline.jsonl` with dedupe.
- Synthesis: `build_background_llm()` → append `## Síntese` section in `profile.md`.

## Out of scope

- Graphiti; continuous webhook timeline for all messages.
