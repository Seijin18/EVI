## Context

- `probe.run_probe` roda às 06:30 (Windmill), checks `calendar`, `tasks`, `gmail`,
  `telegram`, grava `probe_log` e avisa uma vez por dia por check (`probe_notified`).
- `scripts/evi-watchdog` (timer de usuário, 1 min) chama `/health`; alerta após 2 falhas
  e manda recuperação; estado em `~/.local/state/evi-watchdog/state`; lê só o token e o
  chat do Telegram do `.env`.
- `EvolutionClient` não tem `connectionState`; só `scripts/setup-evolution.sh` usa.
- Briefing: `_run_source` transforma falha em `Section.error`, renderizada como
  `⚠ <fonte> indisponível — <motivo>` dentro da seção.
- Medição de 18/10: `state: close` desde 14/10 11:21; OAuth do Google com expiração de 7 dias.

## Decisions

### 1. WhatsApp no watchdog, direto na Evolution
O watchdog lê também `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE_NAME` do `.env` (só essas
linhas, como hoje com o Telegram) e chama `GET 127.0.0.1:8082/instance/connectionState/<inst>`.
Estado ≠ `open` em 2 execuções seguidas → um aviso ("📵 WhatsApp desconectado desde HH:MM —
o EVI não está lendo suas conversas. Gere o QR: …"); volta a `open` → aviso de volta.
Evolution inacessível conta como fora. Estado separado do de saúde do agente no mesmo
arquivo (`wa_failures`, `wa_alerted`, `wa_since`). Não depende do agente: é o caso em que o
agente pode estar bem e o WhatsApp não.

### 2. WhatsApp na sonda e no `/health`
`EvolutionClient.connection_state() -> str | None`. Check `whatsapp` em `probe._CHECKS`
(`reason="disconnected"` se não `open`, `upstream_error` se a Evolution não responde) e em
`health.run_health_checks` (não fatal: `degraded`). A sonda deixa de avisar o WhatsApp
quando o watchdog já avisou no mesmo dia? — não há canal entre os dois; a sonda avisa no
máximo uma vez por dia (regra existente) e o watchdog uma vez por queda: no pior caso duas
mensagens por queda, aceitável.

### 3. `source_status`
Tabela `source_status(source text pk, ok bool, reason text, down_since timestamptz,
checked_at timestamptz)`. Atualizada pela sonda, pelo `/health` (WhatsApp) e pelo briefing
(resultado de cada fonte). `down_since` só é preenchido na transição ok → fora.

### 4. Selo no topo do briefing
Depois do cabeçalho, antes das seções: uma linha por fonte fora, agrupando o Google
("⚠️ Google (agenda, tarefas, e-mail): acesso expirado desde 18/10 — reconecte no
Windmill"), e "📵 WhatsApp desconectado desde 14/10 — gere o QR". A seção afetada continua
existindo com a linha curta de hoje (não repete o motivo). Conta no teto de 25 linhas e
nunca é colapsada. `text_user` e `text_model` iguais nesse trecho (sem conteúdo de terceiros).

### 5. Texto do OAuth
Acrescenta: "O app OAuth está em modo Teste: o Google expira o acesso a cada 7 dias.
Para não acontecer mais, publique o app em Produção (Google Cloud → OAuth consent screen)."

### 6. Flag
`EVI_SOURCE_ALERTS_ENABLED` (default `true`): desliga o check do WhatsApp na sonda/watchdog
e o selo. Decisão do usuário (18/10): novidades entram ligadas.

## Riscos

- Aviso duplicado (sonda + watchdog) numa queda longa: no máximo 2 por queda.
- Evolution reiniciando (≈ 25 s) não gera aviso: exige 2 leituras seguidas (2 min).
- RAM: nenhuma.

## Out of scope

Reconexão automática do WhatsApp; publicar o OAuth em Produção; outros serviços.
