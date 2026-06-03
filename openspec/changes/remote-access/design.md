# Design: remote-access

## Telegram
n8n Telegram node → POST `http://agent-api:8000/webhooks/telegram` with header `X-Api-Key`.

## WhatsApp Phase A
`FixtureMessageSource` + heuristic extractor + `evi-test whatsapp` + golden JSON.

## WhatsApp Phase B options
1. Meta Cloud API — stable, business verification
2. Twilio — middleware, monthly cost
3. Export/backup ingest — private, not real-time
4. Tasker/Macrodroid — fragile, $0

Recommendation: ship Phase A now; pick Phase B when real-time tracking is required.
