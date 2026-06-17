# Tasks: evi-llm-orchestration-inbox

- [x] **1.1 Tools + Windmill**
  - **Files:** `summarize_inbox.py`, `delete_emails.py`, `email_tool.py`, `registry.py`
  - **Verify:** `./scripts/evi-test email`

- [x] **1.2 delete_emails_by_query**
  - **Files:** `delete_emails_by_query.py`, `email_tool.py`, `windmill.py`
  - **Verify:** `tests/unit/test_delete_emails_by_query.py`

- [x] **1.3 Inbox skill + snapshots**
  - **Files:** `EVI_WORKSPACE/skills/inbox-triage/`, `session_context.py`
  - **Verify:** context assembly tests

- [x] **1.4 Direct handler flag**
  - **Files:** `telegram_handler.py`, `whatsapp_control.py`, `direct_handlers.py`
  - **Verify:** `./scripts/evi-test telegram`

- [x] **1.5 Multi-tool prompt**
  - **Files:** `graph.py`, `response_format.py`
  - **Verify:** `./scripts/evi-test email`
