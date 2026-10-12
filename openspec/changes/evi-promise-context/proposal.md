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

- O padrão de promessa continua sendo o **gatilho** (barato, sem LLM). Casou: o EVI lê
  as últimas mensagens da conversa (os dois lados, até 24 h, máx. 10) e pergunta ao LLM
  se há compromisso do usuário e **o quê/para quando**.
- Se o LLM confirmar, a promessa entra com título derivado do contexto ("Mandar a
  modelagem para a Eliana") e data resolvida; se não, nada é guardado.
- Se o LLM falhar (timeout, parse), a promessa entra como hoje (sem regressão).
- A avaliação roda em segundo plano: o webhook não espera o LLM.
- Reavaliação única das promessas `pending` existentes, pelo mesmo caminho.
- Canais do WhatsApp (`@newsletter`, `@broadcast`) nunca são conversas diretas (já
  corrigido; a spec passa a dizer isso).

## Impact

Novo: `agent/services/promise_context.py`, `tests/unit/test_promise_context.py`,
`tests/sim/scenarios/reply-debts/SIM-DEBT-07…`, `SIM-DEBT-08…`.
Alterado: `agent/services/promises.py`, `agent/main.py` (webhook), `.env.example`,
`docs/testing.md`. Specs: `messaging-whatsapp`. Sem container novo.

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
