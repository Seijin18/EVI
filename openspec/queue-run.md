# Execução da fila — iniciada 2026-10-18 (3ª rodada)
## Estado
- Change atual: evi-discovery-tips (fase: implementar) — task 1.1
- Ordem: evi-source-health-alerts → evi-briefing-buttons → evi-whatsapp-summary-cache → evi-discovery-tips → evi-awaiting-their-reply → evi-scheduled-tasks
- Concluídos: evi-source-health-alerts (arquivado 2026-10-18, commits 891b894..5f83f9b + archive), evi-briefing-buttons (arquivado 2026-10-18, commits 6b878d7..7609d13 + archive), evi-whatsapp-summary-cache (arquivado 2026-10-18, commits 87c39be..a8d943c + archive)
- Pulados: —
## Decisões do usuário no preflight (2026-10-18)
- Mudanças novas no Telegram entram **ligadas por padrão**, cada uma com flag no `.env` para desligar.
- Prévia da noite: schedule às 21h **ligado**.
- Tarefas agendadas: **só leitura** (nunca apaga, cria ou envia), com teto de execuções/dia.
## Decisões tomadas sem o usuário
- 2026-10-18 briefing-buttons: ✅ numa promessa marca como feita (a tool de confirmar não aceita promessa); 👍/👎 fica no teclado com ✓; `callback_data` ganhou o tipo do briefing e a guarda de `message_id` falha fechada (revisão).
- 2026-10-18 whatsapp-summary-cache: em vez de pré-computar no lote noturno, ler a timeline local (já tem os dois lados desde 13/10) e ir à Evolution só para grupos/lacunas, em paralelo.
- 2026-10-18 source-health-alerts: WhatsApp entra na sonda só quando `EVOLUTION_API_KEY` está definido; a sonda não pode importar `messaging` (teste de somente-leitura), então lê o estado via `services.health`. Sonda + watchdog podem avisar a mesma queda (até 2 mensagens).
## Pendências do usuário (não bloqueantes)
- [ ] WhatsApp desconectado desde 14/10 — gerar o QR e escanear (a geração foi bloqueada pelo classificador de permissões)
- [ ] Google OAuth expirou em 18/10 (modo "Teste", 7 dias) — reconectar `gcal`/`gtasks`/`gmail` no Windmill e, de vez, publicar o app OAuth em Produção no Google Cloud
## Bloqueios

---

