## Context

- Botões do briefing: `briefing.callback_data`/`parse_callback_data` (`b1:<dia>:<m|e>:<n>:<ação>`,
  resolvido pelo snapshot do dia, `message_id` conferido, falha fechada). Despacho em
  `telegram_handler.handle_briefing_callback`.
- Confirmações criadas pelos changes anteriores da fila: `evi-contact-policy` (`p1:` mudança de
  política e purge), `evi-study-calendar` (publicar grade, remover aulas, associar material) e
  `evi-capability-gaps` (`g1:` ⭐/✖). **Reler esses módulos ao ativar**: os nomes exatos vêm da
  implementação deles.
- A guarda de origem do turno (`write_guard`) impede que conteúdo externo dispare escrita.

## Decisions

### 1. Modelo
`proposals(id bigserial, kind text, title text, body text, payload jsonb, origin text,
state text check in ('pending','approved','rejected','expired','executed','failed'),
version int, chat_id text, tg_message_id bigint, created_at, expires_at, decided_at, result text)`.
`payload` guarda só o necessário para executar (ids, JIDs canônicos, hashes), nunca texto de
terceiros sem `wrap_external`.

### 2. Executores
`proposals.register(kind, *, execute, render, editable=False, ttl=timedelta)`. `execute(payload)
-> ToolResult` roda **só** em `approve`, numa transação que muda `pending → approved → executed|failed`
(idempotente: um segundo toque responde "já feito"). `render(payload)` produz o texto da
mensagem. Tipos iniciais: `policy_change`, `contact_purge`, `study_publish`, `study_remove`,
`study_material`, `gap_triage`.

### 3. Telegram
`callback_data = a1:<id>:<version>:<ok|no|ed>` (≤ 64 bytes). O handler confere o chat do usuário,
`tg_message_id`, `version` e `state=pending`; qualquer divergência falha fechada ("essa proposta
mudou ou já foi decidida"). ✏️ (só `editable`): "responda a esta mensagem com a correção"; a
resposta cria `version+1` e uma mensagem nova. Neste change nenhum tipo é editável; o caminho
fica testado com um tipo de teste.

### 4. Listagem e briefing
`/pendentes`: até 10, as mais antigas primeiro, com o mesmo botão. Briefing da manhã: linha
"🗂 Aguardando você (N): …" com os 3 títulos mais antigos, dentro do teto de linhas.

### 5. Expiração
TTL por tipo (padrão 7 dias; `study_material` 30 dias; `policy_change` 1 dia). O loop in-process
existente (o mesmo dos lembretes) marca `expired` e edita a mensagem ("expirou"). Nunca executa.

### 6. Autonomia
`autonomy_levels(kind pk, level text default 'L1')`. Neste change só `L1` tem efeito. Comando
`autonomia <tipo> L0|L1` (L2+ recusado com "ainda não disponível"). A mudança de nível também é
registrada como proposta.

### 7. API
`GET /v1/proposals?state=pending` e `POST /v1/proposals/{id}/approve|reject`, com `Depends`
de autenticação existente; ação pela API passa pelo mesmo `approve` (mesma idempotência).

## Riscos

- **Migração das confirmações**: feita tipo a tipo, com o teste antigo de cada fluxo mantido.
- **Mensagens órfãs** (proposta decidida pela API): a mensagem do Telegram é editada para
  "decidido em outro lugar".

## Out of scope

Rascunhos; L2/L3; tela; envio a terceiros.

## RAM

Sem container novo.
