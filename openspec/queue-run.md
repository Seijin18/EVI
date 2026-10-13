# Execução da fila — iniciada 2026-10-12 (2ª rodada)
## Estado
- Change atual: evi-promise-context (fase: implementar) — tasks 2.0, 2.1, 2.2, 3.1, 3.2 fechadas; próximas 3.3, 3.4, 4.1, 4.2
- Ordem: evi-promise-context → evi-security-review → evi-contact-knowledge → evi-contact-names → evi-ux-review
- Concluídos: —
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
## Pendências do usuário (não bloqueantes)
## Bloqueios

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
- [ ] Avaliar em 2026-10-17 a validação dos lembretes (desvio < 60 s em ≥ 95%, nenhum vencido sem envio, ≥ 3 lembretes criados) — relatório semanal
- [x] Decidir se a produção usa `EVI_GEMINI_THINKING_BUDGET=0` (a simulação inteira passou com 0; custo cai ~50%) — `.env` — feito em 2026-10-11
- [x] Ligar pendências de resposta: `EVI_REPLY_DEBTS_ENABLED=true` (para de mandar notificação avulsa de compromisso; o briefing passa a ter 3 grupos) — feito em 2026-10-11
- [ ] Avaliar em 2026-10-24 a validação do evi-reply-debts (ação ≥ 30% em "esperando resposta"; se promessas+combinados < 30%, desligar `EVI_WHATSAPP_LLM_EXTRACT`) — relatório semanal
- [x] Flake da simulação: `getUpdates error: TimeoutError` no poller dentro do evi-sim (SIM-VOICE-03 1/3, VOICE-01 ~60 s). O fake usa relógio monotônico; investigar o servidor de fakes (threads) — `agent/testing/sim/fake_telegram.py` — feito em 2026-10-11
- [x] Ligar voz: `EVI_VOICE_ENABLED=true` no `.env` e recriar `agent-api` — feito em 2026-10-11
- [ ] Avaliar em 2026-10-17 a validação da voz (≥ 3 turnos por voz; sucesso ≥ texto − 10 pontos; nenhuma voz sem resposta)
- [x] Instalar o watchdog (timer de usuário, sem sudo) — `docs/operations.md` — feito em 2026-10-11
- [x] Ligar o ack de tool lenta: `EVI_SLOW_ACK_SEC=5` no `.env` — feito em 2026-10-11
- [x] Publicar o novo script `search_emails` no Windmill (sem ele, apagar e-mail é recusado com segurança) — `wmill sync push` — feito em 2026-10-11
- [x] **Reconectar OAuth do Google no Windmill** — feito em 2026-10-11 (novos recursos `evi_gtasks`, `evi_gmail` com `gmail.modify`, `comprehensive_gcal` com `calendar`; `.env` atualizado; sonda 4/4 ok). Se o app OAuth estiver em modo "Teste" no Google Cloud, o token expira em 7 dias — publicar o app em Produção evita reconectar (Calendar, Tasks e Gmail expirados — a sonda de 2026-10-11 confirmou `reason=oauth` nos três) — Windmill UI (http://localhost:8001) → Resources → recursos gcal/gtasks/gmail → reconectar
- [ ] Criar projeto Gemini separado para a simulação (`EVI_SIM_GEMINI_API_KEY`) — `.env`
- [x] Reconectar o WhatsApp (sessão caiu em 10/10 00:28, código 401) — feito pelo usuário em 2026-10-11 (QR); `state: open`
- 2026-10-11 pós-deploy: reboot às 11:46 derrubou agent-api/postgres/qdrant (sem restart policy) → `restart: unless-stopped` + `make up/status/down`. Nomes do WhatsApp: agenda.vcf importada (219 nomes; backup em `data/backups/`), resolução de nomes por agenda > perfil > telefone (LID via `remoteJidAlt`), resumo agrupado por conversa com "Você" explícito; canais de notícias ignorados (`EVI_WHATSAPP_INCLUDE_CHANNELS`). 44 contatos da agenda sem correspondência no WhatsApp.
## Bloqueios
- (resolvido 2026-10-10 — usuário ampliou o orçamento em R$ 10) evi-reminders 3.1: cota diária do Gemini esgotada (429 RESOURCE_EXHAUSTED) com a chave de produção compartilhada. SIM-REM-01..04 passaram 3/3; SIM-REM-05 falhou só por 429. Faltam, quando a cota voltar: `./scripts/evi-sim up` → `./scripts/evi-sim run --id SIM-REM-05 --repeat 3 --llm live` → `--tag critical --llm record` (cassettes estão defasados pelas tools novas; o job `sim-replay` da CI fica vermelho até regravar) → `--tag critical --llm replay` → `--tag critical,adversarial,briefing --repeat 3 --llm live` → task 3.2 (arquivar). Tentado: esperar e repetir SIM-REM-05 uma vez (0/3, 429).
