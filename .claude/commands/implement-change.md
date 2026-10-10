---
description: Implement every task of the active OpenSpec change, end to end, until archived
argument-hint: "[change-slug] (default: the single active change)"
model: opus
---

# Implementar o change OpenSpec até o fim

Você é o **orquestrador** desta implementação. Seu trabalho é decidir, revisar,
integrar e manter o plano em dia — não digitar a maior parte do código. Trabalhe de
forma autônoma e **só pare quando todas as tasks estiverem `[x]` e o change estiver
arquivado**, ou num dos pontos de parada listados no fim.

Change alvo: `$ARGUMENTS` (se vazio, o único change listado por `openspec list`).

## Política de modelos (obrigatória)

| Papel | Quem | Modelo | Use para |
|---|---|---|---|
| Orquestrador | você (esta sessão) | Opus | ler o plano, decidir ordem e abordagem, montar o briefing de cada task, avaliar divergências de design, diagnosticar falha que o implementer não resolveu, decidir o que entra no commit, sincronizar specs, arquivar |
| `implementer` | subagente | Sonnet | escrever código e testes de **uma** task e fazer o `Verify:` dela passar |
| `reviewer` | subagente | Opus | revisão de correção/segurança do diff de tasks com risco (ver abaixo) |
| `explorer` | subagente | Haiku | localizar símbolo, chamador, formato, teste existente — resposta em `path:linha — frase` |
| `test-runner` | subagente | Haiku | rodar `Verify:` e gates e devolver só PASS/FAIL + falhas |

Regras de economia:
- **Não leia código extenso no orquestrador.** Para localizar, chame `explorer`. Use
  `Read` direto só para trechos curtos que você precisa julgar.
- **Não escreva código de task no orquestrador**, exceto correções de 1–5 linhas depois
  de um diagnóstico seu (mais barato que outra rodada do implementer).
- **Não rode suíte longa no orquestrador**: delegue ao `test-runner`.
- Um subagente por task de implementação; tasks **independentes** (arquivos
  disjuntos, sem dependência no `tasks.md`) podem ir em paralelo — no máximo 2 ao mesmo
  tempo, e nunca duas que toquem o mesmo arquivo.
- Prompts de subagente são autocontidos e curtos: o texto da task, `Files:`, `Verify:`,
  os SCN da spec delta e **só o trecho do `design.md` que se aplica** (copiado, não
  "leia o design").

## Passo 0 — Preflight (antes de ficar autônomo)

1. `openspec list` e `openspec instructions apply --change <slug> --json` (só para
   `contextFiles`). Leia `proposal.md`, `design.md`, `tasks.md` e as specs delta do
   change. Não leia `Progress.md` nem `openspec/changes/archive/` (regra do projeto).
2. Peça ao `explorer` para confirmar que os paths citados em `Files:` existem ou são
   novos, e que os arquivos de teste citados em `Verify:` existem (ou serão criados
   pela própria task). Corrija o `tasks.md` se um path estiver errado — é sincronização,
   não mudança de escopo.
3. Peça ao `test-runner` a linha de base: `PYTHONPATH=agent python3 -m pytest tests/unit -q`,
   `./scripts/evi-test smoke`, `ruff check agent/ --select E,W,F --ignore E501`,
   `openspec validate --specs`. Se a base já estiver vermelha, pare e reporte.
4. Levante **tudo o que vai exigir o usuário** ao longo do change (segredos, `sudo`,
   pacotes do sistema, chave de API, decisão de produto em aberto no design) e pergunte
   **de uma vez, agora**. Exemplo para `evi-sim-harness`: `EVI_SIM_GEMINI_API_KEY`
   (projeto Gemini separado) para as tasks com `--llm live`. Depois disso, não
   interrompa o usuário salvo nos pontos de parada.

## Passo 1 — Loop de tasks

Para cada task `[ ]` na ordem do `tasks.md` (respeitando dependências):

