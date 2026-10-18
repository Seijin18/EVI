## Context

- `wa_conversation_state(jid, last_in_at, last_in_preview, last_in_id, last_out_at,
  acknowledged_at)`, chave canônica; atualizado pelo webhook (`reply_debts.track_conversation`).
- Timeline do contato com mensagens `[eu] …` (dois lados) — o texto da última mensagem do
  usuário vem daí (o estado não guarda o texto de saída).
- Heurística de pedido/pergunta: `reply_debts` (fechamentos v2: `?`, verbos de pedido).
- Briefing de segunda já tem a seção semanal "Conversas sem nome" (padrão de seção semanal).

## Decisions

### 1. Critério
`last_out_at > last_in_at` (ou `last_in_at` nulo), `now - last_out_at ≥ EVI_AWAITING_DAYS`
(3) e `≤ 30` dias; conversa direta, não canal, não controle; última mensagem `[eu]` da timeline
com `?` ou verbo de pedido ("me manda/passa/envia/confirma", "consegue", "pode", "qual",
"quando", "como", "você vai", "tem como"); não é fechamento ("valeu", "ok"). Ignorados:
tabela `awaiting_dismissed(jid, out_at)` — ignorar vale para aquela mensagem; uma mensagem
nova sua reabre.

### 2. Seção
Segunda, briefing da manhã, depois das dívidas de resposta e antes de "Conversas sem nome":
"⏳ Esperando resposta deles" — até 3, mais antigas primeiro: "<b>Pessoa</b> · há 5 d ·
“trecho da sua mensagem”" (sua mensagem não é de terceiros, mas é sanitizada e encurtada;
o nome é rótulo do registro). Numeração contínua com o resto do briefing; ref
`awaiting:<jid>`.

### 3. Ações
Botões `[N ✖]` (ignorar) e `[N 🔔]` (lembrete amanhã 9h "Cobrar <Pessoa>: <trecho curto>")
pelo mesmo mecanismo de toque do briefing (`callback_data` com `no`/`rm`); respostas por texto
"ignora N"/"lembra N". Nada é enviado ao contato.

### 4. Flag
`EVI_AWAITING_ENABLED` (padrão `true`).

## Riscos

- Falso positivo quando a pessoa respondeu por outro canal (ligação, pessoalmente): ignorar
  resolve; mostrado só uma vez por semana.
- Mensagens de antes de 13/10 não têm o texto `[eu]`: essas conversas ficam de fora.

## Out of scope

Envio automático; grupos; e-mail.
