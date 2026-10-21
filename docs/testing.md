# EVI testing guide

## Níveis de verificação

| Nível | O que roda de verdade | O que é falso | Comando | Quando |
|---|---|---|---|---|
| L0 unit | funções | tudo em volta | `pytest tests/unit -q` | sempre (CI) |
| L1 `evi-test <feature>` | módulos + fixtures | LLM, Windmill, rede | `./scripts/evi-test <feature>` | sempre (CI) |
| L1c container smoke | imagem montada, /health, /tools | dados | `./scripts/evi-test container` | CI |
| **L2 `evi-sim`** | imagem, poller Telegram, webhook Evolution, LangGraph, LLM real, scripts Windmill, Postgres | Google, Telegram API, Evolution API, relógio | `./scripts/evi-sim run` | antes de cada change ser arquivado (`--tag critical --repeat 3 --llm fill`); CI em modo replay |
| L3 staging (futuro) | + Windmill server e schedules | Google | — | release maior |
| **L4 uso real** | tudo | nada | relatório semanal, sonda diária, `/bom` `/ruim` | contínuo — `evi-usage-validation` |

Ciclo: L2 aprova antes de integrar → L4 mede depois → falha real vira cenário L2.

### L4 — uso real

| Peça | Onde | Quando |
|---|---|---|
| `turn_log` | todo turno de `/chat`, Telegram e controle WhatsApp (tools com `ok`/`reason`, latência, chamadas ao LLM) | sempre |
| `/bom`, `/ruim [motivo]` | Telegram / controle WhatsApp — avalia o último pedido | quando quiser |
| Sinais implícitos (correção, reformulação, tool falhou, "não consigo") | `POST /jobs/usage-signals` | Windmill, todo dia |
| Relatório semanal | `POST /jobs/usage-report` → `EVI_WORKSPACE/reports/usage-YYYY-Www.md` + resumo no Telegram | Windmill, domingo 20h |
| Sonda somente-leitura | `POST /jobs/probe` (agenda, tarefas, Gmail, Telegram; sem LLM, sem escrita) | Windmill, 06:30 |
| Formatos novos do Evolution | `data/payload_shapes/` (valores redigidos), listados no relatório | a cada webhook |
| Tráfego de teste | `X-Evi-Test: 1` ou sessão `evi-test*`/`test-*`/`health-check*`/`tg-digest-verify*` → `is_test`, fora dos KPIs; `scripts/evi-cleanup-test-data` (dry-run; `--apply` apaga) | — |

Falha real → `./scripts/evi-sim promote <turn_id>` gera rascunho anonimizado em
`tests/sim/scenarios/from-usage/` com `expect: {todo: ...}`; o runner recusa o cenário
até a expectativa ser escrita por uma pessoa. Revisar o rascunho antes de commitar.

Todo change de comportamento declara `## Validação em uso real` (KPI, limiar, janela de
7 dias) na proposta; o resultado é registrado no BACKLOG quando a janela fecha.

> **Atenção:** `scripts/evi-telegram-verify.sh`, `scripts/evi-inbox-ux-verify.sh` e
> as flags `--live-*` rodam contra as contas reais (Telegram, Gmail, Calendar) e
> gravam no Postgres de produção. Prefira o L2 `./scripts/evi-sim`; use esses só
> para diagnóstico pontual, não para validar change.

## evi-sim (L2)

Sobe a imagem de produção num projeto compose isolado (`evi-sim`) com fakes de
Google, Telegram API e Evolution API, e conduz cenários YAML contra ela.

```bash
./scripts/evi-sim guard                       # checa isolamento (não toca produção)
./scripts/evi-sim up [--llm live|record|replay|fill]
./scripts/evi-sim run [--tag T] [--id SIM-RU-01] [--repeat N] \
    [--llm live|record|replay|fill] [--max-llm-calls N]
./scripts/evi-sim report                      # último relatório
./scripts/evi-sim down                        # derruba e apaga volumes
```

