# Inbox triage

When the user asks about email, Gmail, or inbox:

1. Call `summarize_inbox`.
2. Group by category: important, promotions/shopping, social, other.
3. Keep response under 12 lines; do not ask for message IDs unless delete failed.
4. For bulk delete by sender (AliExpress, OLX, etc.), use `delete_emails_by_query`.
5. For "delete those" follow-ups, read SESSION TOOL SNAPSHOTS for message ids.
