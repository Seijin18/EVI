## Why

O EVI já mostra quem espera **sua** resposta e o que **você** prometeu, mas não o outro lado:
você perguntou ou pediu algo e a pessoa não respondeu. O Superhuman Auto Reminders
(referência em `docs/ux-review-2026-10.md`) mostra que esse follow-up é um dos lembretes mais
úteis, e o EVI já tem o estado (`wa_conversation_state.last_out_at`/`last_in_at`) e o texto da
sua mensagem na timeline (dois lados desde 13/10).

## What Changes

- **Detecção determinística**: conversa direta em que você foi o último a falar há mais de
  `EVI_AWAITING_DAYS` (padrão 3) dias e sua última mensagem tem pergunta ou pedido (mesma
  heurística de "pedido" das dívidas de resposta, ao contrário).
- **Seção semanal** "Esperando resposta deles" no briefing de segunda: até 3, mais antigas
  primeiro, com quem, há quanto tempo e o trecho da sua mensagem.
- **Ações**: ✖ ignorar (não pergunta de novo sobre essa mensagem) e 🔔 lembrar (lembrete para
  amanhã 9h "cobrar <pessoa>"). O EVI **nunca** manda mensagem ao contato.
- Flag `EVI_AWAITING_ENABLED` (padrão ligado — decisão do usuário em 18/10).

## Impact

Novo: `agent/services/awaiting_reply.py`. Alterado: `agent/services/briefing.py`,
`agent/services/telegram_handler.py` (ações), `agent/db.py`, testes e simulação.
Specs: `proactive`. Sem container novo; sem LLM.

## Validação em uso real

Janela de 2 semanas (2 segundas): ≥ 1 item mostrado por semana; ação (ignorar ou lembrar) em
≥ 30 % dos itens; 0 itens em que a pessoa já tinha respondido.

## Out of scope

- Enviar a cobrança automaticamente (proibido: sem mensagens a terceiros).
- Grupos; e-mail (só WhatsApp).