`run` já faz `guard` + `up`. Gate de change:
`./scripts/evi-sim run --tag critical --repeat 3 --llm fill`. Offline (igual ao CI):
`./scripts/evi-sim run --tag critical --llm replay`.
Briefing: `./scripts/evi-sim run --tag briefing --repeat 3 --llm fill` (passo `job: briefing`;
`reply_matches` do passo avalia o texto enviado ao Telegram).
Briefing legível (SIM-UX-01..03): o briefing vai ao Telegram como HTML (`parse_mode=HTML`) sem
marcadores `«externo`, em ≤ 25 linhas, com seções longas colapsadas em linha-resumo + comando.
`expect.telegram_message` avalia as mensagens enviadas ao usuário no passo: `parse_mode`,
`valid_html` (só `<b>/<i>/<code>`, balanceado, `<`/`&` escapados), `not_matches`, `max_lines`
(linhas não vazias; vale para cada mensagem) e `matches` (ao menos uma). "respondido N" sobre o
briefing novo é coberto pelo SIM-UX-03 (cassete gravado com `--llm record`).
Botões do briefing (SIM-UX-04, 0 chamadas de LLM): o Telegram falso registra o `reply_markup` de cada
`sendMessage` (devolve `message_id`), aceita `answerCallbackQuery` e `editMessageReplyMarkup` (atualiza o
teclado guardado), respeita `allowed_updates` e enfileira `callback_query` (`POST /_sim/telegram/callback`).
O passo `telegram_tap: {item: N, action: ok|no|up|dn, from_chat?: id, briefing?: last|first}` acha o
briefing mais recente (ou o primeiro) e usa o `callback_data` do botão gravado, procurado pelo rótulo
(nunca montado pelo runner); `reply` é o texto do `answerCallbackQuery`. Expectativas novas:
`telegram_keyboard: {contains, not_contains}` (rótulos do teclado após as edições),
`telegram_message: {has_keyboard, callback_data_matches, callback_data_max_bytes}`; `postgres` aceita `briefing_log`.
Dicas de descoberta (SIM-TIP-01/02, tag `briefing`): `job: briefing-evening` chama `/jobs/briefing?kind=evening&wait=true` e `telegram_tap` aceita `action: rm` (botão `N 🔔`, "lembrar amanhã às 9h"). A dica do briefing da manhã gira pelo dia do calendário entre as capacidades não usadas, então o SIM-TIP-01 conta a dica de lembrete em 4 manhãs seguidas (`telegram_sent_count_matching`, exatamente 1), cria um lembrete e prova que 4 manhãs seguintes não a repetem; o cassete normaliza a linha `💡 Dica:` para não depender do dia. O botão 🔔 respondido sai do teclado, então o segundo toque ("Já estava agendado") só é coberto pelos testes unitários.
Esperando resposta deles (SIM-AWAIT-01, tag `reply-debts`, 0 chamadas de LLM): o cenário começa em `M-1 06:00` e usa `clock: +Nd` (soma ao relógio simulado) para que a pergunta sem resposta ao Bruno fique a 4 dias da segunda e o "valeu, abraço!" à Carla a 5. As mensagens `from_me` pelo webhook gravam `last_out_at` e o `[eu]` da timeline; o briefing de `M0 07:00` lista só o Bruno ("há 4 d"), `N ✖` grava `awaiting_dismissed` (tabela aceita em `postgres`), uma mensagem nova sua reabre na segunda seguinte e `N 🔔` cria o lembrete "Cobrar Bruno" sem enviar nada ao contato.
Reply debts: `./scripts/evi-sim run --tag reply-debts --repeat 3 --llm fill` (sim.env liga
`EVI_REPLY_DEBTS_ENABLED`; `postgres` aceita `wa_conversation_state`; `reply_not_matches` exige que
o texto enviado ao Telegram NÃO case com a regex).
Promessas com contexto: `./scripts/evi-sim run --tag reply-debts --repeat 3 --llm fill` (SIM-DEBT-07/08/09;
sim.env liga `EVI_PROMISE_CONTEXT_ENABLED`, atraso de 10 min do relógio simulado e varredura a cada 5 s).
A avaliação não tem passo próprio: o cenário avança o relógio (`clock: +11m`) e o loop em processo
avalia a fila `needs_eval`; `postgres` aceita `within_s` (espera até N s pela contagem) e, em `where`,
`{contains: "texto"}` (ILIKE) e `{weekday: 1-7}` (dia ISO de uma coluna de data). O runner devolve ao
`findMessages` do fake Evolution cada `whatsapp_contact` enviado (contato e `from_me`), com timestamp do
relógio simulado. A chamada `run_structured("promise")` vai ao OpenRouter real (ZDR, teto
`EVI_LLM_TASK_DAILY_USD=0.50`) com a chave de `OPENROUTER_API_KEY` do `.env` (ou
`EVI_SIM_OPENROUTER_API_KEY`); em `record`/`replay` é gravada/servida no mesmo cassete do cenário
(chave `structured:<sha256>` de task+prompt+schema, com data/dia da semana/horários normalizados).
Precisão de extração (evi-extraction-precision, tag `reply-debts`): SIM-DEBT-10 prova que "Boa" 22 s depois da fala
do usuário não vira dívida sem veredito do juiz (`judge_needs_reply` nulo); SIM-DEBT-11 faz o briefing julgar
uma mensagem ambígua ("o sistema caiu de novo" continua listada com `você: "Te mando o orçamento hoje"`; "É isso aí"
julgado `needs_reply=false` sai) — o veredito é gravado em `wa_conversation_state.judge_needs_reply`; SIM-PREC-01
mostra o juiz de tarefa (`needs_eval` → `dismissed`/`auto-eval` para a frase genérica da NF, `undated` com título
"contrato" para o pedido real). Não há endpoint de avaliação: o `clock: D0 09:11` basta, o `reminder_loop` (sim.env,
varredura de 5 s) roda `process_due_task_evaluations` como faz com as promessas. As chamadas `DEBT`/`TASK` vão ao
OpenRouter ZDR em `live`/`record` e ao cassete em `replay`; o contador "LLM calls" do relatório só conta Gemini.
Conhecimento de contato: `./scripts/evi-sim run --tag contact-memory --repeat 3 --llm fill` (SIM-MEM-01/02/04).
O passo `job: contact-learn` chama `POST /jobs/contact-learn?wait=true` (atualiza fatos/"Em aberto" dos contatos com
mensagens novas; a chamada estruturada `CONTACT_KNOWLEDGE` usa o OpenRouter ZDR em `live`/`record` e o cassete em `replay`).
`expect.contact_profile: {jid, section?, matches?, not_matches?}` lê o `profile.md` do contato no container do sim e
aplica regex (sem diferenciar maiúsculas) ao arquivo ou a uma seção (`Fatos`, `Em aberto`). SCN-MEM-18 (JSON inválido não
altera o perfil) fica só nos testes unitários: o harness não injeta falha no LLM. Migração das sínteses antigas:
`./scripts/evi-test contact-knowledge-migrate [--apply]` (dry-run por padrão; só contagens).
Nomes de contato: `./scripts/evi-sim run --tag contact-names --repeat 3 --llm fill` (SIM-NAME-01/02/03). O fake Google
serve a People API (`people/me/connections`, paginada) a partir de `seed.contacts: [{name, phones, email?}]` e o script
Windmill real `list_contacts` roda contra ele (o e-mail do seed existe só para provar que o script o descarta). O passo
`job: contact-names-sync` chama `POST /jobs/contact-names-sync?apply=true&wait=true`; `expect.job_response_matches: <regex>`
(só em passos `job`) confere o JSON devolvido (ex.: `"protected_user": 1`). `push_name: ""` em `whatsapp_contact` omite o
pushName (número "pelado"). Relógio de segunda-feira: `M0 07:00` é a última segunda-feira até hoje, `M1` a seguinte
(`D<n>` continua contando dias); o briefing semanal "Conversas sem nome" só roda nesse dia. A sugestão `CONTACT_NAME_HINT`
é uma chamada estruturada (OpenRouter em `live`/`record`, cassete em `replay`); o prompt só depende do texto das mensagens.
Lembretes: `./scripts/evi-sim run --tag reminders --repeat 3 --llm fill` (o loop roda dentro do
`agent-api` com `EVI_REMINDERS_TICK_SEC=5` e lê o relógio libfaketime). Um passo `clock` aceita
`expect: {reply_within_s, reply_matches, no_reply}`: captura as mensagens enviadas ao Telegram
do usuário após a mudança de relógio (saída proativa, sem mensagem do usuário), como o passo `job`.
`postgres` aceita as tabelas `reminders` e `reminder_fires`.
Tarefas agendadas (SIM-SCHED-01/02, tag `scheduled`): o cenário começa numa segunda (`M0 10:00`), cria a tarefa
"toda sexta às 18h" pelo Telegram e avança o relógio com `clock: +4d` e `+8h`; o loop do `agent-api` (a cada 30 s reais)
dispara a tarefa e entrega "🗓 …" ao Telegram. `postgres` aceita a tabela `scheduled_tasks` e o filtro `turn_log`
`channel: scheduled` prova que o turno rodou. SIM-SCHED-02 agenda "apague meus e-mails de promoção" e confere
`gmail: {deleted_count: 0}` depois da execução (o turno agendado só tem tools de leitura).
Confiabilidade percebida: `./scripts/evi-sim run --tag reliability --repeat 3 --llm fill` (sim.env define
`EVI_SLOW_ACK_SEC=3`). Falha `slow:<segundos>` no Windmill (`fault: {windmill: {summarize_inbox: "slow:8"}}`)
atrasa e depois executa normalmente. `expect.messages_min: N` espera N mensagens no passo (ex.: "⏳" +
resposta; `reply_matches` vê todas, unidas por `\n`); `expect.telegram_sent_count_matching: {regex, count}`
conta as mensagens enviadas ao usuário em todo o cenário.
Voz: `./scripts/evi-sim run --tag voice --repeat 3 --llm fill` (sim.env liga `EVI_VOICE_ENABLED`).
Passos de voz: `telegram_voice: {file, duration_s?}`, `whatsapp_control_voice: {file, duration_s?}` e
`whatsapp_contact_voice: {file, duration_s?, jid?, push_name?}`, onde `file` é um nome em
`tests/fixtures/audio/` (OGG/Opus sintético, fictício; geração e conteúdo no `README.md` da
pasta, via eSpeak NG num container descartável, sem TTS no host). O runner envia os bytes ao fake
(`POST /_sim/telegram/voice` → `getFile` + `GET /file/bot<token>/<path>`; `POST /_sim/evolution/media`
→ `getBase64FromMediaMessage`) e dispara o update/webhook. `expect.media_requests: N` confere
quantas vezes o fake Evolution foi chamado para baixar mídia (`0` prova que o áudio de terceiro
não foi baixado). `no_reply` vale em `telegram_voice`/`whatsapp_control_voice`.
O workspace do sim é semeado a cada reset com os arquivos versionados de `EVI_WORKSPACE/`
(AGENTS/TOOLS/HEARTBEAT/skills) + o `USER.md` fictício de `tests/sim/workspace/`.

