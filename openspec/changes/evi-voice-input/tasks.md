## 1. Transcrição

- [x] 1.1 `services/transcribe.py`: chamada Gemini com áudio (sem tools), limites, erros legíveis, provider `ollama` recusado, flag
  - SCN-VOICE-03, SCN-VOICE-04
  - Files: `agent/services/transcribe.py`, `tests/unit/test_transcribe.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_transcribe.py -q`

## 2. Entradas

- [ ] 2.1 Telegram: `voice`/`audio` → `getFile` + download → transcrição → `chat()` com eco "🎙️ Entendi"
  - SCN-VOICE-01, SCN-VOICE-03
  - Files: `agent/services/telegram_handler.py`, `agent/services/telegram_poller.py`, `tests/unit/test_telegram_handler.py`, `tests/unit/test_telegram_poller.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_handler.py tests/unit/test_telegram_poller.py -q`

- [ ] 2.2 WhatsApp controle: `audioMessage` no parser (só JIDs de controle) + `getBase64FromMediaMessage` + transcrição
  - SCN-VOICE-02, SCN-VOICE-05
  - Files: `agent/services/evolution_parser.py`, `agent/services/whatsapp_control.py`, `agent/messaging/evolution.py`, `tests/unit/test_whatsapp_control.py`, `tests/unit/test_evolution_parser.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_control.py tests/unit/test_evolution_parser.py -q` e `./scripts/evi-test whatsapp`

- [x] 2.3 `turn_log.input_kind` (`text`/`voice`) + linha no relatório semanal
  - SCN-VOICE-06
  - Files: `agent/db.py`, `agent/services/turn_log.py`, `agent/services/usage_report.py`, `tests/unit/test_usage_report.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_usage_report.py tests/unit/test_turn_log.py -q`

## 3. Simulação e fechamento

- [ ] 3.1 Fakes (`getFile`/download, `getBase64FromMediaMessage`), fixture de áudio sintético, cenários `SIM-VOICE-*` (Telegram voz → evento criado; WhatsApp controle voz; áudio de terceiro ignorado; áudio longo recusado), `sim.env`, `.env.example`, `docs/testing.md`
  - SCN-VOICE-01..05
  - Files: `agent/testing/sim/fake_telegram.py`, `agent/testing/sim/fake_evolution.py`, `tests/fixtures/audio/`, `tests/sim/scenarios/voice/`, `tests/sim/sim.env`
  - Verify: `./scripts/evi-sim run --tag voice --repeat 3 --llm live` (3/3) e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.2 Sincronizar specs com o as-built, atualizar `BACKLOG.md`/`Progress.md`/roadmap e arquivar
  - Files: `openspec/changes/evi-voice-input/`, `openspec/BACKLOG.md`, `Progress.md`, `openspec/specs/roadmap.md`
  - Verify: `openspec validate --specs && PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-sim run --tag critical,adversarial --repeat 3 --llm live && ./scripts/evi-sim run --tag critical --llm replay`
