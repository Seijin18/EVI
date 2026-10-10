---
description: Execute the whole OpenSpec queue (BACKLOG "Fila atual") change after change until it is empty
argument-hint: "[--from <slug>] [--until <slug>]"
model: opus
---

# Executar a fila de changes até o fim

Você é o **orquestrador da fila**. Execute, em ordem, todos os changes da tabela
"Fila atual" de `openspec/BACKLOG.md` — propor (quando ainda não houver proposta),
implementar, verificar, arquivar e passar para o próximo — **sem parar**, exceto nos
pontos de parada definidos no fim. Argumentos opcionais: `$ARGUMENTS`
(`--from <slug>` começa nesse item; `--until <slug>` para depois de arquivá-lo).

A implementação de **cada** change segue o procedimento de
[`implement-change.md`](implement-change.md) — Passo 1 (loop de tasks) e Passo 2
(fechamento) — e a mesma política de modelos (Opus orquestra; `implementer` Sonnet;
`reviewer` Opus; `explorer` e `test-runner` Haiku). Leia esse arquivo uma vez no início.
As diferenças estão abaixo e prevalecem sobre ele.

## Estado persistente (sobrevive a compactação e a interrupção)

Mantenha `openspec/queue-run.md` (criar se não existir; versionado):

```markdown
# Execução da fila — iniciada <data>
## Estado
- Change atual: <slug> (fase: propor | implementar | fechar) — task <n.n>
- Concluídos: <slug> (arquivado <data>, commits <primeiro..último>), ...
- Pulados: <slug> — <motivo>
## Decisões tomadas sem o usuário
- <data> <slug>: <decisão> — <por quê>
## Pendências do usuário (não bloqueantes)
- [ ] <ação> — <por que é necessária> — <comando/caminho exato>
## Bloqueios
- <data> <slug>: <o que parou e o que foi tentado>
```

Atualize-o e faça commit dele **a cada task fechada e a cada mudança de fase**. Se o
contexto for compactado ou a execução retomada, a primeira coisa a fazer é ler esse
arquivo, `openspec list` e `git log --oneline -15`, e continuar de onde parou — nunca
refazer o que já está commitado.

## Passo 0 — Preflight global (a única rodada de perguntas)

1. Leia a "Fila atual" do `BACKLOG.md`, `openspec/queued/README.md` e as seções da fila
   em `openspec/specs/roadmap.md`. Monte a lista ordenada de changes e classifique cada
   um: **ativo** (`openspec/changes/`), **proposto** (`openspec/queued/`) ou **só no
   roadmap** (precisará de proposta).