Saúde do WhatsApp no sim: o Evolution falso responde `GET /instance/connectionState/<instância>` com o estado semeado (`seed: {evolution: {state: close}}`; padrão `open`) e `POST /_sim/evolution/state` o muda no meio do cenário. O step `job: probe` roda a sonda diária (`?wait=true`); `SIM-REL-05` (tag `reliability`) garante um único aviso de WhatsApp desconectado e o selo "WhatsApp desconectado desde" no topo do briefing.

Resumo do WhatsApp (SIM-WA-04, tag `whatsapp`): o Evolution falso aceita `seed: {evolution: {delay_ms: 5000}}` (espera artificial em cada `findMessages`/`findChats`, sem travar os outros fakes) e conta as requisições por endpoint (`/_sim/state` → `evolution_requests`). `expect.evolution_requests: {chat/findMessages: 0}` compara a contagem **durante o passo**; o cenário prova que o resumo do dia sai das timelines locais (três contatos + resposta do usuário via webhook) sem nenhuma chamada lenta à Evolution. A latência individual da tool não é exposta pelo harness; o contador zero mais `reply_within_s` cobrem o turno. O reaproveitamento do resumo em cache (2ª pergunta) não é observável no sim (só se confere que a 2ª resposta continua correta e sem `findMessages`).

