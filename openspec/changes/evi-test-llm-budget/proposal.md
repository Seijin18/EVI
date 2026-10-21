## Why

A verificação gasta cota de LLM sem necessidade. Cada task de comportamento e cada fechamento
de change rodam `evi-sim run --repeat 3 --llm live`, que chama o Gemini/OpenRouter de verdade
em **todas** as chamadas do cenário, inclusive nas que não mudaram. Depois vem um `--llm record`
só para gravar o cassete. O `llm-eval` também reavalia todos os casos a cada rodada. Os cassetes
já são indexados pelo hash da requisição normalizada, então o sistema sabe quais chamadas mudaram.
Prioridade de produto: a próxima fila (brainstorm de 20/10, `docs/drafts/`) foi ordenada para
gastar o mínimo de requisições; os testes precisam acompanhar.

## What Changes

- **Novo modo `--llm fill` no `evi-sim`**: chamada com requisição já gravada é servida do cassete;
  só o que mudou vai ao LLM real. Com `--repeat N`, cada tentativa parte do cassete original, de
  modo que **só as chamadas novas** são exercitadas N vezes ao vivo. A tentativa aprovada regrava
  o cassete (substitui o passo `--llm record`).
- Relatório do `evi-sim` separa chamadas **reais** de **servidas do cassete**, com tokens reais.
- **Cache do `llm-eval`** por (tarefa, provedor, modelos, prompt, schema, amostra): rodar de novo
  sem mudar prompt/modelo custa zero. `--no-cache` força chamadas reais.
- Regra de verificação do projeto (`config.yaml`, `CLAUDE.md`, `docs/testing.md`, comandos
  `/implement-change` e `/run-queue`) passa de `--llm live` para `--llm fill`; `live` completo
  fica para checagem periódica de deriva do modelo.

## Impact

Código só de teste: `agent/testing/sim/{cassette,runner,report}.py`, `agent/llm.py` (nome do
provedor sim), `agent/services/llm_structured.py` (modo sim), `scripts/evi-sim`,
`agent/testing/llm_eval/`, `agent/testing/cli.py`. Produção inalterada (provedores `sim-*` só
existem com `EVI_SIM=1`). Spec: `testing`. Sem container novo; sem LLM.

## Validação em uso real

Janela: os 3 próximos changes da fila. Tokens reais de LLM gastos em verificação por change ≤ 30 %
do que o mesmo Verify custaria em `live` (relatório do `evi-sim` mostra os dois números); 0 change
fechado com cassete desatualizado (CI replay verde).

## Out of scope

- Mudar o critério de aprovação (N/N para `critical`, ≥ 2/3 para os demais).
- Trocar o modelo do chat ou dos juízes.
- Cache de LLM em produção.
