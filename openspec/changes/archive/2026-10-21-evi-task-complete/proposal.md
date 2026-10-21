## Why

Em 21/10 o usuário pediu no Telegram "finalize todas as tarefas em aberto, exceto a do mestrado".
A EVI respondeu que "não consegue finalizar várias de uma vez com uma exceção" e não chamou
nenhuma tool. A causa real: **não existe tool para concluir uma tarefa do Google Tasks** (só
`create_task` e `list_tasks`), e `list_tasks` não expõe os IDs que o Windmill já devolve. O
modelo inventou uma restrição em vez de dizer que faltava a capacidade.

## What Changes

- Script Windmill `complete_task` (PATCH `status=completed`) + operação no integration.
- Tool `complete_tasks(match, all_open, except_match)` (`@guarded_write`): resolve alvos em
  código a partir das tarefas abertas (título parcial, case-insensitive, ou ID), aplica as
  exceções e conclui em lote; devolve o que foi concluído, o que foi poupado e o que não casou.
- `list_tasks` passa a mostrar um ID curto por tarefa.
- Prompt do grafo: concluir tarefa usa `complete_tasks`; sem capacidade, dizer isso.

Prioridade de produto: ações de produtividade (tarefas) no Telegram.

## Impact

Novo: `windmill/f/integrations/complete_task.*`. Alterado: `agent/tools/task_tool.py`,
`registry.py`, `write_guard.py`, `agent/integrations/windmill.py`, `agent/services/response_format.py`,
`agent/services/tool_result.py`, `agent/graph.py`, fake Google/Windmill da simulação, docs/.env.
Sem container novo.

## Validação em uso real

Janela de 7 dias: pedidos de concluir tarefa atendidos sem resposta "não consigo" ≥ 90 %;
0 conclusões fora do alvo pedido.

## Out of scope

- Reabrir, editar ou apagar tarefas; múltiplas listas do Google Tasks.
- Investigar a numeração do "Confirmar 3" vs #94 (`confirm_commitments`) — change à parte.
- Limpar as tarefas "Implementar …" já existentes (ação do usuário).