### Formato do cenário

Em `tests/sim/scenarios/<source>/*.yaml` (`real-usage`, `failure`, `adversarial`,
`smoke`, `whatsapp`). Validado por `agent/testing/sim/schema.py`; chave
desconhecida é erro. Exemplo: `tests/sim/scenarios/real-usage/SIM-RU-01*.yaml`.

- Topo: `id` (único), `title`, `tags` (`critical`, `calendar`...), `source`
  (`real-usage|failure|adversarial|synthetic`), `clock` (`D0 09:00`), `seed`
  (`calendar`, `tasks`, `gmail`, `calendars`, `evolution`; datas relativas `D1 10:00`,
  `D-1`), `steps`.
- Cada step tem exatamente um tipo: `telegram: "texto"`, `whatsapp_control: "texto"`,
  `whatsapp_contact: "texto"` ou `{text, jid, from_me, group, push_name}`,
  `clock: "D1 08:00"` ou `"+2h"`, `job: heartbeat|daily-summary`,
  `fault: {windmill|telegram: ...}`; mais `expect:` opcional.
- `expect`: `reply_within_s`, `max_latency_s`, `reply_matches` (regex; único check de
  texto), `no_reply` (+ `no_reply_window_s`, default 15), `calendar`
  (`created: [{summary_contains, start, end}]`, `count`), `tasks`
  (`created: [{title_contains, due}]`, `count`), `gmail` (`deleted_count`,
  `deleted_ids_include`, `not_deleted`), `tools_called_any`, `tools_not_called`,
  `outbound_to_third_parties`, `postgres` (`[{table, where, count}]`; tabelas:
  `pending_commitments`, `whatsapp_contacts`, `messages`, `session_tool_snapshots`).
  Cenários afirmam estado e efeitos, não redação.

