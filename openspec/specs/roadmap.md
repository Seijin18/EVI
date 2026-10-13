# EVI roadmap

**Reestruturado em 2026-10-10** após revisão de produto pelo fluxo de uso
([`docs/ux-review-2026-10.md`](../../docs/ux-review-2026-10.md)). A revisão de
2026-08-12 priorizou a base (hardening, correção, testes) e essa fase está
fechada. A fila agora é guiada pelo que o usuário percebe no dia a dia.

Histórico das etapas 1–17: [`BACKLOG.md`](../BACKLOG.md). Requisitos já
implementados vivem nas specs desta pasta; este arquivo descreve só o que **falta**.

---

## Princípio

> O EVI deve chegar até a pessoa no momento certo com o que exige ação, em vez de
> esperar ser perguntado.

Evidência que motivou a virada (Postgres, 2026-10-10): uso do `/chat` caiu de
520 mensagens (jun) para 0 (set/out); 37 compromissos extraídos do WhatsApp,
**0 confirmados**; stack parada ~6 semanas sem ninguém notar; "O que você pode
fazer?" entre os pedidos mais repetidos.

Canal de saída proativa: **Telegram**. O WhatsApp (Evolution/Baileys, número
pessoal, não-oficial) fica como fonte de leitura e canal de controle de baixo
volume — a Business API oficial proíbe chatbots de uso geral desde 15/01/2026 e o
caminho não-oficial tem risco de banimento por heurística. O EVI não envia
mensagens a terceiros por conta própria.

---

## Concluído (base) — Etapas 12–14, 17

| Etapa | Change | Entrega |
|---|---|---|
| 12 | `evi-runtime-hardening` | Isolamento de sessão, auth em todas as rotas mutáveis, serviços de dados em `127.0.0.1`, fuso via `now_local()`, deps pinadas, `soft_fail` |
| 13.1 | `evi-remove-dev-bridge` | Dev bridge removido (nunca rodou no container) |
| 13.2 | `evi-tool-result-contract` | `ToolResult` + `parse_windmill_result`; corrigiu falso "scheduled" |
| 13.3–13.5 | `evi-small-correctness` | Retry/motivo nos envios, heartbeat, eviction de `seen_ids` |
| 14.1 | `evi-container-smoke-ci` + `evi-smoke-isolation-fix` | Smoke de container na CI com isolamento de volumes/env |
| 14.2–14.7 | `evi-test-coverage-core` | +62 testes no caminho de tráfego (poller, Evolution, db com PG real, webhook) |
| 17 | `evi-contact-vcard-import` | Nomes da agenda por `.vcf` |

---

## Fila — em ordem de dependência

Um change ativo por vez. Cada item abaixo vira `openspec/changes/<slug>/` quando
o anterior for arquivado.

### Etapa V1 — Simulação do sistema montado — **Done** (2026-10-10)

Change: [`evi-sim-harness`](../changes/archive/2026-10-10-evi-sim-harness/proposal.md).
As-built: 21 cenários (real-usage 11, whatsapp 3, failure 3, adversarial 3, smoke 1); `critical` 3/3 live e verdes em replay (job `sim-replay` na CI). Achou e corrigiu: timeout ausente no cliente Gemini, fake Windmill aceitando chaves extras, docstring de `set_whatsapp_contact_name`.

**Por quê.** Os testes atuais mockam o LLM e as integrações; os problemas que
chegaram ao uso real estavam no sistema montado (tool errada, data relativa
errada, envelope do Windmill, path no container). E os harnesses "live" rodam
contra as contas reais e poluem a produção (3 compromissos "Teste digest Telegram").

**Escopo.** Projeto compose `evi-sim` isolado, com a imagem de produção, o poller
real do Telegram, o webhook real do Evolution, LLM real e os scripts Windmill reais;
falsos só nas bordas (Google, Telegram API, Evolution API) e no relógio
(libfaketime). Cenários YAML com expectativas sobre estado e efeitos; corpus inicial
derivado do uso real, de falhas e de injeção; taxa de aprovação com repetição;
record/replay do LLM para a CI.

**Pronto quando:** cenários `critical` 3/3 com LLM real e verdes em replay na CI.

### Etapa V2 — Validação com base no uso real — `evi-usage-validation` — **Done** (2026-10-10)

Change: [`evi-usage-validation`](../changes/archive/2026-10-10-evi-usage-validation/proposal.md).
As-built: `turn_log` em todo turno, `/bom` `/ruim`, sinais implícitos diários, relatório semanal (segunda 00:30), sonda diária somente-leitura, `evi-sim promote`, captura de formatos do Evolution. Ativação em produção depende dos schedules no Windmill.

**Por quê.** Nada mede se o EVI funciona para o usuário depois de integrado; os
sinais da revisão de 2026-10-10 só apareceram por consulta manual ao Postgres.

