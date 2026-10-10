## Context

| Peça existente | Onde | Uso aqui |
|---|---|---|
| Parser do Evolution mantém `fromMe` | `services/evolution_parser.py` (`from_me`) | Base do estado da conversa |
| Filtro de processamento descarta `fromMe` e eco do EVI | `services/evolution_filter.filter_for_processing` (`from_me`, `evi_echo`) | Continua valendo para extração |
| Chat de controle tratado antes da ingestão | `agent/main.py` (`control_jids`) | Nunca vira pendência |
| Grupos marcados por `@g.us` | `services/evolution_parser.py` | Fora do escopo |
| Fila de compromissos | `pending_commitments` (`type`, `event_date`, `due_date`, `status`, `source`) | Promessas e combinados |
| Seção WhatsApp do briefing | `services/briefing._collect_whatsapp` | Vira três subseções |
| Notificação avulsa | `commitment_capture_notify.notify_commitment_captured`, `commitment_review/deliver.maybe_notify_new_pending` | Desligada com a flag |

## Decisões

### 1. Estado por conversa, não histórico

```sql
CREATE TABLE IF NOT EXISTS wa_conversation_state (
  jid VARCHAR(128) PRIMARY KEY,
  last_in_at TIMESTAMPTZ,
  last_in_preview TEXT,        -- truncado em 160
  last_in_id VARCHAR(128),
  last_out_at TIMESTAMPTZ,
  acknowledged_at TIMESTAMPTZ, -- "respondido"/dispensado sem responder
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Atualizado no webhook para conversas **diretas** (não `@g.us`, não chat de controle):
mensagem recebida → `last_in_*`; mensagem `fromMe` que não é eco do EVI → `last_out_at`.
Feito antes de `filter_for_processing`, sem tocar no caminho de extração. Idempotente
por `source_id` (reentrega do webhook não muda nada além de repetir valores).

Pendência = `last_in_at > COALESCE(last_out_at, '-infinity')` e
`last_in_at > COALESCE(acknowledged_at, '-infinity')` e
`now - last_in_at` entre `EVI_REPLY_DEBT_HOURS` e 7 dias. Determinístico.

### 2. Promessas por heurística

Lista versionada e testada de padrões em pt-BR sobre mensagens `fromMe` diretas
("te mando", "te envio", "te aviso", "vejo e te falo", "te respondo", "amanhã te",
"vou ver e", "deixa comigo"). Casou → `pending_commitments` com `type='promise'`,
`source='whatsapp_from_me'`, `source_id` da mensagem, data resolvida pelos mesmos
helpers de `whatsapp_processor` quando houver ("amanhã"). Sem LLM. Só com a flag.

### 3. Combinados só com data

Com a flag, novos itens da extração atual sem `event_date` nem `due_date` entram com
`status='undated'`; `list_pending_commitments` (e, por consequência, briefing e
ferramentas) só lista `pending`. Sem flag, nada muda.

### 4. Briefing e ações

Com a flag, `_collect_whatsapp` vira três subseções na mesma seção (numeração contínua):
"Esperando sua resposta" (contato, há quanto tempo, trecho `wrap_external`), "Suas
promessas" (para quem, o quê, quando), "Combinados" (o quê, quando). Refs:
`reply_debt:<jid>`, `commitment:<id>`. Tools novas: `list_reply_debts`,
`dismiss_reply_debt(jid)` ("respondido"/"ignora" → `acknowledged_at=now`);
promessas usam `dismiss_commitments` (feito/descartado) e combinados `confirm_commitments`.
`AGENTS.md` ganha uma linha com esse mapeamento.

### 5. Fim da notificação avulsa

Com a flag, `notify_commitment_captured` e `maybe_notify_new_pending` retornam sem
enviar (registram em log). O briefing é o único canal.

### 6. Medida

Relatório semanal: por tipo (`reply_debt`, `promise`, `dated`), itens mostrados e
taxa de ação (respondido/feito/confirmado ÷ mostrados).

## Configuração

| Env | Default | Efeito |
|---|---|---|
| `EVI_REPLY_DEBTS_ENABLED` | `false` | Liga promessas, filtro de data, subseções do briefing e silencia a notificação avulsa |
| `EVI_REPLY_DEBT_HOURS` | `4` | Idade mínima da mensagem sem resposta |

## RAM / containers

Nenhum container novo. Uma tabela pequena (uma linha por conversa direta).

## Riscos

- **Privacidade**: o trecho da última mensagem fica no Postgres (160 caracteres), como
  já fica no `timeline.jsonl`. Não sai da máquina além do Telegram do próprio usuário.
- **Falso positivo de pendência**: mensagens que não pedem resposta ("ok", "👍").
  Mitigação: ignorar mensagens recebidas só com emoji/"ok"/"valeu"/"obrigad" (lista
  testada); "respondido" resolve o resto.
- **Usuário responde por outro aparelho**: o Evolution entrega `fromMe` de qualquer
  aparelho conectado; se não entregar, a pendência some com "respondido".

## Out of scope

Ver `proposal.md`.