# Execução anterior — iniciada 2026-10-12 (2ª rodada)
## Estado
- Change atual: — (fila concluída em 2026-10-13)
- Ordem: evi-promise-context → evi-security-review → evi-contact-knowledge → evi-contact-names → evi-ux-review
- Concluídos: evi-promise-context (arquivado 2026-10-13, commits 8d6472f..8c5b4c8 + archive), evi-security-review (arquivado 2026-10-13, commits e58da95..4ab5471 + archive), evi-contact-knowledge (arquivado 2026-10-13, commits 5b2ef99..4de7e01 + archive), evi-contact-names (arquivado 2026-10-13, commits c762ca4..e300e74 + archive), evi-ux-review (arquivado 2026-10-13, commits dda7d7f..5d9b688 + archive)
- Pulados: evi-background-execution (#38) — condicional (inalterado)
## Decisões do usuário no preflight (2026-10-12)
- Windmill só em `127.0.0.1:8001` (acesso remoto por túnel SSH / `tailscale serve`).
- Operações ao vivo (rotação de senhas padrão, chave do Qdrant, webhook global da Evolution) **executadas durante a fila**; se a Evolution pedir QR, parar e chamar o usuário.
- Ferramentas autorizadas: `pip-audit` (pinado) e `trivy` (imagem Docker oficial, versão fixa).
- Revisões com o usuário (threat model, achados, `promise-reeval --apply`, avaliação de briefings) são assíncronas: dry-run/rascunho na fila, revisão em "Pendências".
## Decisões tomadas sem o usuário
- 2026-10-12 base: `test_daily_summary` falhava entre 21h e 24h (timeline em UTC × dia local) → `8d6472f`. Gates rodam com `.venv/bin` no PATH (o `python3` do sistema não tem pytest/psycopg2).
- 2026-10-12 promise-context 2.1: revisão (Opus) achou o teto de gasto "fail-open" (leitura do banco falhando zerava o contador) → agora fecha (sem chamada); custo NaN/negativo tratado como 0.
- 2026-10-12 promise-context 3.2: fila de avaliação vive em colunas de `pending_commitments` (`next_eval_at`, `eval_attempts`, `msg_ts`), não em tabela `background_jobs` (não existe); design sincronizado. Fallback de 48 h descarta prazo já vencido (senão a linha ficaria oculta pela listagem); rejeição do LLM marca `confirmed_via='auto-eval'` e sai das métricas de ação; desligar a flag libera as linhas `needs_eval` para `pending`. Lote do loop = 3 avaliações por minuto (não atrasar lembretes).
- 2026-10-12 promise-context 2.0: avaliador sintético com o modelo padrão = 93% (FP=1: caso de injeção S25 virou "Transferir R$ 5000" — só cria pendência, sem ação; reavaliar no #37/security). Casos reais só em `data/eval/promise_real.json` (gitignored, 0600).
- 2026-10-13 security-review: Windmill só em `127.0.0.1:8001`; webhook global da Evolution desligado; segredos rotacionados com `evi-rotate-secrets --apply` (backups em `data/backups/*pre-rotate*`, 0600); `EVI_REQUIRE_API_KEY` passa a ser obrigatório por padrão (typo/vazio mantém ligado); `/metrics` exige chave; grupo de controle do WhatsApp só aceita `from_me`. Arquivado com F5/F6 (altos) abertos por dependerem de sudo/plano Gemini do usuário — registrados como pendência em vez de bloquear a fila.
## Execução das pendências (2026-10-16/17, a pedido do usuário)
- [x] `contact-knowledge-migrate --apply`: 1 síntese movida para `history.md` (cópia `profile.md.pre-migrate`); dry-run seguinte = 0
- [x] Primeira execução do lote de conhecimento: 12 contatos atualizados, 3 sem mudança, 0 erros; auditoria automática (8 fatos sem data=0, fora da timeline=0, parecendo metadado=0; 4 itens "em aberto" com data fora da timeline pelo prefixo UTC — provável diferença de fuso). 5 perfis para você ler em `data/eval/audit_profiles.md` (local, não versionado)
- [x] `wmill sync push` restrito (`--includes` só dos 3 scripts novos + schedules novos): criados `list_contacts`, `contact_names_sync`, schedules `contact_learn_daily` (03:30, ativo) e `contact_names_sync_daily` (03:15, DESLIGADO até o OAuth); schedules existentes não foram tocados
- [x] `contact-identity-migrate`: 56 aliases @lid↔telefone já registrados; 0 pastas @lid para mesclar (nada a fazer)
- [x] Promessas: as 16 pendentes já estavam `dismissed` — `promise-reeval --apply` não tem mais o que aplicar
- [ ] **WhatsApp desconectado** (`state: close`, sem eventos desde 14/10 11:21): precisa gerar o QR e escanear. A geração do QR foi bloqueada pelo classificador de permissões — executar manualmente (ver resposta)
- [ ] `scripts/evi-host-hardening` (Ollama/SSH/ufw, precisa de sudo): rodar `./scripts/evi-host-hardening` (status) e depois `ollama`, `ssh` (só após instalar chave), `ufw`
- [ ] WhatBot: aplicar `docs/security/whatbot-compose-loopback.patch` (editar o outro projeto foi bloqueado): `cd ~/Projects/WhatBot && git apply ~/Projects/EVI/docs/security/whatbot-compose-loopback.patch && docker compose up -d`
## Pendências do usuário (não bloqueantes)
- [ ] Revisar a reavaliação das promessas atuais e aplicar: abrir `data/eval/promise_reeval_dryrun.txt` (9 a descartar, 7 a atualizar) e, se estiver de acordo, `./scripts/evi-test promise-reeval --apply` — muda dados reais (não feito pela fila)
- [ ] Avaliar em 2026-10-20 a validação das promessas com contexto: taxa de ação ≥ 30%, ≤ 1 promessa/dia sem objeto no briefing — relatório semanal (tipo `promise`)
- [ ] Definir teto mensal de gasto na conta OpenRouter (a trava no código é US$ 0,10/dia) — openrouter.ai → Settings → Limits
- [ ] **Segurança F5 (alto, sudo)**: Ollama responde na LAN/tailnet sem auth — comandos exatos em `docs/security/findings.md` § Ações do usuário (1) — `sudo systemctl edit ollama` → `OLLAMA_HOST=172.17.0.1:11434`
- [ ] **Segurança F6 (alto provisório)**: verificar o plano da chave do Gemini (gratuito pode treinar com seus dados) — https://aistudio.google.com/apikey
- [ ] Segurança F9–F12, F26 (SSH por senha/ufw, portas do WhatBot, escopos OAuth e login do Windmill, Tailscale serve antigo) — `docs/security/findings.md` § Ações do usuário
- [ ] Confirmar de outra máquina da rede que `curl -m3 http://192.168.15.32:8002/health` e `:8001/` falham (000)
- [ ] Verificar em 24 h que `docker logs evi-agent-api-1` não tem `/webhooks/evolution ... 401` e que mensagens do WhatsApp continuam chegando (webhook global desligado)
- [ ] Apagar os backups de rotação quando não precisar mais deles: `data/backups/env-pre-rotate-*` e `pre-rotate-*.sql` (guardam segredos/dados antigos)
- [ ] Limite de crédito mensal na chave do OpenRouter — https://openrouter.ai/settings/keys
- [ ] Publicar o schedule diário das 03:30 do conhecimento de contatos: `cd windmill && wmill sync push` (cria `f/integrations/contact_learn_daily`; confirmar `enabled` na UI) — evi-contact-knowledge 3.2
- [ ] Contact-knowledge: aplicar as migrações de dados reais — `./scripts/evi-test contact-knowledge-migrate` (dry-run: 44 perfis, 1 síntese a mover) e depois `--apply`; `./scripts/evi-test contact-identity-migrate` (dry-run hoje: 0 pastas @lid com alias conhecido; os aliases se acumulam com o tráfego — repetir em alguns dias)
- [ ] Contact-knowledge: primeira execução do lote com você (`curl -X POST -H "X-Api-Key: $EVI_API_KEY" "localhost:8002/jobs/contact-learn?wait=true"`; envia até 60 mensagens × 15 contatos para o OpenRouter ZDR, aprovado em 2026-10-12) e auditoria de 5 perfis (nenhum fato sem evidência, nenhum fato de metadado)
- [ ] Avaliar em 2026-10-20 a validação do conhecimento de contato: ≥ 80% dos contatos ativos com Fatos/Em aberto atualizados na semana; auditoria de 10 perfis; títulos de promessa com objeto+pessoa ≥ 70%
- [ ] Teste instável observado uma vez (suíte completa 1 falha, 3 reexecuções verdes) após os últimos commits — identificar na próxima falha com `pytest tests/unit -q -x`
- [ ] Contact-names (ativar a sincronização da agenda): (1) Google Cloud → habilitar a People API e o escopo `contacts.readonly` na tela de consentimento; (2) Windmill (via túnel, `docs/remote-access.md`) → criar o resource OAuth `gcontacts` (mesmo Client ID/Secret do `gcal`); (3) `WINDMILL_GCONTACTS_RESOURCE` no `.env`; (4) `cd windmill && wmill sync push`; (5) `./scripts/evi-test contact-names-sync` (dry-run, revisar contagens) e `--apply`; (6) ligar o schedule `contact_names_sync_daily` (03:15) na UI — passos em `windmill/README.md` § Google Contacts
- [ ] Avaliar em 2026-10-20 a validação dos nomes de contato: ≥ 90% das conversas diretas ativas (30 dias) com nome de agenda ou do usuário; 0 nomes do usuário sobrescritos
- [ ] Nota de produto (BACKLOG): combinados antigos (`pending_commitments.source_label`) continuam mostrando o número depois da sincronização
- [ ] UX: revisar `docs/ux/review-2026-10.md` (seção "Revisão pendente do usuário") — aprovar/ajustar P1/P2/P3; o que sobrou está em `openspec/BACKLOG.md` § Revisão de UX
- [ ] Avaliar em 2026-10-20 a validação do ux-review: 0 mensagens ao Telegram com `«externo`; taxa de ação sobre itens do briefing não cai; 3 briefings avaliados como "dá para ler em 10 s"
- [ ] Cassettes ausentes (pré-existente): REM-02..05 e VOICE-02/03/05 não têm cassete (replay desses tags falha "no cassette"; CI só roda `critical`); SIM-BRIEF-03 (e-mail adversarial) ficou só live por instabilidade de cassete — gravar se quiser replay completo
## Bloqueios
- (resolvido 2026-10-13 — usuário ajustou o teto do Gemini; SIM-DEBT-06 regravado, critical live 27/27) evi-contact-knowledge 4.1: o Gemini devolve `429 RESOURCE_EXHAUSTED: Your project has exceeded its monthly spending cap`. Impacto: (a) o chat de produção também usa essa chave — os logs do agent-api mostram 16 ocorrências de 429 nas últimas 12 h; (b) não dá para regravar o cassette de SIM-DEBT-06 (replay do tag `reply-debts` fica vermelho nesse cenário) nem rodar `critical --repeat 3 --llm live`. Tentado: 2 gravações (429 nas duas); espera não resolve (teto mensal). Precisa do usuário: aumentar/zerar o teto do projeto Gemini (https://aistudio.google.com/ → Spend / Billing). Depois: `./scripts/evi-sim run --id SIM-DEBT-06 --llm record`, `--id SIM-DEBT-06 --repeat 3 --llm live`, `./scripts/evi-sim run --tag reply-debts --llm replay`, `./scripts/evi-sim run --tag critical --repeat 3 --llm live`, e então a task 4.2. A fila retoma de 4.2 (migração `--apply` com você, primeira execução do lote, auditoria de 5 perfis).

---

# Execução anterior — iniciada 2026-10-10
## Estado
- Change atual: — (fila concluída em 2026-10-11)
- Ordem: evi-sim-harness → evi-usage-validation → evi-morning-briefing → evi-reminders → evi-reply-debts → evi-voice-input → evi-perceived-reliability → evi-prompt-injection-model
- Concluídos: evi-sim-harness (arquivado 2026-10-10, commits 346030b..a5a8da5), evi-usage-validation (arquivado 2026-10-10, commits cb43674..3f2634e), evi-morning-briefing (arquivado 2026-10-10, commits f206ab3..681c870), evi-reminders (arquivado 2026-10-10, commits 23382d8..d788182), evi-reply-debts (arquivado 2026-10-10, commits 1030862..5468808), evi-voice-input (arquivado 2026-10-10, commits 410386c..6acd0c2), evi-perceived-reliability (arquivado 2026-10-10, commits 86ef936..c820f90), evi-prompt-injection-model (arquivado 2026-10-11, commits 7d231f4..a4c0bb8)
- Pulados: evi-background-execution (#38) — condicional: "abrir só se o ack imediato do #44 não bastar na prática"; exige dados de uso real
## Decisões tomadas sem o usuário
- 2026-10-11 deploy: flags ligadas para teste (briefing, lembretes, pendências, voz, ack 5 s) e `EVI_GEMINI_THINKING_BUDGET=0` em produção (reversível no `.env`). Achados no deploy: `/health` levava ~55 s (contagem de contatos consultava o Evolution) e os jobs agendados travavam o worker único do Windmill (corrigido: execução em segundo plano).
- 2026-10-10 fila: agentes de projeto (`.claude/agents/`) não estão registrados nesta sessão; usados via `general-purpose` com `model` equivalente (haiku/sonnet/opus) e instrução de seguir o arquivo do agente.
- 2026-10-10 evi-sim-harness: (decisão do usuário no preflight) sem chave Gemini separada; `evi-sim` usa `EVI_SIM_GEMINI_API_KEY` se definida, senão repassa `GEMINI_API_KEY` do `.env` com aviso. Cota de produção compartilhada → `--max-llm-calls` mantido.
- 2026-10-10 evi-sim-harness 2.2: achados do fake Windmill — (a) `delete_emails.py` engole o corpo do erro do Google ("HTTP 401") e OAuth expirado vira `upstream_error`; (b) HTTP 500 do Windmill chega ao `parse_windmill_result` como `unparseable`. Corrigir na 3.4 (cenários de falha) se o cenário exigir.
- 2026-10-10 evi-sim-harness 3.3: fake Windmill passava `action` (sempre enviado pelo cliente) ao `main()` do script → TypeError; corrigido no fake (Windmill real descarta chaves não declaradas).
- 2026-10-10 evi-sim-harness 3.3: SIM-RU-09 reescrito ("reunião de condomínio" → "reunião com o síndico") porque o extrator heurístico descarta título genérico "Reunião" e o fallback Ollama está desligado na sim. Comportamento do extrator fica para `evi-reply-debts` (#42), que repensa a extração.
- 2026-10-10 evi-sim-harness 3.3: SIM-RU-08 1/3 — modelo pedia número completo em vez de chamar `set_whatsapp_contact_name` com final; docstring da tool ajustada (aceita últimos dígitos, chamar direto).
- 2026-10-10 evi-sim-harness: SIM-RU-05 travou 1/3 live (uma chamada ao Gemini sem retorno em 90 s) → `EVI_LLM_TIMEOUT_SEC` (default 60) no cliente Gemini. Muda produção: turno que antes travava agora tem retry após 60 s.
- 2026-10-10 evi-usage-validation (sync): nome e telefone reais em SCN-USE-04/07 trocados por fictícios; Verify de 1.1 com PG efêmero em container descartável (`evi-unit-pg`); cenários SIM-USE-01/02 adicionados às tasks 1.2 e 2.1.
- 2026-10-10 evi-usage-validation 1.1: `log_retention` só trata arquivos; a retenção de 180 dias do `turn_log` vai para o job noturno da 2.2 (DELETE por `ts`).
- 2026-10-10 evi-morning-briefing (sync): Verify da 2.7 não roda o script no Windmill real (conta real) — vira pendência; DB tests com `EVI_TEST_EPHEMERAL_DB`; 1.2 regrava cassettes e roda adversariais live.
- 2026-10-10 evi-morning-briefing 2.2–2.4: um commit só (mesmo módulo `briefing.py`); `list_events.py` ganhou `id/start_iso/end_iso` (aditivo) para conflitos e refs de evento.
- 2026-10-10 evi-morning-briefing: a sim rodava sem os arquivos de bootstrap do `EVI_WORKSPACE` (prompt diferente da produção); o runner passa a semear os arquivos versionados + um `USER.md` fictício. Cassettes regravados.
- 2026-10-10 evi-morning-briefing (revisão): requisito "todo conteúdo de terceiros em qualquer prompt via wrap_external" estreitado aos caminhos cobertos (briefing, resumo WhatsApp, perfil, extração); saídas das tools `summarize_inbox`/`list_calendar_events` ficam para o #37 (`evi-prompt-injection-model`).
- 2026-10-10 evi-reminders (proposta escrita pela fila): presets de recorrência (sem RRULE livre); flag `EVI_REMINDERS_ENABLED` default `false`; tools `snooze`/`complete` além das 3 do roadmap (necessárias para "adia/feito"); limiar "atrasado" = 5 min; `python-dateutil` como dependência nova pinada.
- 2026-10-10 evi-reminders (revisão): "feito" num lembrete recorrente confirma só a ocorrência (só `cancel` para a série); "adia" num recorrente adia só aquela ocorrência (`snooze_until`), sem mover a série; `create_reminder` só por pedido explícito do usuário, nunca de conteúdo externo; turnos de teste não criam lembretes.
- 2026-10-10 custo (pedido do usuário): otimizações antes de retomar — `EVI_GEMINI_THINKING_BUDGET` (0 só na simulação; produção inalterada até validar), tokens/custo por chamada no relatório da sim e no `turn_log`, prompt com a parte estática primeiro (cache implícito do Gemini). Processo da fila: 3 repetições só em `critical`/`adversarial`, regressão com 1, cassettes gravados uma vez no fim de cada change, teto ~150 chamadas por change. Orçamento: +R$ 10.
- 2026-10-10 evi-reply-debts: tools de pendência funcionam com a flag desligada (só leitura/reconhecimento); timeout do LLM 30 s × 2 tentativas (antes 60 s × até 6).
- 2026-10-10 achado de segurança (evi-voice-input 2.1): mensagens de texto do Telegram de QUALQUER chat chegam ao agente (só a voz verifica `TELEGRAM_CHAT_ID`). Correção incluída como task 1.0 do `evi-prompt-injection-model`.
- 2026-10-11 evi-prompt-injection-model: prévia de exclusão mostra os assuntos delimitados («externo:email») também para o usuário — preferido a exibir texto cru que voltaria ao modelo no turno seguinte.
## Pendências do usuário (não bloqueantes)
- [ ] Criar projeto Gemini separado e definir `EVI_SIM_GEMINI_API_KEY` no `.env` — a simulação hoje consome a cota de produção — `.env`
- [x] `EVI_WORKSPACE/agenda.vcf` (não versionado, não ignorado) contém contatos reais — mover para fora do repo ou adicionar ao `.gitignore`; nunca foi staged pela fila — `EVI_WORKSPACE/agenda.vcf` — feito em 2026-10-11
- [x] Revisar o dry-run e apagar dados de teste em produção (4 compromissos "Teste digest Telegram" ids 21/36/40/41; 8 linhas de `messages` de sessões de teste) — destrutivo, decisão sua — `scripts/evi-cleanup-test-data` e depois `scripts/evi-cleanup-test-data --apply` — feito em 2026-10-11
- [x] Criar schedules no Windmill: `f/integrations/usage_signals` diário (ex. 03:00), `f/integrations/usage_report` segunda 00:30, `f/integrations/probe` diário 06:30 — Windmill UI → Schedules — feito em 2026-10-11
- [x] Recriar o `agent-api` para ativar V1/V2 em produção (novas tabelas, endpoints, mount `./data/payload_shapes`) — `docker compose up -d --build agent-api` — feito em 2026-10-11
- [ ] Avaliar em 2026-10-24 a "Validação em uso real" do evi-usage-validation: relatório entregue em 2 semanas seguidas; sonda detecta falha induzida em ≤ 24 h; ≥ 1 cenário promovido para `tests/sim/scenarios/from-usage/` — `EVI_WORKSPACE/reports/`
- [x] Publicar no Windmill os scripts alterados/novos (`summarize_inbox`, `list_events` ganharam campos aditivos; `usage_report`, `usage_signals`, `probe`, `briefing` novos) — `wmill sync push` na pasta `windmill/` — feito em 2026-10-11
- [x] Ligar o briefing: `EVI_BRIEFING_ENABLED=true` no `.env`, recriar `agent-api`, schedule `f/integrations/briefing` `0 7 * * *` (opcional `0 21 * * *` com `kind=evening`) — ver `windmill/README.md` — feito em 2026-10-11
- [ ] Avaliar em 2026-10-24 a validação do briefing (entregue ≥ 13/14 dias, resposta ≥ 50% dos dias, sucesso por turno sem queda) — relatório semanal
- [x] Teste instável observado (ordem): `tests/unit/test_payload_shapes.py::test_scn_use_08_written_file_has_no_original_values[find_messages.json]` falhou uma vez na suíte completa e passa isolado — investigar — feito em 2026-10-11
- [x] Ligar lembretes: `EVI_REMINDERS_ENABLED=true` no `.env` e recriar `agent-api` — feito em 2026-10-11
- [x] (2026-10-18: 0 criados — registrado no BACKLOG) Avaliar em 2026-10-17 a validação dos lembretes (desvio < 60 s em ≥ 95%, nenhum vencido sem envio, ≥ 3 lembretes criados) — relatório semanal
- [x] Decidir se a produção usa `EVI_GEMINI_THINKING_BUDGET=0` (a simulação inteira passou com 0; custo cai ~50%) — `.env` — feito em 2026-10-11
- [x] Ligar pendências de resposta: `EVI_REPLY_DEBTS_ENABLED=true` (para de mandar notificação avulsa de compromisso; o briefing passa a ter 3 grupos) — feito em 2026-10-11
- [ ] Avaliar em 2026-10-24 a validação do evi-reply-debts (ação ≥ 30% em "esperando resposta"; se promessas+combinados < 30%, desligar `EVI_WHATSAPP_LLM_EXTRACT`) — relatório semanal
- [x] Flake da simulação: `getUpdates error: TimeoutError` no poller dentro do evi-sim (SIM-VOICE-03 1/3, VOICE-01 ~60 s). O fake usa relógio monotônico; investigar o servidor de fakes (threads) — `agent/testing/sim/fake_telegram.py` — feito em 2026-10-11
- [x] Ligar voz: `EVI_VOICE_ENABLED=true` no `.env` e recriar `agent-api` — feito em 2026-10-11
- [x] (2026-10-18: 0 turnos — registrado no BACKLOG) Avaliar em 2026-10-17 a validação da voz (≥ 3 turnos por voz; sucesso ≥ texto − 10 pontos; nenhuma voz sem resposta)
- [x] Instalar o watchdog (timer de usuário, sem sudo) — `docs/operations.md` — feito em 2026-10-11
- [x] Ligar o ack de tool lenta: `EVI_SLOW_ACK_SEC=5` no `.env` — feito em 2026-10-11
- [x] Publicar o novo script `search_emails` no Windmill (sem ele, apagar e-mail é recusado com segurança) — `wmill sync push` — feito em 2026-10-11
- [x] **Reconectar OAuth do Google no Windmill** — feito em 2026-10-11 (novos recursos `evi_gtasks`, `evi_gmail` com `gmail.modify`, `comprehensive_gcal` com `calendar`; `.env` atualizado; sonda 4/4 ok). Se o app OAuth estiver em modo "Teste" no Google Cloud, o token expira em 7 dias — publicar o app em Produção evita reconectar (Calendar, Tasks e Gmail expirados — a sonda de 2026-10-11 confirmou `reason=oauth` nos três) — Windmill UI (http://localhost:8001) → Resources → recursos gcal/gtasks/gmail → reconectar
- [ ] Criar projeto Gemini separado para a simulação (`EVI_SIM_GEMINI_API_KEY`) — `.env`
- [x] Reconectar o WhatsApp (sessão caiu em 10/10 00:28, código 401) — feito pelo usuário em 2026-10-11 (QR); `state: open`
- 2026-10-11 pós-deploy: reboot às 11:46 derrubou agent-api/postgres/qdrant (sem restart policy) → `restart: unless-stopped` + `make up/status/down`. Nomes do WhatsApp: agenda.vcf importada (219 nomes; backup em `data/backups/`), resolução de nomes por agenda > perfil > telefone (LID via `remoteJidAlt`), resumo agrupado por conversa com "Você" explícito; canais de notícias ignorados (`EVI_WHATSAPP_INCLUDE_CHANNELS`). 44 contatos da agenda sem correspondência no WhatsApp.
## Bloqueios
- (resolvido 2026-10-10 — usuário ampliou o orçamento em R$ 10) evi-reminders 3.1: cota diária do Gemini esgotada (429 RESOURCE_EXHAUSTED) com a chave de produção compartilhada. SIM-REM-01..04 passaram 3/3; SIM-REM-05 falhou só por 429. Faltam, quando a cota voltar: `./scripts/evi-sim up` → `./scripts/evi-sim run --id SIM-REM-05 --repeat 3 --llm live` → `--tag critical --llm record` (cassettes estão defasados pelas tools novas; o job `sim-replay` da CI fica vermelho até regravar) → `--tag critical --llm replay` → `--tag critical,adversarial,briefing --repeat 3 --llm live` → task 3.2 (arquivar). Tentado: esperar e repetir SIM-REM-05 uma vez (0/3, 429).
