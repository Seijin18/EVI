## Decisões

### 1. Watchdog fora do EVI

`scripts/evi-watchdog` (bash + curl): `GET http://127.0.0.1:${EVI_PORT:-8000}/health`
com timeout de 10 s; `status` `down` ou falha HTTP conta como falha (`degraded` não).
Estado em `${XDG_STATE_HOME:-~/.local/state}/evi-watchdog/state` (falhas seguidas,
`alerted`). Na 2ª falha seguida: `sendMessage` direto em `api.telegram.org` com
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` lidos só dessas duas linhas do `.env`. Ao voltar
depois de alertar: uma mensagem "voltou". Timer de usuário a cada 1 min
(`systemctl --user`, sem `sudo`); instalação é ação do usuário, documentada. Teste:
`--dry-run` imprime a decisão sem enviar; testes unitários em bash via `bats`-like shell
ou um teste Python que roda o script com um servidor falso e `TELEGRAM_API_BASE`.

### 2. `/ajuda` determinístico

`services/help_text.build_help()` monta 6–8 linhas com exemplos reais das features
ligadas (agenda, tarefas, e-mail, briefing se ligado, lembretes se ligados, pendências
se ligadas, voz se ligada, `/bom` `/ruim`). `/ajuda` e `/help` em `chat_commands`; a
frase "o que você pode fazer" (normalizada) também é atendida sem LLM. `AGENTS.md`
aponta para `/ajuda`.

### 3. Ack de tool lenta

No `TurnCollector`, `on_tool_start` arma um `threading.Timer(EVI_SLOW_ACK_SEC)`; se a
tool não terminou, envia "⏳ fazendo… (<nome amigável da tool>)" pelo canal do turno
(Telegram ou chat de controle) — uma vez por turno; `on_tool_end/error` cancela. Turnos
de API/teste não recebem ack. Desligado com 0.

### 4. OAuth na hora

`parse_windmill_result` já classifica `reason=oauth`. Ao classificar, chama
`probe.notify_oauth(check)` que reutiliza `claim_probe_notification(day, check)` — o
mesmo controle diário da sonda, então sonda e turno nunca avisam duas vezes no dia.

## Configuração

| Env | Default | Efeito |
|---|---|---|
| `EVI_SLOW_ACK_SEC` | `0` | Liga o ack (sugerido 5) |
| `EVI_WATCHDOG_URL` | `http://127.0.0.1:8000/health` | Alvo do watchdog |

## RAM / containers

Nenhum container. Um processo curto por minuto no host.

## Riscos

- Watchdog lendo o `.env`: só as duas variáveis do Telegram, nunca o arquivo inteiro.
- Ack em excesso: uma vez por turno, só acima do limiar.

## Out of scope

Ver `proposal.md`.
