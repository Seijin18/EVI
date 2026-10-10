## Why

Hoje não há como saber se o EVI está funcionando **para o usuário**. `/metrics`
conta requisições e latência de webhook; `logs/telegram.jsonl` registra tools mas é
rotacionado (estava vazio em 2026-10-10). Os sinais que importaram na revisão de
produto — 0 de 37 compromissos confirmados, uso caindo a zero, stack parada 6
semanas — só apareceram porque alguém foi consultar o Postgres à mão. Nenhum change
anterior definiu como medir se cumpriu o objetivo depois de entrar em uso.

O `evi-sim-harness` valida **antes** de integrar; este change valida **depois**, com
o uso real, e fecha o ciclo: falha real vira cenário de simulação. Também é a
linha de base para medir o briefing (#40), que vem logo depois.

## What Changes

- **Registro de turnos** (`turn_log`, Postgres): canal, pedido, resposta (truncada),
  tools chamadas com `ok`/`reason` estruturados (coletados do `ToolResult`), latência,
  chamadas ao LLM, erro, e marcação de teste.
- **Sinais de resultado**:
  - explícitos: `/bom` e `/ruim [motivo]` sobre o último turno;
  - implícitos (job noturno): correção ("não", "errado", "na verdade…") ou reformulação
    do mesmo pedido em até 3 min, tool que falhou sem continuação, "não consigo";
  - de domínio: compromisso confirmado × dispensado.
- **Relatório semanal** (`/jobs/usage-report`): KPIs (dias ativos, turnos, taxa de
  sucesso por turno, falhas por tool e motivo, taxa de correção, latência p50/p95,
  LLM por turno, confirmação de compromissos) comparados com a semana anterior e com a
  linha de base; lista curta de turnos para revisar. Salvo em
  `EVI_WORKSPACE/reports/` e resumido no Telegram.
- **Sonda diária somente-leitura** em produção: lista eventos de hoje, tarefas e 1
  e-mail pelo caminho real (sem LLM, sem escrita); avisa uma vez por dia no Telegram
  se uma integração falhar (ex.: OAuth expirado).
- **Higiene de dados de teste**: turnos/linhas de teste marcados e excluídos dos KPIs;
  script de limpeza (dry-run por padrão) para o que os harnesses live já gravaram.
- **Do uso real para a simulação**: `evi-sim promote <turn_id>` gera rascunho
  anonimizado de cenário; captura de *formatos* novos de payload do Evolution (só
  estrutura) para manter os fakes fiéis.
- **Regra de processo**: todo change de comportamento declara na proposta uma seção
  "Validação em uso real" (KPI + limiar + janela de 7 dias), avaliada pelo relatório
  e registrada no BACKLOG.

## Impact

Novo: `agent/services/turn_log.py`, `agent/services/usage_signals.py`,
`agent/services/usage_report.py`, `agent/services/probe.py`,
`agent/testing/sim/promote.py`, `windmill/f/integrations/usage_report.py`,
`windmill/f/integrations/probe.py`, `scripts/evi-cleanup-test-data`.
Alterado: `agent/db.py`, `agent/main.py`, `agent/services/tool_result.py`,
`agent/services/chat_commands.py`, `agent/services/metrics.py`,
`openspec/config.yaml`, `.gitignore`. Spec: `testing`.
Sem container novo.

## Validação em uso real (deste próprio change)

- Relatório semanal gerado e entregue em 2 semanas seguidas.
- Sonda detecta uma falha induzida (credencial do Windmill trocada em teste manual)
  em até 24 h.
- ≥ 1 cenário promovido do uso real para `tests/sim/scenarios/from-usage/`.

## Out of scope

- Dashboard (Grafana etc.): o relatório em Markdown + `/metrics` bastam para um usuário.
- Detecção de "desfazer" (evento criado pelo EVI apagado no Google em 24 h): exige
  ler o calendário retroativamente; fica para depois do briefing.
- Envio de qualquer dado para fora da máquina além do resumo no Telegram do próprio
  usuário.
- Watchdog de indisponibilidade do próprio EVI (é do #44 — precisa rodar fora dele).
