## Design

- Resolve contacts via FS + Postgres merge (`collect_known_contacts`, `search_contacts`). Postgres `whatsapp_contacts` is canonical for identity (display name, aliases, phone); filesystem `contact_filesystem` is canonical for timeline/narrative memory (profile.md, timeline.jsonl). See `openspec/specs/data-long-memory/spec.md` for the explicit split.
- Backfill: Evolution `POST /chat/findMessages/{instance}` → `timeline.jsonl` with dedupe.
- Discovery: Evolution `findContacts`/`findChats` → `evolution_discovery.py`, surfaced via `whatsapp_activity` tools (list/summarize recent chats).
- Ingest-log replay: `commitment_replay.py` replays `evolution_webhook.jsonl` lines to backfill `pending_commitments` and `message_timeline` when the Evolution cache lags or messages were dropped by the live webhook filter.
- Synthesis: `build_background_llm()` → append `## Síntese` section in `profile.md`.

## Out of scope

- Graphiti; continuous webhook timeline for all messages.
