## Why

Em 21/10, "finalize todas as tarefas exceto a do mestrado" falhou de um jeito pior que um erro:
o EVI **inventou uma restrição** ("não consigo várias de uma vez com exceção") em vez de dizer
que não existia a tool. A lacuna só virou o change `evi-task-complete` porque o usuário
investigou. O usuário pediu (20/10) que o que o EVI não sabe fazer seja **registrado
internamente para virar change OpenSpec** (`docs/drafts/brainstorm-assistente-2026-10-20.md` §7).
O sinal implícito `cant_do` já existe em `usage_signals`, mas só vira contagem no relatório.

## What Changes

- Tool `report_capability_gap(pedido, o_que_falta, contorno)` e regra no prompt: sem capacidade,
  **não inventar restrição**. Registrar e responder "ainda não sei fazer isso; anotei como
  melhoria #N", com o contorno quando houver.
- **Registro de lacunas** (`capability_gaps`) com dedupe determinístico, contagem,
  primeira/última vez e exemplo anonimizado. Os sinais implícitos (`cant_do`, `/ruim`/👎 com tool
  inexistente) entram como candidatos. Há um espelho legível em `EVI_WORKSPACE/gaps/`.
- **Relatório semanal**: "🧩 Pedidos que eu ainda não sei atender" (top 3) com ⭐ importante /
  ✖ descartar; `/melhorias` lista tudo.
- **Exportar para OpenSpec**: `./scripts/evi-test gaps-export <id>` gera
  `openspec/proposals-inbox/<slug>/proposal.md` (modelo com a evidência), fora da fila. O
  usuário refina e enfileira numa sessão de código.

## Impact

Novo: `agent/services/capability_gaps.py`, `agent/tools/gap_tool.py`. Alterado:
`agent/tools/registry.py`, `agent/services/write_guard.py`, `agent/graph.py` (regra),
`agent/services/usage_report.py`, `agent/db.py`, `agent/testing/cli.py`. Spec: `agent-api`.
Sem container novo. LLM: **0 chamadas novas em background**. A tool é chamada dentro do turno
que já existe (+1 ida e volta só quando há lacuna, evento raro).

## Validação em uso real

Janela de 14 dias: 0 respostas com restrição inventada nos turnos com `cant_do` (revisão do
relatório); ≥ 1 lacuna real registrada; ≥ 1 exportada para `proposals-inbox/` em 30 dias.

## Out of scope

- Gerar o texto do change com LLM (`evi-gap-to-proposal`, depois da oficina).
- Implementar sozinho; escrever em `openspec/changes/` ou `queued/`.
- Lacunas que derrubariam guardas (pagar, enviar a terceiros sem aprovação): ficam como
  "recusado por regra", nunca como proposta.
