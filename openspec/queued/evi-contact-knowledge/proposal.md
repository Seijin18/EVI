## Why

O aprendizado de contato (`evi-contact-learning`, 2026-06-17) existe mas não entrega:
nenhum agendamento roda `/jobs/contact-learn`; 41 de 42 `profile.md` têm só o
cabeçalho; a única síntese trata a data de criação do perfil como "reunião marcada".
Mesmo rodando, o desenho não serviria: cada execução **acrescenta** uma "Síntese (data)"
narrativa ao fim do arquivo, enquanto `read_profile_excerpt` lê os **primeiros** N
caracteres — quem consome o perfil (extração por LLM, `get_contact_info`) nunca vê a
síntese mais recente. E a timeline só tem mensagens recebidas: metade da conversa falta.
Prioridade de produto: promessas e dívidas de resposta precisam saber quem é a pessoa e
o que está em aberto com ela (`evi-promise-context`).

## What Changes

- **Timeline com os dois lados**: mensagens `fromMe` diretas passam a ser gravadas na
  timeline do contato (como `[eu] …`), sem entrar na extração.
- **Perfil estruturado, substituído e não acrescentado**: `profile.md` passa a ter
  seções gerenciadas — `## Fatos` (fatos estáveis, cada um com a data da mensagem que o
  sustenta) e `## Em aberto` (assuntos pendentes, reescrita a cada atualização) — e
  `## Notas`, só do usuário, nunca tocada pelo EVI.
- **Atualização incremental**: o LLM recebe os fatos atuais + as mensagens novas desde a
  última atualização e devolve JSON (adicionar/remover fatos, novo "em aberto"); o código
  aplica. Metadados do arquivo nunca vão ao prompt. Fato sem data de evidência é descartado.
- **Leitura única**: `read_contact_knowledge(jid)` devolve Fatos + Em aberto (limitado);
  `get_contact_info`, extração por LLM e `evi-promise-context` passam a usá-la.
- **Agendamento diário** no Windmill, só para contatos com mensagens novas, por
  recência, com teto por execução.
- Canais, broadcasts e grupos não ganham pasta de contato.
- Migração única: sínteses antigas saem do `profile.md` para `history.md`.

## Impact

Novo: `agent/services/contact_knowledge.py`, `tests/unit/test_contact_knowledge.py`,
`tests/sim/scenarios/contact-memory/`, `windmill/f/integrations/contact_learn.schedule.yaml`
(ou passo documentado na UI). Alterado: `agent/services/contact_learning.py`,
`agent/services/contact_learn_cron.py`, `agent/services/contact_filesystem.py`,
`agent/services/reply_debts.py` (grava `fromMe` na timeline), `agent/tools/contact_tool.py`,
`agent/services/whatsapp_llm_extract.py`, `agent/services/promise_context.py`.
Specs: `data-long-memory`. Sem container novo. Modelo default medido: OpenRouter com
retenção zero (`qwen/qwen3.8-27b`: 8/8 nos simulados e sem fatos inventados nos reais;
locais ≤ 5/8 e aceitam injeção). Aprovado pelo usuário em 2026-10-12. Custo estimado: < US$ 0,50/mês, dentro do teto diário de
`llm_structured`.

## Validação em uso real

Janela de 7 dias após ligar o agendamento:
- ≥ 80% dos contatos com ≥ 3 mensagens na semana têm `## Fatos` ou `## Em aberto`
  atualizado na semana;
- auditoria de 10 perfis: 0 fatos sem evidência na timeline, 0 fatos vindos de metadado;
- títulos de promessa (`evi-promise-context`) nomeiam objeto e pessoa em ≥ 70% dos casos.

## Out of scope

- Grafo de conhecimento (Graphiti/Neo4j) e embeddings de contato.
- Contatos de grupo (participantes) — só conversas diretas.
- Edição de fatos pelo chat ("anota que a Ana é minha chefe") — próximo passo, se o
  perfil se provar útil.
- `profile_updater` (regex "sou o…/trabalho na…" sobre as mensagens do próprio usuário
  no chat de controle): fica como está; avaliar remoção em change próprio.