### Critério de aprovação

`critical` e `adversarial`: N/N repetições. Demais: ≥ 2/3. Relatórios em
`logs/sim/`.

### Custo de LLM nos testes

| Modo | LLM real | Quando usar |
|---|---|---|
| `replay` | nunca (sem chave) | CI; conferir que nada mudou |
| `fill` | **só** nas requisições que não estão no cassete (prompt, tool ou conversa mudou; cenário novo) | Verify de task e gate de change (`--repeat 3`: só o que mudou roda 3× ao vivo); a tentativa aprovada regrava o cassete |
| `record` | todas | regravar um cassete inteiro de propósito |
| `live` | todas, sem gravar | checagem de deriva do modelo (ex.: mensal ou ao trocar a versão do Gemini/OpenRouter) |

O relatório mostra `real N · served M` e os tokens reais; `--max-llm-calls` conta só as reais.
Se um change não mexe em prompt, docstring/schema de tool nem no que entra na conversa, o
`fill` dele custa **0 chamadas**.

`llm-eval` guarda as respostas em `data/eval/cache.jsonl` por (tarefa, provedor, modelos,
prompt, schema): rodar de novo sem mudar nada custa 0. Use `--no-cache` (ou
`EVI_LLM_EVAL_CACHE=0`) ao trocar de modelo ou para checar deriva.

### Cassetes (replay)

Respostas do LLM gravadas em `tests/sim/cassettes/` alimentam o modo `replay` (CI,
sem chave). **Regravar após qualquer mudança de prompt, docstring de tool ou schema
de tool:** `./scripts/evi-sim run --tag critical --llm fill` (só as chamadas que mudaram vão ao
LLM real) e commitar os cassetes alterados. `--llm record` regrava o cassete inteiro.

### Isolamento

Projeto compose `evi-sim` (portas 18000/18080), sem `.env` de produção, sem mount
de `./data` nem `./logs`, e `guard` valida o compose renderizado (projeto, env_file, binds de
`data`/`logs`, hosts reais como api.telegram.org/googleapis.com) e aborta `up`/`run`
se algo vazar. Chave do LLM: `EVI_SIM_GEMINI_API_KEY`; se ausente, cai em
`GEMINI_API_KEY` de produção com aviso — a **cota é compartilhada**. `replay` nunca
usa chave.

### Novo cenário a partir de falha real

1. Copie o `id`/pedido real (Telegram/WhatsApp) para um YAML em
   `tests/sim/scenarios/real-usage/` (ou `failure/`), tags `real-usage` (+ `critical`
   se for regressão que não pode voltar).
2. Reproduza o estado com `seed` e `clock`; asserte o efeito esperado em `expect`.
3. `./scripts/evi-sim run --id <ID> --repeat 3 --llm fill` deve falhar antes do fix
   e passar depois; grave o cassete (`--llm record`) e commite.

Tiers legados (ainda válidos):

1. **Unit** — `pytest tests/unit -q` (no Docker/Ollama)
2. **Integration CLI** — `./scripts/evi-test <feature> [--verbose]`
3. **Smoke E2E** — `./scripts/evi-test smoke --full` (needs agent-api + Ollama)

