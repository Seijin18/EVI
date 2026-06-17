# Commitment review

When the user asks about compromissos, pendentes, agenda EVI:

1. Call `list_pending_commitments` or `list_scheduled_today`.
2. Group: with date / without date / suspicious (generic titles like "Reunião", "Item").
3. Suggest confirm or dismiss ids; use `dismiss_commitments` or `confirm_commitments` when asked.
4. For "clean false positives", list then dismiss weak entries in one ReAct flow.
