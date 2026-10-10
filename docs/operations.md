# Operações

## Watchdog (`scripts/evi-watchdog`)

Roda **fora** do EVI (timer de usuário do systemd, a cada minuto). Faz `GET /health`
(timeout 10 s); erro HTTP, timeout ou `status: "down"` é falha (`degraded` não é).
Na 2ª falha seguida envia **um** alerta no Telegram ("⚠️ EVI fora do ar desde HH:MM — motivo");
quando o health volta depois de alertar, envia **uma** mensagem "✅ EVI voltou (fora por N min)".

Configuração (opcional):

| Env | Default |
|---|---|
| `EVI_WATCHDOG_URL` | `http://127.0.0.1:8002/health` (porta publicada do `agent-api`) |
| `EVI_WATCHDOG_TIMEOUT` | `10` (segundos) |
| `TELEGRAM_API_BASE` | `https://api.telegram.org` |

`TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` vêm do ambiente ou, se ausentes, dessas duas
linhas do `.env` do repo (o arquivo nunca é "sourced"; o token nunca é impresso).
Estado: `${XDG_STATE_HOME:-~/.local/state}/evi-watchdog/state`.

### Instalar (ação do usuário)

```bash
cd ~/Projects/EVI   # as units assumem o repo em ~/Projects/EVI (edite ExecStart se não for)
mkdir -p ~/.config/systemd/user && cp scripts/systemd/evi-watchdog.* ~/.config/systemd/user/ \
  && systemctl --user daemon-reload && systemctl --user enable --now evi-watchdog.timer
systemctl --user list-timers evi-watchdog.timer
journalctl --user -u evi-watchdog.service -n 20
```

Desinstalar: `systemctl --user disable --now evi-watchdog.timer`.

### Testar

```bash
scripts/evi-watchdog --dry-run   # imprime a decisão (ok / fail N / would alert / would send recovery); não envia nem grava estado
```

Teste induzido: `docker compose stop agent-api`, esperar ~2 min (chega o alerta, uma vez),
`docker compose start agent-api` (chega "voltou", uma vez).
