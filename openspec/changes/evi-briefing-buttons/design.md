## Context

- Envio: `telegram_notify.send_telegram_message(text, chat_id, *, parse_mode)` só faz
  `sendMessage` (sem `reply_markup`).
- Entrada: `telegram_poller.fetch_updates` chama `getUpdates` sem `allowed_updates`;
  `telegram_handler.process_telegram_update` só lê `update["message"]`, com a allowlist
  `_chat_allowed` primeiro. O webhook `/webhooks/telegram` usa a mesma função.
- Itens numerados do briefing → `refs` no snapshot `morning_briefing` (`kind:id`:
  `reply_debt:<jid>`, `commitment:<id>`, `name_prompt:<jid>`, `event/task/email`);
  `resolve_briefing_items(numbers, session_id, kind)` resolve pelo dia local.
- Ações hoje: `dismiss_reply_debt(…, briefing_items)` → `db.acknowledge`;
  `confirm_commitments(…, briefing_items)` / `dismiss_commitments(…)`; nome: `try_name_reply`.
- Engajamento: `briefing_log.replied_at` via `note_user_reply` (janela de horas).

## Decisions

### 1. Teclado
Uma linha por item acionável visível (depois do `fit_volume`), na ordem do briefing:
`[N ✅] [N ✖]` (nome: só `[N ✖ ignorar]`). Última linha `[👍] [👎]`. Sem botão para
agenda/e-mail/tarefa nesta versão. Teto: 10 linhas de itens (o resto continua por texto).

### 2. `callback_data`
`b1:<yyyymmdd>:<n>:<a>` (≤ 20 bytes): versão, dia do briefing, número, ação
(`ok` | `no` | `up` | `dn`). O servidor resolve `n` pelo snapshot do dia; o tipo do item
decide a função (`ok` em dívida = respondido; em commitment = confirmar; `no` = ignorar/
dispensar). Nada de jid, id ou texto no botão.

### 3. Tratamento
`allowed_updates=["message","callback_query"]` no `getUpdates`. Callback:
1. chat e remetente na allowlist (`_chat_allowed` sobre `message.chat.id` e `from.id`);
2. parse estrito; dia ≠ do snapshot atual → resposta "Esse briefing é antigo" e nada muda;
3. executa a função determinística (mesmas usadas pelas tools, sem LLM);
4. `answerCallbackQuery` com texto curto ("Ok, marcado como respondido");
5. `editMessageReplyMarkup` tirando a linha do item (ou trocando por `✓ N`);
6. `briefing_log.replied_at` marcado; `turn_log` com `input_kind='button'`.
Idempotente: tocar duas vezes não confirma em dobro (as funções já filtram por status).

### 4. Feedback
`briefing_log.feedback` (`up`/`down`, último vale) + nota opcional futura. Entra no
relatório semanal.

### 5. Falhas
Se o envio com teclado falhar (HTML/markup), reenvia sem teclado (texto continua valendo).
Callback com erro → resposta "Não consegui; responda 'respondido N'".

### 6. Flag
`EVI_BRIEFING_BUTTONS` (padrão `true`).

### 7. As-built (sincronização)
- ✅ numa **promessa** marca a promessa como feita (`done`, `confirmed_via='telegram_button'`); em
  combinado datado confirma pelo mesmo caminho da tool. ✖ dispensa os dois.
- A linha 👍/👎 fica no teclado com ✓ no escolhido (permite trocar a nota; o último toque vale).
- Guarda extra: o `message_id` do toque tem de ser o do briefing gravado no snapshot (evita que o
  teclado da manhã use os números de outro briefing do mesmo dia).
- Idempotência por lista `done` de números no snapshot mais recente.

## Riscos

- Botão em briefing de outro dia: resolvido pelo dia no `callback_data`.
- Telegram limita `callback_data` a 64 bytes: formato curto fixo.
- RAM: nenhuma.

## Out of scope

Botões em outras mensagens; escolha de horário.
