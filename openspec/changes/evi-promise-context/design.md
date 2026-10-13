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

### Avaliação prévia (2026-10-12)

Antes de fechar o desenho, o prompt foi medido com um avaliador fora do repo (scratchpad;
vira a task 2.0): 30 casos simulados do dia a dia (pedido + "pode deixar", agradecimento,
negação, pergunta, passado, promessa do contato, oferta genérica, condicional, datas
relativas, já cumprida, injeção) e 24 casos reais das conversas do usuário (rótulos
revisáveis). GPU: GTX 1060 3 GB, ~2,5 GB livres.

Resultado (prompt v3/v4; "simulados" = 30 casos, "reais" = 24; nuvem só nos simulados):

| Modelo | Onde | Simulados | Reais | Falsos positivos | p50 |
|---|---|---|---|---|---|
| qwen2.5:3b (atual) | local | 53% | 29% | 3 | 5 s |
| granite4:micro | local | 50% | 46% | 12 | 5 s |
| qwen3:1.7b | local | 47% | 29% | 12 | 1,7 s |
| qwen3:1.7b + think | local | 63% | 29% | 5 | 15 s (4 timeouts) |
| qwen3:4b | local | 67% | 42% | 11 | 7 s |
| qwen3:4b + think | local | — | — | — | 50/54 timeouts (120 s) |
| qwen3:4b, prompt v4 (sem cópia de exemplo, `done` só por mensagem do usuário) | local | 70% | 54% | 10 | 6,8 s |
| Gemini 2.5 Flash (direto) | nuvem | 80% | — | 2 | 1 s |
| qwen/qwen3.8-27b | OpenRouter ZDR | 93% | 88% | 1 | 1,1 s |
| qwen/qwen3.5-35b-a3b | OpenRouter ZDR | 93% | — | 0 | 1,0 s |
| google/gemini-3.1-flash-lite | OpenRouter ZDR | 93% | — | 1 | 1,5 s |
| **google/gemma-4-31b-it** | OpenRouter ZDR | **90%** | **96%** | 0 | 1,2–2,5 s |
| google/gemma-4-26b-a4b-it | OpenRouter ZDR | 87% | — | 1 | 1,0 s |
| openai/gpt-oss-120b | OpenRouter ZDR | 73% | — | 6 | 2,0 s |
| mistralai/mistral-small-2603 | OpenRouter ZDR | inconclusivo (429 do provedor) | | | |

Custo da rodada inteira na nuvem: ~US$ 0,03. **Conclusão: nenhum modelo que cabe na
GTX 1060 (≤ 4B) chega perto do aceitável** — erram metade dos casos reais e/ou geram
falsos positivos (o problema original). Modelos abertos de 27–35B via OpenRouter com
retenção zero acertam 90–93%.

Achados que mudaram o desenho:

- **Promessas são cumpridas logo depois.** Nos casos reais, link do drive, senha e dados
  do outro carro foram enviados de 1 min a 3 h depois da promessa. Avaliar na hora gera
  pendência já resolvida → avaliação com atraso + checagem de cumprimento (§4).
- **LLM erra conta de data.** "sexta" virou 18/10 (qwen2.5) — o LLM só copia a expressão
  de prazo; o código resolve (§3). `_resolve_date` não entende "dia 20", "fim de semana",
  "semana que vem", "às 19h" (= hoje) → estendido.
- **Campo de raciocínio antes da decisão** (`pedido`) e três exemplos curtos ajudam o
  modelo a usar o pedido do contato; "oferta genérica" ("qualquer coisa te aviso") precisa
  estar listada como negativo explícito.
- **O gatilho de padrão já elimina** pergunta, negação e passado antes do LLM.

## Decisions

### 1. Padrão = gatilho, LLM = juiz

Casou o padrão (`detect_promise`) → agenda avaliação. A decisão "é promessa?", o título e
"já cumprida?" vêm do LLM com contexto. Sem padrão, nada é avaliado.

### 2. Camada de tarefa estruturada, com provedor por tarefa

Novo `agent/services/llm_structured.py`, compartilhado com `evi-contact-knowledge`:

```python
run_structured(task: str, prompt: str, schema: dict) -> dict | None
```

- Provedor e modelo por tarefa: `EVI_LLM_TASK_<TASK>_PROVIDER` (`openrouter` | `ollama` |
  `gemini`) e `EVI_LLM_TASK_<TASK>_MODEL` (lista separada por vírgula = fallback de
  modelo dentro do mesmo provedor, campo `models` do OpenRouter).
- **OpenRouter sempre com** `provider: {zdr: true, data_collection: "deny",
  require_parameters: true}` e `response_format: json_schema` `strict` — fixo no código,
  não configurável: retenção zero é condição para mandar conversas para fora.
- Teto de gasto: `EVI_LLM_TASK_DAILY_USD` (default 0,10) somando `usage.cost` de cada
  resposta (tabela `llm_task_usage`); estourou → `None` (cai no `needs_eval`).
- Saída estruturada nativa: Ollama `format=<json schema>`, `temperature=0`, `think`
  configurável (`EVI_LLM_TASK_<TASK>_THINK`); Gemini `responseSchema` +
  `propertyOrdering` (a ordem dos campos importa: raciocínio antes da decisão).
- Valida o JSON contra o schema; inválido/timeout → `None` (o chamador decide).
- **Sem fallback automático para nuvem.** `EVI_LLM_TASK_<TASK>_FALLBACK=gemini` é opt-in
  explícito: mandar conversas para fora é decisão do usuário, não do código.
