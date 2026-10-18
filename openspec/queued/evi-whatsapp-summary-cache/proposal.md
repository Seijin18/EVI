## Why

"Resuma meu WhatsApp" e "o que chegou hoje no WhatsApp" levam ~46 s (p50) e puxam o p95 de
todos os turnos para 51 s (`docs/product-review-2026-10-18.md`). O tempo não é o LLM: cada
pedido faz até ~31 chamadas sequenciais à Evolution (`findChats` + um `findMessages` por
conversa). Desde `evi-contact-knowledge` o webhook já grava toda mensagem direta, dos dois
lados, na timeline do contato — o EVI tem os dados localmente e mesmo assim pergunta à
Evolution a cada vez.

## What Changes

- **Fonte local primeiro**: listar/resumir mensagens recentes lê as timelines locais
  (identidade canônica, dois lados) em vez da Evolution.
- **Evolution só como complemento**: grupos liberados (`EVI_WHATSAPP_GROUP_WHITELIST`) e
  períodos anteriores ao início da timeline continuam vindo da Evolution, em paralelo
  (pool limitado), nunca 30 chamadas em fila.
- **Cache curto do resumo** (10 min, invalidado por mensagem nova) — pedir de novo é instantâneo.
- Meta: p95 das duas tools < 5 s; p95 geral < 15 s.
- Ajuste do roadmap: a etapa falava em pré-computar no lote noturno; ler a fonte local resolve
  sem defasagem de um dia (decisão registrada).

## Impact

Alterado: `agent/services/whatsapp_activity.py`, `agent/services/evolution_discovery.py`,
`agent/services/message_timeline.py` (leitura por período), testes, um cenário de simulação.
Specs: `messaging-whatsapp`. Sem container novo; sem mudança de prompt.

## Validação em uso real

Janela de 7 dias: p95 de `list_recent_whatsapp_messages`/`summarize_whatsapp_messages` < 5 s
no `turn_log`; nenhuma reclamação de mensagem faltando (feedback 👎 ou correção no turno
seguinte).

## Out of scope

- Mudar o texto/estilo do resumo.
- Histórico completo de grupos (continua por whitelist e Evolution).
