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