**Escopo.** `turn_log` com resultado estruturado das tools; sinais explícitos
(`/bom`, `/ruim`) e implícitos (correção, reformulação, falha); relatório semanal
com KPIs contra linha de base; sonda diária somente-leitura em produção; dados de
teste fora dos KPIs; `evi-sim promote` transforma falha real em cenário
anonimizado. Regra nova: todo change de comportamento declara "Validação em uso
real" (KPI, limiar, janela).

**Dependência.** V1 (o `promote` escreve cenários do simulador).
**Pronto quando:** 2 relatórios semanais seguidos entregues; 1 falha real promovida.

### Etapa 18 — Briefing matinal + guarda de injeção mínima — **Done** (2026-10-10)

Change: [`evi-morning-briefing`](../changes/archive/2026-10-10-evi-morning-briefing/proposal.md).
As-built: briefing determinístico com claim atômico por dia, histórico persistido, snapshot fixado; `wrap_external` em briefing, perfis, resumo e extração WhatsApp. Ligar com `EVI_BRIEFING_ENABLED=true` + schedule no Windmill.
Recuado para depois de V1/V2: nasce com cenários de simulação (`SIM-BRIEF-*`) e
com linha de base de uso para medir o efeito.
Briefing determinístico no Telegram (agenda, tarefas, e-mails que pedem ação,
pendências WhatsApp), numerado, com falha parcial visível; responder ao briefing
age sobre os itens. Inclui a parte mínima do #37: conteúdo de terceiros delimitado
(`wrap_external`) nos quatro caminhos que chegam ao grafo principal.

**Pronto quando:** briefing chega todo dia por 2 semanas; `evi_briefing_replied_total`
> 0 em pelo menos metade dos dias.

### Etapa 19 — Lembretes que disparam — `evi-reminders` — **Done** (2026-10-10)

Change: [`evi-reminders`](../changes/archive/2026-10-10-evi-reminders/proposal.md).
As-built: loop in-process com claim atômico, recorrência por preset com `anchor_day`, adiar/feito sem mover a série, atrasado nunca descartado. Ligar com `EVI_REMINDERS_ENABLED=true`.

**Por quê.** "Me lembra às 18h de pagar o boleto" é o recurso mais básico de
qualquer assistente por mensagem (Zapia, Perplexity, Poke) e hoje é impossível: o
EVI só cria evento no Google Calendar e depende da notificação de outro app.

**Escopo.**
- Tabela `reminders` (`id, due_at timestamptz, text, rrule NULL, status, chat_id,
  created_from`), tools `create_reminder`, `list_reminders`, `cancel_reminder`
  registradas no `registry.py`.
- Disparo por **loop in-process** no `agent-api` (mesmo padrão do
  `telegram_poller`, tick de 30 s), não por cron do Windmill: pontualidade é o
  que define confiança (crítica recorrente ao Poke são lembretes atrasados), e um
  cron por minuto no Windmill é mais pesado e mais uma dependência no caminho.
- Recorrência via `dateutil.rrule` (diária, semanal, mensal, dias úteis).
- Resposta ao lembrete: "feito", "adia 1h", "adia para amanhã" (snapshot como no
  briefing).
- Lembrete atrasado (stack fora do ar) é entregue ao voltar com a marca
  "atrasado", nunca descartado em silêncio.

**Fora.** Escalonamento para SMS/ligação; lembretes para terceiros; envio por WhatsApp.

**Dependência.** Etapa 18 (padrão de entrega + snapshot + `wrap_external`).
**Pronto quando:** desvio de disparo < 60 s em 95% dos casos (medido no log).

### Etapa 20 — Pendências de resposta e promessas — `evi-reply-debts` — **Done** (2026-10-10)

Change: [`evi-reply-debts`](../changes/archive/2026-10-10-evi-reply-debts/proposal.md).
As-built: estado por conversa direta, pendências determinísticas, promessas por padrão, combinados só com data, briefing em 3 grupos, fim da notificação avulsa. Ligar com `EVI_REPLY_DEBTS_ENABLED=true`.

**Por quê.** A extração de "compromissos" teve 0 confirmações em 37 itens. Os
itens chegam sem data ("Jantar"), sem sentido ("baixeii pra te mandar") ou sem
contexto para decidir. Repensar o alvo, não ajustar limiar. Referência:
Superhuman Auto Reminders (mensagens enviadas sem resposta).

**Escopo.**
- (a) **Esperando sua resposta**: conversa direta cuja última mensagem é do
  contato e tem mais de `N` horas. Determinístico, sem LLM.
- (b) **Promessas suas**: mensagens enviadas por você com padrão de compromisso
  ("te mando amanhã", "vejo e te falo"). Exige ingerir mensagens `fromMe` —
  **verificar** se o webhook/`evolution_filter` hoje as descarta (há echo guard).
