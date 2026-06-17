## Why

Gmail UX was rigid (direct handlers, no IDs, no bulk delete). LLM must orchestrate Windmill tools with session snapshots.

## What Changes

- `delete_emails_by_query` Windmill + tool
- `EVI_DIRECT_HANDLERS=false` default path via grafo
- Inbox skill + multi-tool prompt rules

**Out of scope:** permanent Gmail rules UI.