- Sem LangChain no caminho (chamada HTTP direta, como `whatsapp_llm_extract`): schema
  nativo e `think` não passam pelo wrapper atual.

Tarefa deste change: `PROMISE`. **Default: `openrouter`,
`google/gemma-4-31b-it,qwen/qwen3.8-27b`** — Gemma 4 31B teve o melhor resultado nos casos
reais (23/24, 0 falso positivo; o único erro é o caso ambíguo "vou só confirmar e te
aviso"); Qwen 3.8 27B como fallback de modelo.
Estimativa: ~10 avaliações/dia × ~US$ 0,0003 ≈ US$ 0,10/mês. `ollama` continua
suportado (para quem aceitar a qualidade medida) e o avaliador é o gate para trocar.

### 3. Contexto, prompt e saída

`promise_context.conversation_context(jid, at_ts, knowledge="")`: até 10 mensagens antes
(24 h) e as mensagens depois até o momento da avaliação, dos dois lados, via
`findMessages`; fallback `read_timeline_tail(jid, 6)`. Texto do contato em
`wrap_external`. Nome do contato pelo registro (`effective_label`).

Schema (nesta ordem):

```json
{"pedido": "str", "usuario_se_compromete": "bool", "what": "str", "quando": "str", "done": "bool"}
```

`due = resolve_due(quando, ts_da_mensagem)` no código (estende `_resolve_date`).
`what` vazio ou só verbo genérico ("Avisar", "Responder", "Mandar") → tratado como não.

**Perfil do contato fica de fora, por enquanto.** O `profile.md` atual não serve como
contexto (lê só o início; 41/42 vazios; a única síntese trata a criação do perfil como
"reunião"). `evi-contact-knowledge` cria `read_contact_knowledge(jid)` e liga no
parâmetro `knowledge`.

### 4. Avaliação com atraso e cumprimento

- A avaliação roda `EVI_PROMISE_EVAL_DELAY_MIN` (default 30) min depois da mensagem, com
  as mensagens que vieram depois no contexto (`done`). Promessa já cumprida não é gravada.
- Varredura diária antes do briefing (06:45, mesmo job do probe/briefing no Windmill ou
  loop in-process dos lembretes): promessas `pending` com mensagens novas do usuário no
  chat são reavaliadas só quanto a `done` → `status='done'`.

### 5. Falha do LLM: `needs_eval`

Sem resposta válida → linha gravada com `status='needs_eval'` (fora de listagens,
briefing e notificações). Nova tentativa em 30 min; depois, na varredura diária. Após
48 h sem avaliação → `pending` com o texto original (nada some em silêncio).

### 6. Fora do caminho do webhook

`capture_promises` grava `needs_eval` imediatamente (idempotência por
`(source, source_id)`) com `next_eval_at = msg_ts + delay` e `eval_attempts = 0`
(colunas novas em `pending_commitments`; não existe tabela `background_jobs` — o estado
da fila é a própria linha). O loop in-process (o mesmo dos lembretes, `evi-reminders`)
pega linhas `needs_eval` com `next_eval_at <= now`. Reinício do container não perde nada: o estado está no
Postgres.

### 7. Reavaliação das existentes

`./scripts/evi-test promise-reeval` (dry-run; `--apply` grava): cada `type='promise'`
`pending`, contexto em torno de `created_at` (antes + depois). Não → `dismissed`; sim e
cumprida → `done`; sim → título/data novos. Falha → não mexe.

### 8. Avaliador no repositório

`agent/testing/llm_eval/` + `./scripts/evi-test llm-eval promise [--model M] [--provider P]`:
casos simulados versionados em `tests/eval/promise_cases.yaml`; casos reais **só locais**
em `data/eval/promise_real.json` (gitignored), gerados por
`./scripts/evi-test llm-eval-collect promise`. Gemini nunca recebe os casos reais.
Saída: acerto, FP/FN, título, data, p50/p95. É o gate para trocar modelo ou prompt.

### 9. Flag

`EVI_PROMISE_CONTEXT_ENABLED` (default `true` quando `EVI_REPLY_DEBTS_ENABLED=true`):
`false` volta ao comportamento só-padrão sem deploy.

## Riscos

- **Privacidade**: com o default, até ~15 mensagens por promessa saem da máquina para o
  OpenRouter e um provedor com retenção zero (políticas verificadas em 2026-10-12:
  OpenRouter não guarda prompts por padrão; `zdr` filtra endpoints que não retêm;
  `data_collection: deny` exclui quem treina). Aprovado pelo usuário em
  2026-10-12 (proposta). O avaliador nunca manda os casos reais para a nuvem sem `--allow-cloud-real`.
- **Disponibilidade/limite do provedor**: 429 visto no Mistral; fallback de modelo na
  lista + `needs_eval` cobrem.
- **Custo**: teto diário no código; crédito pré-pago com limite mensal na conta.
- **VRAM**: `OLLAMA_MAX_LOADED_MODELS=1`; se a tarefa usar um modelo diferente do chat,
  cada troca custa o carregamento (~2–5 s). Avaliações são poucas e atrasadas: aceitável.
- **Custo/latência**: ~5–10 avaliações/dia; nenhuma no caminho do usuário.

## Out of scope

- Detecção de promessas sem padrão; promessas em grupos.
- Gravar `fromMe` na timeline e usar o perfil do contato no prompt: vêm em
  `evi-contact-knowledge` (próximo da fila).