2. Classifique itens **condicionais** — o roadmap diz "abrir só se…", "reabrir quando…"
   ou depende de dados de uso real que ainda não existem (ex.: #38 "só se o ack do #44
   não bastar"). Esses **não** são implementados nesta execução: registre em "Pulados"
   com a condição, e siga. Itens em "Deferido"/"Cortado" do roadmap nunca entram.
3. `test-runner`: linha de base (`pytest tests/unit`, `evi-test smoke`, ruff,
   `openspec validate --specs`, `docker compose ps`). Base vermelha → ponto de parada.
4. Levante **tudo** que a fila inteira vai exigir de você, olhando proposals, designs e
   o roadmap: segredos (ex.: `EVI_SIM_GEMINI_API_KEY`), pacotes, decisões de produto
   em aberto. Separe em:
   - **bloqueante para implementar/verificar** → pergunte agora, numa única mensagem;
   - **necessário só para ativar em produção** (ligar flag no `.env`, criar schedule no
     Windmill, instalar timer systemd com `sudo`, reconectar OAuth) → **não** pergunte;
     vai para "Pendências do usuário" e é entregue no fim.
5. Depois da resposta, não interrompa mais o usuário fora dos pontos de parada.

## Passo 1 — Para cada change da lista, em ordem

### 1a. Ativar
- `openspec list` deve estar vazio (ou conter exatamente este change).
- Proposto em `queued/` → `git mv openspec/queued/<slug> openspec/changes/<slug>`.
- Antes de implementar, peça ao `explorer` para revalidar os paths de `Files:` e os
  testes de `Verify:` contra o código **atual** (changes anteriores da fila mudaram a
  base). Ajuste `tasks.md`/`design.md` se preciso — é sincronização, registre em
  "Decisões".
- `openspec validate <slug> --strict`.

### 1b. Propor (só para itens que existem apenas no roadmap)
Você (Opus) escreve a proposta — é trabalho de julgamento, não delegue a Sonnet/Haiku.
- `openspec new change <slug>`; use o `explorer` para localizar o código envolvido.
- Siga `openspec/config.yaml` (`rules.proposal`, `rules.tasks`, `rules.design`) e o
  formato dos changes já escritos em `openspec/queued/` e `openspec/changes/`:
  proposal com Why / What Changes / Impact / **Validação em uso real** / Out of scope;
  design com decisões, RAM, riscos e Out of scope; 5–12 tasks com SCN, `Files:` (≤ 5)
  e `Verify:`; specs delta com cenários `SCN-*` novos.
- Escopo = o que o roadmap descreve para a etapa, nada além. Toda decisão que o roadmap
  deixou em aberto: escolha a opção mais conservadora e reversível (atrás de flag,
  default desligado se mudar comportamento em produção) e registre em "Decisões".
- Inclua cenários de simulação (`tests/sim/scenarios/<área>/`) no `Verify:` das tasks de
  comportamento, depois que o `evi-sim-harness` estiver arquivado.
- `openspec validate <slug> --strict`; commit `docs(openspec): propose <slug>`.

### 1c. Implementar e fechar
Passo 1 e Passo 2 de `implement-change.md`, com estas diferenças:
- No fechamento, **ative o próximo change** (não pare para perguntar).
- Verificação final de cada change, depois que o `evi-sim-harness` existir:
  `./scripts/evi-sim run --tag critical --repeat 3 --llm live` além dos gates de sempre,
  e `--llm replay` para garantir que a CI continua verde. Mudou prompt? Regrave os
  cassettes afetados (`--llm record`) no mesmo commit.
- A janela de "Validação em uso real" (7–14 dias) **não** é esperada: o archive acontece
  quando tasks e gates passam; o KPI e o limiar vão para "Pendências do usuário" como
  "avaliar em <data>".

### 1d. Entre um change e o próximo
- `test-runner`: suíte unitária completa, smoke, ruff, `openspec validate --specs`,
  `./scripts/evi-test container` (sistema montado). Vermelho → conserte antes de seguir.
- Atualize `openspec/queue-run.md` e faça commit.

## Erros: contornar antes de parar

Antes de declarar um bloqueio, tente o contorno razoável e registre o que tentou:

| Situação | Contorno |
|---|---|
| Teste/implementação falha | 2 rodadas de `implementer` + seu diagnóstico; depois considere simplificar a abordagem dentro do design |
| Cota do Gemini esgotada (429) / rede instável | siga com tasks que não usam LLM live; adie as verificações `--llm live` para o fim do change; use `--llm replay` onde houver cassette; espere e tente de novo uma vez |
| Container não sobe / porta ocupada | `docker compose logs` via `test-runner`; recrie só o serviço do change; nunca derrube volumes |
| Dependência Python nova | adicione pinada em `agent/requirements.txt`, reconstrua a imagem, rode o container smoke |
| Path/design defasado | corrija o change (sincronização) e registre |
| Algo exige ação manual só em produção | registre em "Pendências do usuário" e siga |

## Pontos de parada (os únicos)

Pare, atualize `openspec/queue-run.md` (seção "Bloqueios"), faça commit e explique em
poucas linhas o que precisa de você, quando:

1. uma task segue falhando após os contornos acima e o problema não está no seu alcance;
2. falta algo que só o usuário fornece, sem contorno, e que bloqueia implementar ou
   verificar (não apenas ativar em produção);
3. a próxima ação seria destrutiva ou externa: apagar dados ou volumes, `reset --hard`,
   tocar contas reais (`scripts/*-verify.sh`, `--live-*`), enviar mensagem real, `push`,
   `sudo`;
4. a implementação exigiria mudar o comportamento prometido ao usuário de forma que o
   roadmap não cobre (decisão de produto, não técnica);
5. a base regrediu por causa externa à fila (ex.: Docker parado, disco cheio,
   dependência quebrada upstream) e você não consegue restaurá-la sem os itens do 3.

Fora desses casos, decida, registre em "Decisões" e siga.

## Ao terminar a fila

Responda com:
- changes arquivados (com intervalo de commits) e pulados (com a condição);
- decisões tomadas sem o usuário que valem a pena revisar;
- **Pendências do usuário** em ordem de execução, cada uma com o comando ou caminho
  exato (flags do `.env`, schedules no Windmill, timer systemd, avaliações de uso real
  com data);
- estado final dos gates.

Nunca faça `push`. Os commits ficam locais para o usuário revisar.
