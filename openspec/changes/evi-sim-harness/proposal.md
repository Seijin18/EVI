## Why

A suíte atual (371 unit, smoke 13/13, harnesses offline) testa unidades com
LLM e integrações mockados. Os problemas que chegaram ao uso real não estavam
nas unidades e sim no sistema montado: o LLM escolhendo a tool errada, datas
relativas ("amanhã") resolvidas errado, envelopes do Windmill que nenhum mock
reproduzia (bug do `"criad"`), o dev bridge que nunca rodou no container. Os
harnesses "live" que existem hoje (`evi-telegram-verify.sh`, `--live-windmill`)
rodam contra as contas reais e **poluem os dados de produção** — a fila de
compromissos tem 3 linhas "Teste digest Telegram" geradas por eles.

Falta um nível de teste que exercite o sistema **como o usuário o usa**: mensagem
entrando pelo poller do Telegram ou pelo webhook do Evolution, LLM real, scripts
Windmill reais, estado verificável no fim — sem tocar em conta real. Ele vem
antes do briefing (#40) para que o briefing e tudo que vier depois nasçam
validados por ele. Prioridade de produto: confiabilidade das ações do usuário.

## What Changes

- **Nível L2 — simulação do sistema montado** (`evi-sim`): projeto compose isolado
  com a **mesma imagem** do `agent-api`, Postgres efêmero e um container de
  *fakes* nas bordas externas. Nada no caminho interno é mockado.
- **Fakes nas bordas, código real no meio**:
  - *fake Google* com estado (Calendar, Tasks, Gmail — só o subconjunto que os
    scripts usam);
  - *fake Windmill* que executa os **scripts reais** de `windmill/f/integrations/`
    interceptando `urllib` para o fake Google, e devolve os envelopes reais
    (`run_wait_result`), inclusive falhas injetáveis (OAuth expirado, timeout, 5xx);
  - *fake Telegram Bot API* (`getUpdates`/`sendMessage`) — o **poller real** roda;
  - *fake Evolution* (envio capturado); entrada por POST no webhook real com payloads
    no formato capturado do Evolution.
- **Relógio simulado** via libfaketime na imagem de simulação (sem mudança no código
  do agente): cenários dizem "D1 07:00" e o sistema inteiro vê essa hora.
- **Cenários em YAML** (`tests/sim/scenarios/`): estado inicial, passos (usuário
  fala, mensagem de contato chega, relógio avança, job dispara) e expectativas
  sobre **estado e efeitos** (evento criado com data X, nada apagado, nenhuma
  mensagem a terceiros, resposta em até N s) — não sobre texto exato.
- **Corpus inicial derivado do uso real**: ~20 cenários a partir dos pedidos reais
  registrados em `messages` (criar evento relativo, listar amanhã, resumir e limpar
  e-mail, renomear contato por número, revisar/dispensar compromissos, "o que você
  pode fazer?"), mais falhas de integração e 3 casos adversariais de injeção.
- **Repetição e taxa de aprovação** (LLM não é determinístico): `critical` precisa
  passar 3/3; demais ≥ 2/3. Relatório JSONL + Markdown em `logs/sim/`.
- **Modo record/replay do LLM** para a CI: gravado localmente com o Gemini real,
  reproduzido na CI sem chave nem cota.
- Duas costuras mínimas no código, inertes por padrão: `TELEGRAM_API_BASE` e a guarda
  de isolamento do projeto `evi-sim`.

## Impact

Novo: `docker-compose.sim.yml`, `agent/Dockerfile.sim`, `agent/testing/sim/`
(fakes, runner, schema), `tests/sim/scenarios/`, `tests/sim/cassettes/`,
`scripts/evi-sim`. Alterado: `agent/services/telegram_notify.py`,
`agent/services/telegram_poller.py`, `.github/workflows/ci.yml`,
`docs/testing.md`, `.env.example`. Spec: `testing`.
RAM: ~0,6 GB a mais enquanto a simulação roda (ver design).

## Out of scope

- Validação com base no uso real em produção (métricas de resultado, feedback,
  relatório semanal, promoção de falhas reais para cenários) — change seguinte,
  `evi-usage-validation` (`openspec/queued/`).
- Windmill server real dentro da simulação (schedules, OAuth real). Os scripts são
  reais; o agendador não. Fica como nível L3 opcional no roadmap.
- RAG/Qdrant e Neo4j nos cenários (prioridade secundária).
- LLM-as-judge para qualidade de texto: o campo existe no schema, desligado por padrão.
- Migrar `evi-telegram-verify.sh` e `evi-inbox-ux-verify.sh` para a simulação — os
  scripts ganham aviso de que tocam dados reais; a remoção vem depois de o L2 provar
  que os cobre.
