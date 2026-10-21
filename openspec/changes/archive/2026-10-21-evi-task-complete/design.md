## Decisions

### 1. Resolução em código, não no modelo
"Todas menos X" é difícil para o modelo sem IDs. `complete_tasks` lista as abertas
(`list_tasks`, até 100), filtra por `match` (substring normalizada ou ID) ou `all_open=True`,
remove as que casam com `except_match` e conclui cada uma via `complete_task`. Sem `match` e
sem `all_open`, recusa (nada é concluído por omissão). `match` ambíguo (casa >1) só conclui
tudo que casou quando o usuário listou o termo; o resultado sempre lista os títulos afetados.

### 2. Escrita
`complete_tasks` entra em `WRITE_TOOLS` (`@guarded_write`): só por pedido do usuário, nunca
em turno de job/agendado/conteúdo externo. Conclusão é reversível no Google Tasks.

### 3. Saída
`ToolResult` com `data={"completed": [...], "kept": [...], "unmatched": [...]}`; texto em
português com contagem. Falha parcial reporta quais falharam; erro OAuth usa o aviso padrão.

### 4. IDs
`list_tasks` imprime `• [id8] título — prazo` (8 primeiros caracteres do ID); a resolução
aceita o prefixo. Título continua envolto em `wrap_external`.

### 5. Windmill
`complete_task(task_id, gtasks, tasklist_id)`: `PATCH /tasks/v1/lists/{list}/tasks/{id}` com
`{"status":"completed"}`. Webhook `WINDMILL_WEBHOOK_COMPLETE_TASK`.

## Out of scope
Sem container novo (0 MB de RAM); sem portas novas.