- (c) Combinados com data explícita — a extração atual, restrita a itens com data
  resolvida.
- Cada item com trecho da conversa (`wrap_external`), data resolvida e ação de
  um toque. Entram no briefing; notificação avulsa deixa de existir.
- Métrica: taxa de confirmação por tipo.

**Decisão embutida.** Se a taxa de confirmação de (b)+(c) ficar abaixo de 30%
após duas semanas, desligar a extração por LLM e manter só (a).

**Dependência.** Etapa 18.

### Etapa 21 — Mensagens de voz — `evi-voice-input` — **Done** (2026-10-10)

Change: [`evi-voice-input`](../changes/archive/2026-10-10-evi-voice-input/proposal.md).
As-built: voz no Telegram e no chat de controle transcrita pelo Gemini com eco; áudio de terceiros nunca baixado. Ligar com `EVI_VOICE_ENABLED=true`.

**Por quê.** No Brasil, áudio é o modo padrão no WhatsApp; Zapia e Luzia nasceram
transcrevendo áudio. Hoje o EVI ignora `audioMessage`/voice.

**Escopo.**
- Voz no Telegram (`getFile`, OGG/Opus) e no chat de controle do WhatsApp
  (`audioMessage` via Evolution) → transcrição pelo Gemini (entrada de áudio
  nativa) → mesmo fluxo do texto, com a transcrição ecoada na resposta.
- Só áudio do próprio usuário. Áudios de terceiros não são transcritos por padrão.
- Com `EVI_LLM_PROVIDER=ollama`: resposta "áudio não suportado neste modo".

**Nota.** Reabre parcialmente o item cortado "Llava + Whisper": o motivo do corte
era rodar localmente na GTX 1060 3 GB. Via Gemini não usa GPU e cabe no free tier.
Ressalva: no free tier o Google pode usar o conteúdo para treino — aceitável para
comandos ditados ao próprio assistente, por isso o limite a áudio do usuário.

### Etapa 22 — Confiabilidade percebida — `evi-perceived-reliability` — **Done** (2026-10-10)

Change: [`evi-perceived-reliability`](../changes/archive/2026-10-10-evi-perceived-reliability/proposal.md).
As-built: watchdog externo (timer de usuário), `/ajuda` sem LLM, ack de tool lenta (`EVI_SLOW_ACK_SEC`), aviso de OAuth no turno com o controle diário da sonda.

Itens pequenos, independentes, que mudam a confiança no dia a dia.

