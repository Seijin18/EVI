## Why

"Toda sexta às 18h, resuma meus e-mails da semana" ou "todo dia às 8h, me diga se tem
reunião com cliente" — no Perplexity (referência em `docs/ux-review-2026-10.md`) isso vira uma
tarefa agendada. No EVI, um lembrete agendado só repete um **texto fixo**; não há como pedir
que ele **rode uma pergunta** no horário. A base existe: o loop dos lembretes (presets de
recorrência) e o grafo com allowlist de tools por origem do turno.

## What Changes

- **Criar por conversa**: "toda sexta 18h, resuma meus e-mails da semana" → tarefa agendada
  com a pergunta, o horário e a recorrência (mesmos presets dos lembretes). Listar, pausar e
  cancelar por conversa.
- **Execução só de leitura** (decisão do usuário em 18/10): o turno agendado roda o agente com
  **apenas tools de leitura** (agenda, tarefas, e-mail, WhatsApp, contatos) — nada apaga, cria
  ou envia; o resultado chega no Telegram com o título da tarefa.
- **Tetos**: no máximo 10 tarefas ativas e 6 execuções por dia; execução que falha avisa uma
  vez e tenta na próxima ocorrência.
- Flag `EVI_SCHEDULED_TASKS_ENABLED` (padrão ligado).

## Impact

Novo: `agent/services/scheduled_tasks.py`, `agent/tools/scheduled_task_tools.py`. Alterado:
`agent/services/reminder_loop.py` (dispara), `agent/graph.py`/`agent/main.py` (turno só de
leitura), `agent/tools/registry.py`, `agent/db.py`, testes e simulação. Specs: `proactive`.
Sem container novo. Custo: uma chamada de chat por execução (≤ 6/dia).

## Validação em uso real

Janela de 14 dias: ≥ 1 tarefa agendada criada; ≥ 90 % das execuções entregues no horário
(± 2 min); 0 execuções com tool de escrita.

## Out of scope

- Tarefas que escrevem (criar evento, apagar e-mail, responder).
- Agendar por expressão cron livre.
