## Context

- Lembretes (`evi-reminders`): tabela `reminders`, presets de recorrência, loop in-process
  (`reminder_loop._run`, tick 30 s) que dispara e grava `reminder_fires`; tools
  `create_reminder`/`snooze`/`complete`/`cancel`, criação só por pedido explícito do usuário.
- Injeção (`evi-prompt-injection-model`): `WRITE_TOOLS` + `@guarded_write`; guarda por origem
  do turno; só `graph.py` faz `bind_tools`.
- Teto de gasto do chat: nenhum explícito (Gemini); tarefas agendadas precisam de teto próprio.

## Decisions

### 1. Modelo
Tabela `scheduled_tasks(id, title, prompt, next_at, repeat, active, created_at, last_run_at,
last_status, runs_today, runs_day)`; mesmos presets e cálculo de próxima ocorrência dos
lembretes (reusar a função). `title` curto derivado do pedido.

### 2. Tools
`create_scheduled_task(prompt, due_at, repeat)`, `list_scheduled_tasks()`,
`cancel_scheduled_task(id_or_title)`, `pause/resume`. São tools de escrita sobre o próprio
EVI (`@guarded_write`): só por pedido explícito no turno do usuário, nunca a partir de
conteúdo externo. Teto de 10 ativas.

### 3. Execução
O loop (a cada tick) pega tarefas com `next_at <= now`, ativas, respeitando 6 execuções/dia
(contador por dia local). Para cada uma: monta um turno com `channel='scheduled'`, sessão
própria (`scheduled:<id>`, sem histórico do chat), e roda o grafo com **um conjunto de tools
filtrado**: todas as tools registradas menos `WRITE_TOOLS` e menos as próprias tools de
agendamento/lembrete (`build_graph(tools=read_only_tools())` — o grafo hoje recebe
`get_all_tools()`; aceitar uma lista). Prompt do sistema acrescenta: "Execução agendada pelo
usuário: responda direto, sem perguntas de volta." Resultado → Telegram:
"🗓 <título>\n<resposta>". Fora da thread do loop dos lembretes (executor de 1 worker) para não
atrasar lembretes. Timeout 90 s.

### 4. Falha
Erro/timeout → `last_status='error'`, avisa uma vez ("Não consegui rodar '<título>' agora;
tento na próxima"), segue para a próxima ocorrência. Teto do dia estourado → adia para o dia
seguinte e avisa uma vez.

### 5. Segurança
Defesa em profundidade: (a) tools de escrita não estão ligadas no grafo agendado; (b) a guarda
por origem recusa escrita em `channel='scheduled'` mesmo se uma tool escapar; (c) conteúdo
externo continua delimitado. Teste: um prompt agendado "apague meus e-mails de promoção" não
consegue apagar nada.

### 6. Flag
`EVI_SCHEDULED_TASKS_ENABLED` (padrão `true`).

## Riscos

- Custo: ≤ 6 chamadas de chat/dia.
- Concorrência com o chat: sessão própria, executor separado.
- RAM: nenhuma relevante.

## Out of scope

Tarefas que escrevem; cron livre.
