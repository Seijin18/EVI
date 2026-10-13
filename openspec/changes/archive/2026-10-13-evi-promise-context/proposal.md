## Why

As promessas capturadas das mensagens do usuário (`evi-reply-debts`, §2) olham só a
frase dele: "Pode deixar", "Aí eu te aviso" e "Vou ver aqui e já te passo" viram itens
sem objeto, sem data e sem como agir. Ao mesmo tempo, um "Pode deixar" em resposta a
"me manda o orçamento amanhã?" **é** uma promessa real: o objeto está na mensagem do
contato. Um filtro pela frase do usuário erra para os dois lados, e só o contexto da
conversa decide. Prioridade de produto: produtividade (dívidas de resposta e promessas)
logo abaixo da entrega proativa. A extração de promessas por LLM ficou explicitamente
fora de escopo em `evi-reply-debts`; este change é a continuação.

## What Changes

- O padrão de promessa continua sendo o **gatilho** (barato, sem LLM). Casou: 30 min
  depois, o EVI lê a conversa (antes e depois, os dois lados) e pergunta ao LLM se há
  compromisso do usuário, **o quê**, **o prazo** (resolvido no código) e se **já foi
  cumprido**.
- Camada `llm_structured` com provedor por tarefa (`openrouter` | `ollama` | `gemini`),
  saída JSON nativa e teto de gasto diário. Default medido: **OpenRouter com retenção zero**
  (`google/gemma-4-31b-it`: 90% nos simulados, 96% nos reais); nenhum modelo que cabe na GPU local passou
  de 67% (ver design). **Decisão do usuário (2026-10-12):** trechos de conversa podem sair da
  máquina para endpoints com retenção zero (OpenRouter `zdr` + `data_collection: deny`).
- Avaliador versionado (`./scripts/evi-test llm-eval promise`) como gate para trocar
  modelo/prompt.
- Se o LLM confirmar, a promessa entra com título derivado do contexto ("Mandar a
  modelagem para a Eliana") e data resolvida; se não, nada é guardado.
- Se o LLM falhar, a promessa fica oculta (`needs_eval`) e é reavaliada; após 48 h sem
  avaliação, entra como hoje.
- A avaliação roda em segundo plano: o webhook não espera o LLM.
- Reavaliação única das promessas `pending` existentes, pelo mesmo caminho.
- Canais do WhatsApp (`@newsletter`, `@broadcast`) nunca são conversas diretas (já
  corrigido; a spec passa a dizer isso).

## Impact

Novo: `agent/services/promise_context.py`, `tests/unit/test_promise_context.py`,
`tests/sim/scenarios/reply-debts/SIM-DEBT-07…`, `SIM-DEBT-08…`.
Novo também: `agent/services/llm_structured.py`, `agent/testing/llm_eval/`,
`tests/eval/promise_cases.yaml`. Alterado: `agent/services/promises.py`, `agent/main.py`,
`agent/services/whatsapp_processor.py` (datas), `agent/db.py`, `.env.example`,
`docs/testing.md`. Specs: `messaging-whatsapp`, `providers`, `testing`. Sem container novo.
Custo estimado: < US$ 0,20/mês.

## Validação em uso real

Janela de 7 dias, pelo relatório semanal (`/jobs/usage-report`, tipo `promise`):
- taxa de ação (feito/descartado/agendado) das promessas ≥ 30% (hoje ~0%);
- ≤ 1 promessa/dia sem objeto ("Pode deixar" como título) no briefing.

## Out of scope

- Mudar a detecção de "esperando sua resposta" (continua determinística).
- Gravar as mensagens `fromMe` na timeline do contato e usar o perfil do contato no
  prompt — ambos em `evi-contact-knowledge` (fila).
- Promessas em grupos.
- Usar o LLM para detectar promessas sem padrão (gatilho continua sendo a lista).
