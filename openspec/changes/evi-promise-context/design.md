## Context

`promises.capture_promises` roda no webhook (`main.py`) logo após
`reply_debts.track_conversation`, só com `EVI_REPLY_DEBTS_ENABLED=true`. Hoje grava
qualquer `fromMe` direta que case `PROMISE_PATTERNS`, com o texto do usuário como título.

Fontes de contexto disponíveis:

| Fonte | Lados | Atualidade | Uso |
|---|---|---|---|
| Evolution `findMessages` (por chat) | contato + usuário | tempo real | **primária** |
| `timeline.jsonl` (`read_timeline_tail`) | só recebidas (`EVI_WHATSAPP_INCOMING_ONLY=true`) | por ingest | fallback |

`parse_evolution_message_list` deduplica por id da mensagem (fix `b6148ca`): a Evolution
grava a mesma mensagem duas vezes após reconectar.

## Decisions

### 1. Padrão = gatilho, LLM = juiz

Casou o padrão → enfileira avaliação. A decisão "é promessa?" e o título vêm do LLM com
contexto. Sem padrão, nada é avaliado (custo e ruído controlados).

### 2. Contexto

`promise_context.conversation_context(jid, before_ts)`: últimas até 10 mensagens do chat
via `findMessages`, dentro de 24 h antes da mensagem, em ordem cronológica, cada uma como
`Você: …` / `<nome>: …`. Falhou a Evolution → `read_timeline_tail(jid, 6)`. Todo texto de
terceiros passa por `wrap_external` (modelo de prompt injection, `2026-10-11`).

O nome do contato vem do registro Postgres (`effective_label`), para o título dizer
"para a Eliana" e não um número.

**Perfil do contato fica de fora, por enquanto.** O `profile.md` atual não serve como
contexto: `read_profile_excerpt` lê os primeiros N caracteres (cabeçalho + a síntese mais
antiga), 41 de 42 perfis estão vazios e a única síntese existente trata a data de criação
do perfil como uma "reunião". Colocá-lo no prompt piora a decisão. O change seguinte,
`evi-contact-knowledge`, cria `read_contact_knowledge(jid)` (fatos com evidência +
assuntos em aberto) e tem uma task para ligá-lo aqui. `conversation_context` já recebe
um parâmetro `knowledge: str = ""` para que essa ligação seja de uma linha.

### 3. Prompt e saída

Entrada: data de referência, nome do contato, contexto e a mensagem do usuário. Saída JSON:
`{"promise": false}` ou `{"promise": true, "what": "<verbo no infinitivo + objeto + para
quem>", "due": "YYYY-MM-DD"|null, "time": "HH:MM"|null}`. `what` vazio ou genérico
("Responder", "Avisar") conta como `false`. Modelo: o tier de fundo de `build_llm`
(Ollama local), timeout `EVI_WHATSAPP_LLM_TIMEOUT_SEC`.

### 4. Falha do LLM

Timeout/parse inválido → grava como hoje (título = texto do usuário). Evita perder
promessa real quando o LLM local está fora; o relatório semanal mostra se isso vira ruído.

### 5. Fora do caminho do webhook

`capture_promises` só detecta e agenda; a avaliação roda em
`services.background_jobs.run_in_background("promise_context", …)`. Idempotência continua
por `(source, source_id)`.

### 6. Reavaliação das existentes

`reevaluate_pending_promises()` (chamada única via `evi-test`/CLI, não job agendado):
para cada `type='promise'`, `status='pending'`, reconstrói o contexto em torno de
`created_at`. LLM diz "não" → `status='dismissed'`; diz "sim" → atualiza título/data.
Falha → não mexe.

### 7. Flag

`EVI_PROMISE_CONTEXT_ENABLED` (default `true` quando `EVI_REPLY_DEBTS_ENABLED=true`):
permite voltar ao comportamento só-heurística sem deploy.

## Riscos

- **Privacidade**: até 10 mensagens vão ao LLM. Com o tier local (Ollama) não saem da
  máquina; se `EVI_LLM_PROVIDER=gemini` for o único disponível, o trecho sai — mesmo
  perfil do `summarize_whatsapp` atual.
- **Custo/latência**: uma chamada por mensagem que casa o padrão (~5–10/dia no uso real).
- **RAM**: nenhum container novo; usa o Ollama já carregado.

## Out of scope

- Detecção de promessas sem padrão; promessas em grupos.
- Gravar `fromMe` na timeline e usar o perfil do contato no prompt: vêm em
  `evi-contact-knowledge` (próximo da fila).