## Commands

| Feature | Command | SCN |
|---------|---------|-----|
| All offline smoke | `./scripts/evi-test smoke` | SCN-E2E-02 |
| Full stack | `./scripts/evi-test smoke --full` | SCN-E2E-05 |
| Session isolation | `./scripts/evi-test sessions` | SCN-RT-03, SCN-TEST-11 |
| Container smoke (sistema montado) | `./scripts/evi-test container` | SCN-CI-02, SCN-CI-03 |
| Bounded memory (single buffer) | `./scripts/evi-test memory` | — |
| Session round-trip (Postgres) | `DATABASE_URL=... ./scripts/evi-test session` | — |
| WhatsApp pipeline | `./scripts/evi-test whatsapp --verbose` | SCN-WA-04 |
| Commitments queue | `DATABASE_URL=... ./scripts/evi-test commitments` | SCN-WA-10, SCN-CHAT-02 |
| File organizer | `./scripts/evi-test file-organizer` | SCN-FO-01 |
| Calendar (mock) | `./scripts/evi-test calendar` | SCN-CAL-02 |
| Calendar (live Windmill) | `./scripts/evi-test calendar --live-windmill` | SCN-CAL-04 |
| Tasks (mock) | `./scripts/evi-test tasks` | SCN-TASK-03 |
| Tasks (live Windmill) | `./scripts/evi-test tasks --live-windmill` | SCN-TASK-05 |
| Email (mock) | `./scripts/evi-test email` | SCN-EMAIL-04 |
| Email (live Windmill) | `./scripts/evi-test email --live-windmill` | SCN-EMAIL-05 |
| Evolution parse | `./scripts/evi-test evolution` | SCN-WA-05 |
| Telegram (polling setup) | `./scripts/evi-telegram-polling-setup.sh` | SCN-TG-03 |
| Telegram (live E2E) | `./scripts/evi-telegram-verify.sh` | SCN-TG-02, SCN-WA-12 |
| Telegram (mock) | `./scripts/evi-test telegram` | SCN-TG-01 |
| Telegram LLM audit/persist | `tests/unit/test_telegram_handler.py` | SCN-TG-02 |
| Telegram (live webhook) | `./scripts/evi-test telegram --live-telegram` | SCN-TG-02 |
| Telegram (polling) | `TELEGRAM_MODE=polling` + poller startup | SCN-TG-04 |
| Telegram (direct list) | `tests/unit/test_telegram_list.py` | SCN-TG-05 |
| Calendar list events (unit) | `tests/unit/test_telegram_list.py` | SCN-CAL-06 |
| Calendar list events (mock) | `./scripts/evi-test calendar-list` | SCN-CAL-06 |
| Calendar list events (live) | `./scripts/evi-test calendar-list --live-windmill` | SCN-CAL-06 live |
| Evolution log fields | `./scripts/evi-test evolution` | SCN-WA-13..15 |
| JSONL log retention | `agent/services/log_retention.py` | SCN-OPS-02 |
| Deep health (unit) | `tests/unit/test_health.py` | SCN-API-02 |
| Deep health (offline) | `./scripts/evi-test health` | SCN-API-02 |
| Deep health (live) | `./scripts/evi-test health --full` | SCN-API-02 live |
| Prometheus metrics | `./scripts/evi-test metrics` | SCN-OPS-03 |
| GitHub Actions CI | `.github/workflows/ci.yml` | SCN-CI-01 |
| RAG (offline) | `./scripts/evi-test rag` | SCN-RAG-01..03 wiring |
| RAG (live Qdrant) | `./scripts/evi-test rag --live-qdrant` | SCN-RAG-04 |
| LLM factory | `tests/unit/test_llm_factory.py` | EVI_LLM_PROVIDER, EVI_EMBED_PROVIDER |
| Integration factory | `tests/unit/test_integration_factory.py` | EVI_ORCHESTRATOR, EVI_WHATSAPP_PROVIDER |
| Notes | `./scripts/evi-test notes` | SCN-NOTE-02 |
| Session/Postgres | `DATABASE_URL=... ./scripts/evi-test session` | SCN-E2E-03 |
| Contact FS memory | `./scripts/evi-test contact-memory` | SCN-MEM-02 |
| Daily summary | `./scripts/evi-test daily-summary` | SCN-MEM-02b |
| Knowledge graph | `./scripts/evi-test graph` | SCN-MEM-03 |
| Memory live (stack) | `./scripts/evi-test memory-live` | SCN-MEM-02/03 live |