| Item | Escopo |
|---|---|
| Alerta "EVI fora do ar" | `scripts/evi-watchdog` (systemd timer no host, fora do compose) chama `/health`; após 2 falhas seguidas manda direto na API do Telegram. Não pode depender do próprio EVI |
| "O que você pode fazer?" | Resposta curta e estável com 6–8 exemplos reais (`/ajuda` em `chat_commands` + linha no `AGENTS.md`) |
| Ack imediato | Tool que passa de ~5 s manda "fazendo…" antes do resultado (núcleo do antigo #38) |
| OAuth expirado | Detectar `reason=oauth` e avisar uma vez por dia com o link de reconexão do Windmill |

### Etapa 23 — Modelo de ameaça de injeção (restante) — `evi-prompt-injection-model` — **Done** (2026-10-11)

Change: [`evi-prompt-injection-model`](../changes/archive/2026-10-11-evi-prompt-injection-model/proposal.md).
As-built: Telegram restrito ao chat do usuário, exclusão de e-mail com prévia do código e "sim" na mensagem seguinte, guarda de escrita por origem do turno, saídas de tools delimitadas, `evi-test injection`.

A parte mínima (delimitação) entra na Etapa 18. Fica aqui:
- Confirmação obrigatória antes de tool destrutiva (`delete_emails_by_query` com
  mais de N itens, ou qualquer exclusão) — fluxo de dois passos.
- Allowlist de tools por origem do turno (turno disparado por conteúdo externo
  não tem tools de escrita).
- Corpus adversarial em `tests/fixtures/injection/` + `evi-test injection`.
- Referência: material de hardening do OpenClaw (conteúdo externo é hostil por
  padrão; nunca expor config/segredos).

### Etapa 24 — Execução em background (restante) — `evi-background-execution`

Depois do ack imediato (Etapa 22): tarefas longas desacopladas do turno, com
cancelamento e resultado entregue depois. Só abrir se o ack não bastar na prática.

### Etapa 25 — Promessas com contexto — `evi-promise-context` — **Done** (2026-10-13)

Change: [`evi-promise-context`](../changes/archive/2026-10-13-evi-promise-context/proposal.md).
As-built: padrão = gatilho, LLM (OpenRouter ZDR, `google/gemma-4-31b-it`) = juiz com a conversa antes/depois; `llm_structured.run_structured` (provedor por tarefa, ZDR fixo, teto diário); fila `needs_eval` nas colunas de `pending_commitments` avaliada pelo loop in-process (atraso 30 min, retry 30 min, 48 h → `pending`); varredura diária de cumprimento; `promise-reeval`; avaliador `llm-eval promise` (93% sintético); canais fora das dívidas; dedupe da Evolution.

### Etapa 26 — Conhecimento de contato — `evi-contact-knowledge` — **Done** (2026-10-13)

Change: [`evi-contact-knowledge`](../changes/archive/2026-10-13-evi-contact-knowledge/proposal.md).
As-built: `profile.md` com `## Fatos`/`## Em aberto` (substituídos, com data de evidência) e `## Notas` (só do usuário); `update_contact_knowledge` incremental via `run_structured("CONTACT_KNOWLEDGE")` (Gemma 4 26B → Qwen 3.8, OpenRouter ZDR) com janela de mensagens, validação de datas e filtro de injeção; timeline com os dois lados; `canonical_jid` (`wa_jid_alias`); lote diário 03:30 por JID (até 15); `contact-knowledge-migrate` e `contact-identity-migrate` (dry-run por padrão).

### Etapa 27 — Revisão de segurança — `evi-security-review` — **Done** (2026-10-13)

Change: [`evi-security-review`](../changes/archive/2026-10-13-evi-security-review/proposal.md).
As-built: modelo de ameaças e registro de 28 achados (`docs/security/`); `agent-api`/Windmill só em `127.0.0.1`; webhook global da Evolution desligado; segredos rotacionados por `evi-rotate-secrets`; autenticação obrigatória por padrão (`/metrics` incluído); grupo de controle do WhatsApp só aceita `from_me`; CVEs corrigidos; job `security` na CI (`evi-security-scan --ci`). Abertos para o usuário: Ollama (F5), plano Gemini (F6), SSH/ufw, WhatBot, OAuth, login do Windmill.

### Etapa 28 — Nomes de contato — `evi-contact-names` — **Done** (2026-10-13)

Change: [`evi-contact-names`](../changes/archive/2026-10-13-evi-contact-names/proposal.md).
As-built: script Windmill `list_contacts` (People API, só nome+telefones); `name_source` (`user`/`agenda`/`vcard`) e `apply_entries` genérico (nome do usuário nunca sobrescrito, ambíguos e números estrangeiros ignorados); `/jobs/contact-names-sync` (dry-run por padrão) e wrapper Windmill com schedule 03:15 desligado até o OAuth `gcontacts`; `@lid` herda nome do telefone; pergunta semanal no briefing de segunda com respostas determinísticas "nomeia N <nome>"/"ignora N" e sugestão de nome com evidência literal (`CONTACT_NAME_HINT`).

---

## Deferido (sem data)

| Item | Notas |
|------|-------|
| Snapshots estruturados de sessão (#34b) | Exige `response_format="content_and_artifact"` do LangChain. O briefing (Etapa 18) e os lembretes resolvem os casos de uso concretos com snapshot próprio; reabrir só se "apaga o primeiro" falhar fora deles |
| Briefing semanal / personalização de seções | Depois de medir o diário |
| Botões inline 👍/👎 no Telegram | Exige `callback_query` no poller; a métrica usa resposta textual por ora |
| Pool de conexões Postgres | ~4–6 conexões por turno de `/chat`. Sem evidência de gargalo |
| Gating de tools por configuração | 24 tools sempre ligadas; degrada seleção no fallback Ollama. Revisar quando lembretes/voz somarem tools |
| `/health` com checks concorrentes | 6 checks síncronos × 3 s bloqueiam uma thread |
| Compose profile Ollama | Conveniência |
| Empacotamento para terceiros | Docker + OAuth Windmill + QR Evolution é a maior barreira para uma "pessoa comum"; fora de foco enquanto o EVI é assistente de um usuário técnico |

## Cortado

| Item | Motivo |
|------|--------|
| **MCP servers isolados** | Resolve restart isolado — problema que o projeto não tem. Adiciona processos, latência e superfície de falha |
| **Llava + Whisper locais** | Incompatível com GTX 1060 3 GB (`OLLAMA_MAX_LOADED_MODELS=1`). A parte de áudio foi reaberta via Gemini na Etapa 21; visão continua cortada |
| **Cache Redis de embeddings** | Otimização sem medição |
| **Adapter WhatsApp Meta/Twilio** | A Business API proíbe exatamente este caso de uso (chatbot de uso geral) desde 15/01/2026 |
| **Dev bridge** | Removido em 12/08/2026 (`evi-remove-dev-bridge`). Use `ssh` |
