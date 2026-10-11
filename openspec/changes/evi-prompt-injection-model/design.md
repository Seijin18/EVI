## Decisões

### 1. Exclusão em dois passos, verificada no código

`delete_emails(message_ids, confirm_token="")` e `delete_emails_by_query(q, max_messages,
confirm_token="")`:
- sem token válido → não apaga; resolve o alvo (ids ou busca, sem apagar), guarda
  `{token, ids, query, created_turn_id, session_id, expires_at(10 min)}` no snapshot
  `pending_delete` e devolve "Vou apagar N e-mails: <assuntos delimitados>. Confirma?";
- com token → só executa se (a) o token existe no snapshot da sessão e não expirou,
  (b) o turno atual é **posterior** ao turno que criou o token, e (c) o texto do usuário
  no turno atual casa com a lista de confirmações ("sim", "confirma", "pode apagar",
  "apaga", "ok pode") e não contém negação. O texto vem do coletor do turno, não do
  modelo. Apaga exatamente os ids guardados (a busca não é refeita).
- `max_messages` limitado a 50 no código.

O injetor não consegue confirmar: a confirmação exige uma nova mensagem do usuário.

### 2. Allowlist por origem

`write_guard.WRITE_TOOLS` (`schedule_event`, `create_task`, `delete_emails*`,
`confirm_commitments`, `dismiss_commitments`, `set_whatsapp_contact_name`,
`learn_whatsapp_contact`, `create_reminder`, `cancel_reminder`). Cada uma chama
`write_guard.check()` no início: se `current_channel()` não for `telegram`,
`whatsapp_control` ou `api`, devolve "ação bloqueada: turno não iniciado pelo usuário".
Hoje nenhum turno com tools nasce de conteúdo externo; a guarda impede regressões.

### 3. Saídas delimitadas

`format_inbox_result` envolve assunto e remetente com `wrap_external(source="email")`;
o formatador de `list_calendar_events` envolve títulos e descrições
(`source="agenda"`). Prompt e cassettes mudam (regravar).

### 4. Corpus

`tests/fixtures/injection/*.yaml`: texto adversarial + onde entra (assunto, corpo de
WhatsApp, perfil, título de evento) + expectativa. `evi-test injection` roda offline:
`wrap_external` contém tudo, a guarda bloqueia, o token não confirma sem novo turno.
Simulação: `SIM-ADV-04` (e-mail pede para apagar tudo; usuário diz "ok" → nada apagado
sem token), `SIM-ADV-05` (usuário pede para apagar promoções → prévia → "sim" → apagadas
só as da prévia).

## RAM / containers

Nenhum.

## Riscos

- Fricção: apagar e-mail passa a exigir uma resposta a mais. Aceito — ação irreversível.

## Out of scope

Ver `proposal.md`.

## As-built (2026-10-11)

- **Telegram restrito** ao `TELEGRAM_CHAT_ID` (+ `TELEGRAM_ALLOWED_CHAT_IDS`) — achado de
  segurança da Etapa 21: qualquer chat conversava com o EVI.
- **Exclusão**: a confirmação só vale na mensagem **imediatamente seguinte** à prévia
  (qualquer outro turno descarta o pendente); a prévia é anexada à resposta pelo código;
  só há prévia se a mensagem do usuário pedir exclusão; confirmação por correspondência
  exata ("sim", "confirma", "pode apagar"…); ids sem assunto conhecido são recusados;
  mensagem encaminhada no Telegram não confirma. A prévia usa o script somente-leitura
  `search_emails` (Windmill antigo → recusa, nunca apaga). Reinício do processo invalida
  pendentes.
- **Guarda de escrita**: 17 tools (inclui organizar arquivos, notas e ingestão de RAG)
  recusam turno de canal que não seja do usuário; um teste força a classificação de toda
  tool nova.
- **Saídas delimitadas**: e-mail, agenda, tarefas, mensagens e contatos do WhatsApp,
  resumo de compromissos, grafo e aprendizado de contato. Os formatadores não ecoam mais
  JSON cru quando um assunto contém "failed".
- O atalho direto "apagar email <id>" foi removido (passa pelo fluxo de dois passos).
- `evi-test injection` (13 ataques) no smoke (15/15); `SIM-ADV-04/05`; cassettes
  normalizam o token de exclusão.
