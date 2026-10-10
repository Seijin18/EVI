## Context

| Peça existente | Onde | Situação |
|---|---|---|
| Handler do Telegram | `services/telegram_handler.process_telegram_update` | Retorna `skipped: no text` para voz |
| Poller (GET) | `services/telegram_poller._api_get` + `telegram_api_base()` | Sem `getFile`/download |
| Parser do Evolution | `services/evolution_parser._text_from_message` | Ignora `audioMessage` |
| Cliente Evolution | `agent/messaging/evolution.py` | Sem `getBase64FromMediaMessage` |
| Entrada do turno | `main._telegram_invoke_chat` / `_whatsapp_control_invoke_chat` | Texto → `chat()` |

## Decisões

### 1. Transcrever e seguir como texto

O áudio vira texto antes do grafo: `transcribe(audio_bytes, mime) -> str` faz uma
chamada ao Gemini (sem tools) com o áudio como parte de conteúdo e a instrução
"transcreva literalmente, em português, só o texto". O texto resultante entra em
`chat()` como se o usuário tivesse digitado. O grafo, as tools, o `turn_log` e o
histórico não mudam. A resposta ganha uma primeira linha "🎙️ Entendi: <transcrição>"
(truncada em 200 caracteres). `turn_log` marca `channel` normal e um campo
`input_kind='voice'` para o relatório.

Custo: áudio entra a US$ 1,00/1M tokens no 2.5 Flash (~32 tokens/s): 1 min ≈ US$ 0,002.

### 2. Origem do áudio

- Telegram: só mensagens do `TELEGRAM_CHAT_ID` configurado (o poller já filtra o chat).
  `voice` (OGG/Opus) e `audio` (mp3/m4a). `getFile` → `GET {base}/file/bot<token>/<path>`.
  Limite de 20 MB (Bot API) e `EVI_VOICE_MAX_SECONDS`.
- WhatsApp: `audioMessage` só quando o remetente é um JID de controle; o parser marca
  `kind='audio'` e guarda o `message key`; o controle chama
  `POST /chat/getBase64FromMediaMessage/<instance>`. Áudio de qualquer outro remetente
  continua descartado antes de qualquer download.

### 3. Falhas visíveis

Sem flag, provider `ollama`, áudio longo demais, download ou transcrição falhando →
resposta curta explicando (nunca silêncio). Transcrição vazia → "não consegui entender
o áudio, pode repetir?".

### 4. Simulação

Fake Telegram ganha `getFile` + download de arquivo; fake Evolution ganha
`getBase64FromMediaMessage`. Fixture de áudio sintético em pt-BR gerado por TTS local
(fictício, ≤ 60 KB, versionado). Cenários `SIM-VOICE-*` usam o Gemini real (live) e
cassette no replay.

## Configuração

| Env | Default | Efeito |
|---|---|---|
| `EVI_VOICE_ENABLED` | `false` | Liga a transcrição |
| `EVI_VOICE_MAX_SECONDS` | `300` | Duração máxima aceita |

## RAM / containers

Nenhum container novo; áudio em memória (≤ 20 MB), descartado após transcrever.

## Riscos

- **Treino no free tier**: no free tier o Google pode usar o conteúdo; com billing ativo
  (caso atual) não. Limitado a áudio do próprio usuário.
- **Transcrição errada executando ação**: o eco "Entendi: …" deixa o erro visível; ações
  destrutivas já exigem pedido explícito e, depois do #37, confirmação.

## Out of scope

Ver `proposal.md`.

## As-built (2026-10-10)

- Fixtures de áudio gerados por espeak-ng + opusenc num container descartável; a frase
  virou "marca consulta no dentista amanhã às três da tarde" (o TTS robótico tornava
  "marca dentista" ininteligível). Ver `tests/fixtures/audio/README.md`.
- Voz no Telegram verifica `TELEGRAM_CHAT_ID`. Achado: o **texto** não verifica — qualquer
  chat conversa com o EVI; correção na task 1.0 do `evi-prompt-injection-model`.
- Áudio de terceiros só conta como atividade ("[áudio]") para pendências de resposta;
  nunca é baixado nem transcrito.
- Erros de download do Telegram não carregam o token.
- `turn_log.input_kind` e linha de voz no relatório semanal.
