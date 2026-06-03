# Proposal: productivity-core

## Intent
Deliver productivity features: notes, auto-insights, Postgres sessions, n8n tasks/email tools.

## Scope
- POST /note, POST /insight
- save_note_manual, create_task, summarize_inbox
- db.py + DATABASE_URL in compose
