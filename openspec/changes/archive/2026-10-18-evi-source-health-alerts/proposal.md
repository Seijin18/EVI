## Why

Na primeira semana de uso (revisão de 18/10, `docs/product-review-2026-10-18.md`) o
WhatsApp ficou desconectado de 14/10 a 18/10 e o OAuth do Google expirou em 18/10 — e o
usuário não soube pelo EVI. A sonda diária não verifica o WhatsApp, o watchdog só olha o
`/health` do agente, e uma fonte fora vira uma linha de erro no meio do briefing. Poke e
Superhuman (referências) mostram que confiança depende de precisão e pontualidade; um
assistente que lê o WhatsApp e passa 4 dias cego sem avisar perde exatamente isso.

## What Changes

- **WhatsApp na sonda e no watchdog**: `connectionState` da Evolution vira check da sonda
  diária e do watchdog (a cada minuto, direto na Evolution, sem depender do agente). Aviso
  no Telegram após 2 leituras seguidas fora de `open`, uma vez por queda, com o que fazer
  (gerar o QR) e aviso de volta.
- **`/health` mostra o WhatsApp** (check `whatsapp`; não derruba o status, só `degraded`).
- **Estado das fontes**: tabela `source_status` com desde quando cada fonte está fora.
- **Selo no topo do briefing**: fonte fora (WhatsApp desconectado, Google com OAuth
  expirado, outra falha) aparece em uma linha no topo, com desde quando e a ação, em vez
  de só uma linha de erro no meio.
- **Aviso de OAuth explica o ciclo de 7 dias** do modo "Teste" e a saída definitiva
  (publicar o app OAuth em Produção).
- Flag `EVI_SOURCE_ALERTS_ENABLED` (default `true`, decisão do usuário em 18/10).

## Impact

Alterado: `agent/messaging/evolution.py`, `agent/services/health.py`,
`agent/services/probe.py`, `agent/services/briefing.py`, `agent/db.py`,
`scripts/evi-watchdog`, `docs/operations.md`, `.env.example`; testes e simulação
(fake Evolution com `connectionState`). Specs: `agent-api`, `proactive`, `testing`.
Sem container novo; sem LLM.

## Validação em uso real

Janela de 7 dias: toda queda do WhatsApp com mais de 10 min gera exatamente um aviso
(conferir `logs` do watchdog × `probe_log`); 0 dias com fonte fora sem selo no briefing.

## Out of scope

- Reconectar o WhatsApp automaticamente (gerar/enviar QR exige o usuário).
- Publicar o app OAuth em Produção (ação do usuário no Google Cloud).
- Monitorar Windmill/Postgres além do que `/health` já faz.
