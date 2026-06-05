## Why

Telegram chat processed messages but never replied; digest (SCN-WA-12) lacked live verification.

## What Changes

- `send_telegram_message(text, chat_id)` + webhook reply (`telegram_sent`)
- `telegram_to_evi.py` stdlib; fixture chat_id real; `evi-telegram-verify.sh`

**Out of scope:** Public tunnel setup (manual `setWebhook`).