### Runtime v3 / Inbox UX (Jun 2026)

| Feature | Command | SCN |
|---------|---------|-----|
| Runtime v3 offline | `./scripts/evi-test runtime-v3` | SCN-UX-RUNTIME |
| Briefing offline (sem LLM) | `./scripts/evi-test briefing` | SCN-BRIEF-01/01b/02 |
| Corpus de prompt injection (offline, sem LLM) | `./scripts/evi-test injection` | SCN-SEC-01, SCN-INJ-01/02/03 |
| Inbox UX mock | `./scripts/evi-test inbox-ux` | SCN-UX-INBOX-01/02/04 |
| Inbox UX live harness | `./scripts/evi-inbox-ux-verify.sh` | SCN-UX-INBOX live |
| Chat invoke (unit) | `tests/unit/test_chat_invoke.py` | SCN-UX-CHAT |
| LLM-first control (unit) | `tests/unit/test_whatsapp_control.py`, `test_telegram_handler.py` | SCN-UX-WA-CTRL-01 |
| Evolution require_ts | `./scripts/evi-test evolution` | SCN-UX-WA-ING-01 |
| Email messages fixture | `tests/fixtures/windmill/email_summary_messages.json` | SCN-EMAIL-04 |


| SCN | Test file |
|-----|-----------|
| SCN-CHAT-03 | `tests/unit/test_commitment_tools.py` — confirm event → `schedule_event` |
| SCN-CHAT-04 | `tests/unit/test_commitment_tools.py` — confirm task → `create_task` |
| SCN-EMAIL-03 | `tests/unit/test_email_tool.py` — `summarize_inbox` wiring |
| SCN-WA-09 | `tests/unit/test_evolution_filter.py` |
| SCN inbox priority | `tests/unit/test_commitment_priority.py` |
| SCN-WA-16 LLM fallback | `tests/unit/test_whatsapp_llm_extract.py` |
| SCN-UX-CHAT | `tests/unit/test_chat_invoke.py` — context + tool snapshots |
| SCN-UX-WA-CTRL | `tests/unit/test_whatsapp_control.py` — LLM-first when `EVI_DIRECT_HANDLERS=false` |

```bash
pytest tests/unit/test_commitment_tools.py -q
```

## WhatsApp logs

```bash
./scripts/evi-test whatsapp --verbose
jq -s '.' logs/whatsapp_*.jsonl | less
```

Golden file: `tests/golden/whatsapp_commitments.json`

Windmill offline fixtures: `tests/fixtures/windmill/` (replaces legacy `n8n/` prefix per SCN-DEP-02).

## OpenSpec verify

```bash
pytest tests/unit -q && ./scripts/evi-test smoke
openspec validate --specs
```

Scenario IDs are defined in `openspec/specs/*/spec.md`.

## E2E checklist (SCN-E2E)

| Step | Command | Pass criteria |
|------|---------|---------------|
| SCN-E2E-01 | `docker compose up -d --build` | postgres → qdrant/windmill healthy → agent-api (SCN-OPS-01) |
| SCN-OPS-01 | `docker compose ps` | postgres, qdrant, windmill-server, agent-api show `healthy` |
| SCN-E2E-02 | `./scripts/evi-test smoke` | 13/13 offline |
| SCN-E2E-03 | `export DATABASE_URL=postgresql://evi:PASS@localhost:5433/evidb` | session + commitments connect (host port 5433) |
| SCN-E2E-04 | Ollama running on host (not in compose) | `curl host.docker.internal:11434` from agent; chat retries until model loads |
| SCN-E2E-05 | `./scripts/evi-test smoke --full` | chat PASS or documented skip |
| SCN-E2E-06 | `./scripts/evi-test evolution` | parse fixture PASS |
| SCN-CHAT-02 | `DATABASE_URL=... ./scripts/evi-test commitments` | list tool returns seeded row |

### Last run

- **2026-06-05** — `evi-commitment-close-loop`: run `pytest tests/unit -q && ./scripts/evi-test smoke` after apply
- Full stack: requires Ollama + compose (see SCN-E2E-04/05)
