## Context

`list_debts` (reply_debts.py) filtra candidatos por tempo e por `is_closing_message` (vocabulário
fechado). O briefing mostra só o `last_in_preview`. As promessas usam `needs_eval` +
`promise_context` (juiz com a conversa, `run_structured`, tarefa `PROMISE`). Tarefas/eventos
nascem em `main.py` (`extract_commitment` → `insert_pending_commitment`) sem juiz.
Telegram: `ALLOWED_UPDATES = ["message", "callback_query"]`; o `message_id` do briefing fica no
snapshot (`session_tool_snapshots`); respostas de chat não guardam `message_id`.

## Decisions

1. **Dívida = regra primeiro, LLM só no ambíguo.** Ordem: encerramento (v3) → fora; pedido
   claro (`?` ou `looks_like_request`) → fica sem LLM; aceno curto logo após fala do usuário → fora;
   o restante (curto/sem pedido) é *ambíguo* → juiz.
2. **Juiz de dívida fora do caminho de leitura.** `list_debts` só lê veredito guardado
   (`wa_conversation_state.judge_in_id`, `judge_needs_reply`, `judge_at`); não chama LLM.
   `judge_candidates(limit=5)` roda no tick do `reminder_loop` (junto das promessas) e logo antes
   do briefing. Veredito vale para o `last_in_id` julgado; mensagem nova invalida.
   Sem veredito (LLM fora, teto, desligado) = candidato continua dívida (fail-safe: não
   esconder um pedido real).
3. **Contexto do juiz**: últimas 8 mensagens da timeline (`message_timeline`), os dois lados
   rotulados, cada texto de terceiro em `wrap_external`; saída `{needs_reply: bool, reason}` (≤ 120 car.).
   Tarefa `DEBT`, mesmo provedor/ZDR/teto diário das demais (`EVI_LLM_TASK_DEBT_*`).
4. **Contexto no item**: nova coluna `last_out_preview` (texto da última mensagem do usuário,
   truncado em 80); o briefing mostra `Felipe · "Boa" (você: "Vou esperar essa terminar…")`.
5. **Juiz de tarefa**: `task` vindo de `extract_commitment` entra como `needs_eval` (o mesmo
   atraso de 30 min e fallback de 48 h das promessas, `commitment_status_for` preservado para o
   estado final). Tarefa `TASK`: `{keep: bool, title, due}`; `keep=false` → `dismissed` com
   `confirmed_via='auto-eval'`. Falha/48 h → estado calculado pela regra (`pending`/`undated`).
   Eventos continuam sem juiz.
6. **Reações**: `ALLOWED_UPDATES` ganha `message_reaction`; `process_telegram_update` trata
   `message_reaction` só do chat autorizado: 👍 → `up`, 👎 → `down` (outros emojis ignorados;
   remover a reação não apaga). Alvo: (a) `message_id` do snapshot do briefing → `set_briefing_feedback`;
   (b) `turn_log.tg_message_id` (nova coluna, gravada quando a resposta do chat é enviada) →
   `feedback = 'bom'|'ruim'`. Mensagem desconhecida = ignorar. Webhook aceita o campo igual a `callback_query`.
7. **Nada de DDL destrutivo**: só `ADD COLUMN IF NOT EXISTS` no `init_db`.

## Risks

- Latência/custo: no máximo 5 julgamentos de dívida por tick e 3 de tarefa por minuto; teto
  diário existente (fail-closed no OpenRouter). Custo esperado < US$ 0,01/dia.
- Privacidade: conteúdo de terceiros só para OpenRouter ZDR (aprovado em 12/10), `wrap_external`
  em tudo (injeção: o juiz só devolve booleano + frase curta, nunca aciona tools).
- Falso negativo (esconder pedido real): juiz só vê candidatos ambíguos; pedido claro nunca passa por ele.

## Out of scope

Ver proposta.