1. **Briefing** → `implementer` com: task, `Files:`, `Verify:`, SCN, trecho do design,
   e qualquer decisão sua sobre ambiguidades.
2. **Resultado do implementer**:
   - `DONE` → siga.
   - `FAILED` → diagnostique você (leia a falha, use `explorer` se preciso). Corrija se
     for pequeno; senão, um segundo `implementer` com o diagnóstico. Máximo 2 rodadas de
     implementer por task.
   - `BLOCKED` ou `DIVERGENCE FROM DESIGN` → decida você. Se a divergência for melhor
     e couber no objetivo do change, aceite e **atualize `design.md`/spec delta agora**.
     Se mudar o escopo ou o comportamento prometido ao usuário, é ponto de parada.
3. **Revisão** → `reviewer` quando a task toca: isolamento de dados/contas, segurança,
   auth, envio de mensagens, concorrência/loops em background, migrações de banco, ou
   o caminho de produção do agente (`agent/main.py`, `agent/llm.py`, tools). Tasks só de
   teste, fixture, doc ou cenário YAML não precisam. `CHANGES REQUIRED` com `blocker` →
   volta ao implementer com os issues; `suspect` → você decide.
4. **Verificação independente** → `test-runner` roda o `Verify:` da task. Nunca marque
   `[x]` com base apenas no relato do implementer.
5. **Fechar a task**: marque `[x]` no `tasks.md` (com nota curta se houve divergência) e
   faça um **commit local** só com os arquivos da task (`git add <paths>`, nunca `-A`),
   mensagem no estilo do `git log` (`feat(escopo):`, `test:`, `fix(escopo):`), terminando
   com a linha `Co-Authored-By` indicada nas instruções da sessão. Nunca `push`, nunca
   `--no-verify`.
6. A cada 3 tasks fechadas, `test-runner` roda a suíte unitária inteira + ruff. Regressão
   → conserte antes de seguir.

Mantenha o contexto do orquestrador enxuto: depois de fechar uma task, registre para
si só o essencial (task, commit, decisões) — o detalhe já está no `tasks.md` e no git.

## Passo 2 — Fechamento do change

1. `test-runner`: suíte unitária, `./scripts/evi-test smoke`, ruff, `openspec validate --specs`
   e os comandos de verificação final da última task (ex.: `./scripts/evi-sim run --tag critical --repeat 3 --llm live`).
2. **Sincronizar**: compare o que foi implementado com `proposal.md`, `design.md` e as
   specs delta; ajuste o que divergiu para refletir o as-built.
3. `openspec archive <slug>`; depois `openspec validate --specs`.
4. Atualize `openspec/BACKLOG.md` (status do change → Done, data, resumo de 1–2 linhas),
   `Progress.md` (etapa + matriz de features), `openspec/specs/roadmap.md` (etapa →
   Done), contagens no `CLAUDE.md` (specs, smoke) se mudaram, e a tabela de
   `openspec/queued/README.md`.
5. Commit `docs(openspec): archive <slug>`.
6. **Não ative o próximo change** de `openspec/queued/` — isso é decisão do usuário.

## Pontos de parada (os únicos)

Pare, explique em poucas linhas e pergunte, quando:
- uma task continua falhando depois de 2 rodadas de implementer **e** do seu diagnóstico;
- a implementação exige mudar escopo ou o comportamento prometido na proposta;
- falta algo que só o usuário fornece e não foi levantado no preflight;
- uma ação seria destrutiva ou externa: apagar dados, `reset --hard`, tocar contas reais
  (`scripts/*-verify.sh`, `--live-*`), `push`, `sudo`;
- a suíte de base regrediu e a causa não está no change.

Em qualquer outro caso, decida e siga. Ao terminar, responda com: tasks concluídas
(com commits), divergências do design e como foram resolvidas, o que ficou para o
usuário fazer (ex.: configurar schedule no Windmill) e o próximo change da fila.
