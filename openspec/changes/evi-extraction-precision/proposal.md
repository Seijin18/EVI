## Why

Em 20/10 o briefing das 07h listou uma "pendência" do WhatsApp que não era: o Felipe respondeu
"Boa" 22 s depois de uma mensagem do usuário — um aceno, não um pedido — e o item chegou sem
contexto. As dívidas de resposta são determinísticas (`docs/ux-review-2026-10.md` P3) e a lista
de "mensagens de encerramento" não cobre a conversa real ("boa", "massa", "demorou"…); o mesmo
vale para as tarefas extraídas por regex (`enviar|mandar` em qualquer frase: "As empresas
gostam do fornecedor enviar a NF…" virou tarefa). Só as promessas passam pelo juiz LLM com
contexto. Meta de produto: precisão e pontualidade definem a confiança no briefing
(Poke, `docs/product-review-2026-10-18.md`). Além disso, 👍/👎 por reação do Telegram é o
feedback mais barato e hoje não é capturado.

## What Changes

- **Dívidas de resposta**: vocabulário de encerramento ampliado (v3); regra "aceno logo depois
  de fala sua" (≤ 3 palavras, sem pedido, ≤ 10 min após sua última mensagem); **juiz LLM só
  para os ambíguos** (últimas mensagens da conversa, veredito guardado por mensagem, falha
  segura = regra determinística); o item do briefing mostra o que o usuário disse antes.
- **Tarefas extraídas por regex** (tipo `task`) passam pelo mesmo caminho assíncrono das
  promessas (`needs_eval`) com um juiz próprio: "isso é um compromisso/pedido que o usuário
  precisa cumprir?".
- **Reações do Telegram** (`message_reaction`): 👍/👎 em mensagem do briefing ou resposta do
  chat vira o mesmo feedback dos botões e de `/bom` `/ruim`.
- Flags `EVI_DEBT_JUDGE` e `EVI_TASK_JUDGE` (ligadas por padrão), tarefas `DEBT` e `TASK` em
  `llm_structured` (OpenRouter ZDR, teto diário já existente).

## Impact

Alterado: `agent/services/reply_debts.py`, novos `debt_judge.py` e `task_judge.py`,
`agent/services/briefing.py`, `agent/services/reminder_loop.py`, `agent/services/llm_structured.py`,
`agent/services/telegram_poller.py`, `agent/services/telegram_handler.py`, `agent/main.py`,
`agent/db.py` (colunas em `wa_conversation_state` e `turn_log`), testes, `llm-eval`, simulação.
Specs: `messaging-whatsapp`, `proactive`, `testing`. Sem container novo. Nova superfície de LLM
(conteúdo de terceiros): `wrap_external` + revisão leve de segurança.

## Validação em uso real

Janela de 7 dias (até 27/10): ação em dívidas de resposta ≥ 30 % (hoje 14 %); nenhuma
dívida reportada pelo usuário como "sem pedido"; ≥ 1 reação 👍/👎 registrada no relatório
semanal.

## Out of scope

- Reescrever a extração de eventos; mudar o limiar de 4 h; responder mensagens pelo usuário.
- Expirar tarefas vencidas no briefing: a listagem já exclui itens com data passada
  (`list_pending_commitments`).
- Reações em mensagens de lembretes ou de alertas.
