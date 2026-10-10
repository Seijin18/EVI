## Why

No Brasil, áudio é o modo padrão no WhatsApp; assistentes como Zapia e Luzia nasceram
transcrevendo áudio. Hoje o EVI descarta voz em silêncio: o handler do Telegram retorna
"no text" e o parser do Evolution ignora `audioMessage` — o usuário fala e não recebe
nada. Roadmap: Etapa 21; análise em [`docs/ux-review-2026-10.md`](../../../docs/ux-review-2026-10.md).

## What Changes

- Voz do usuário no Telegram (`voice`/`audio` → `getFile` → download) e no chat de
  controle do WhatsApp (`audioMessage` → `getBase64FromMediaMessage` do Evolution).
- Transcrição pelo Gemini com entrada de áudio nativa (sem GPU, sem dependência nova);
  a transcrição entra no mesmo fluxo do texto e é ecoada no início da resposta
  ("🎙️ Entendi: …"), para o usuário ver o que foi entendido.
- Só áudio do próprio usuário (chat do Telegram configurado e JIDs de controle).
  Áudio de terceiros continua não transcrito.
- `EVI_LLM_PROVIDER=ollama` → resposta "áudio não suportado neste modo".
- Limite de duração (`EVI_VOICE_MAX_SECONDS`, default 300) e falha visível
  ("não consegui ouvir o áudio") em vez de silêncio.
- Atrás de `EVI_VOICE_ENABLED` (default `false`).

## Impact

Novo: `agent/services/transcribe.py`, `tests/fixtures/audio/` (áudio sintético, fictício),
`tests/sim/scenarios/voice/`. Alterado: `agent/services/telegram_handler.py`,
`agent/services/telegram_poller.py` (download), `agent/services/evolution_parser.py`,
`agent/services/whatsapp_control.py`, `agent/messaging/evolution.py`,
`agent/testing/sim/fake_telegram.py`, `agent/testing/sim/fake_evolution.py`,
`.env.example`. Specs: `agent-api`, `messaging-whatsapp`. Sem container novo.

## Validação em uso real

Janela de 7 dias após ligar `EVI_VOICE_ENABLED`, pelo relatório semanal:
- ≥ 3 turnos por voz na janela;
- taxa de sucesso dos turnos por voz ≥ a dos turnos de texto − 10 pontos;
- nenhuma voz descartada em silêncio (todo áudio recebido gera resposta).

## Out of scope

- Transcrever áudio de terceiros (privacidade e custo).
- Responder em áudio (TTS).
- Transcrição local (GPU de 3 GB; motivo do corte original do "Llava + Whisper").
- Imagens e documentos.
