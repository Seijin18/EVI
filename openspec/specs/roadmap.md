# EVI roadmap

**Reestruturado em 2026-08-12** após revisão geral do sistema. A ordem anterior
priorizava features novas sobre a base; esta versão inverte isso. Os itens abaixo
estão em ordem de dependência — cada etapa assume a anterior fechada.

Histórico das etapas 1–11 (todas concluídas): [`BACKLOG.md`](../BACKLOG.md).

---

## Etapa 12 — Runtime hardening — **Done** (12 Ago 2026)

`evi-runtime-hardening`, arquivado 2026-08-12.

| Item | Estado |
|------|--------|
| Isolamento de sessão | Done — `services/session_memory.py` (LRU por `session_id`). Junto: `_on_trim` deixou de sobreviver a `clear()`, `_reset_session` passou a usar seu argumento, `/insight` deixou de ler o buffer global, e os locks do `session_lane` ganharam teto |
| Auth em `/note`, `/insight`, `/reset`, `/tools` | Done — `Depends` nos quatro + `EVI_REQUIRE_API_KEY` (default `false`) |
| Serviços de dados fora de `0.0.0.0` | Done — `127.0.0.1`, PG no host em **5433**, Qdrant com `QDRANT_API_KEY` |
| Fuso horário na CALENDAR LOOKUP TABLE | Done — `now_local()` com `ZoneInfo(EVI_TIMEZONE)` |
| Pin de dependências + sem `--reload` | Done — `agent/requirements.txt` (LangChain 0.3 → **1.3.15**, 243 testes verdes na major nova) |
| `build_background_llm` sem mutar `os.environ` | Done — provider explícito; `extract_llm_text` também recebe o provider certo |
| Log nos `except Exception: pass` | Done — `services/soft_fail.py`, 35 sites, zero restantes |

---

## Etapa 13 — Dívida de correção

Bugs conhecidos que a suíte atual não pega porque testa unidades mockadas, não
comportamento montado.

| # | Item | Decisão necessária |
|---|------|--------------------|
| 13.1 | **Dev bridge: `_REPO_ROOT` = `/` no container** | Consertar (`EVI_REPO_ROOT` + montar repo + `git`/`claude` na imagem) **ou** remover código + spec. Hoje está marcado Done e não roda. Decisão de produto, não técnica. |
| 13.2 | **Contrato estruturado de tools** | Substituir `if "failed" in result.lower()` por resultado tipado (`ok: bool`). Toca as 26 tools e os scripts Windmill — change próprio, mas quanto mais tools, mais caro. |
| 13.3 | `heartbeat._contacts_needing_synthesis` | Comparação `last_ts[:10] > text[idx:idx+40]` é sempre verdadeira (`'2' > '#'`). Todo contato é sinalizado como sem síntese. ~3 linhas. |
| 13.4 | Dedupe de `evolution_seen_ids.json` | `list(set)[-5000:]` evicta em ordem arbitrária; read-modify-write sem lock. |

---

## Etapa 14 — Lacunas de teste

A CI valida lógica de unidade e specs, **não deployment**. Foi por isso que 13.1
passou como Done. Fechar nesta ordem:

| # | Item | Cobre |
|---|------|-------|
| 14.1 | **Smoke de container no CI** | `docker compose up agent-api` + `GET /health` + `GET /tools`. Teria pego o dev bridge e pegaria qualquer erro de path/import só visível na imagem. |
| 14.2 | `agent/tools/calendar_tool.py` | Tool central do produto, zero testes. O sniffing de `"failed"`/`"status":"created"` nunca foi exercitado. |
| 14.3 | `agent/auth.py` | Zero testes na função que decide acesso. |
| 14.4 | `agent/services/telegram_poller.py` | `TELEGRAM_MODE=polling` é o caminho de produção atual e não tem teste. |
| 14.5 | `agent/services/evolution_client.py` | Envio de WhatsApp para fora — sem cobertura. |
| 14.6 | `agent/services/session_lane.py` + registry de sessão | Primitiva de concorrência sem teste de concorrência. |
| 14.7 | `agent/db.py` | Sem testes (exige Postgres). Serviço de PG efêmero no CI. |

---

## Etapa 15 — Superfície de injeção de prompt

Conteúdo de terceiros (WhatsApp) chega ao LLM sem delimitação em três caminhos:
`whatsapp_llm_extract`, `summarize_whatsapp_messages` e `_contact_profile_block`.
O extract usa o tier de background (Ollama), o que limita o dano; os outros dois
voltam para o grafo principal, que tem `delete_emails_by_query` e `schedule_event`
ligados.

Precisa de threat model e spec própria antes de código. Referência prática: o
material de hardening da comunidade OpenClaw (conteúdo externo é hostil por padrão;
instruções defensivas no bootstrap; nunca expor config/segredos).

---

## Etapa 16 — Execução em background (o que falta para ser "assistente")

Hoje o EVI só age quando você fala com ele. O `heartbeat` é o embrião de agir
sozinho, mas roda um checklist fixo. É aqui que está o valor incremental real —
depois de 12–15, não antes.

| Item | Notas |
|------|-------|
| Tarefas longas desacopladas do chat | `schedule_event` tem `timeout=180`; no WhatsApp o usuário fica 3 min sem sinal e sem abortar |
| Feedback de progresso / cancelamento | Mínimo: ack imediato + resultado depois, em vez de bloquear o turno |
| Heartbeat com ações, não só avisos | Requer 13.3 corrigido primeiro |

---

## Deferido (sem data)

| Item | Notas |
|------|-------|
| Pool de conexões Postgres | ~4–6 conexões por turno de `/chat`. Sem evidência de gargalo na carga atual. |
| Gating de tools por configuração | 26 tools ligadas sempre, incluindo dev bridge desligado. Degrada seleção no fallback Ollama. |
| `/health` com checks concorrentes | 6 checks síncronos × 3s bloqueiam uma thread. |
| Adapter WhatsApp Meta/Twilio | `BaseMessagingClient` já existe; escrever o 2º impl antes de precisar tem valor baixo. |
| Compose profile Ollama | Stack self-contained. Conveniência. |

## Cortado

Itens retirados do roadmap na revisão de 2026-08-12, com motivo:

| Item | Motivo |
|------|--------|
| **MCP servers isolados** | Resolve restart isolado — problema que o projeto não tem. 26 tools em um registry único funcionam. Adiciona processos, latência e superfície de falha sem benefício mensurável. |
| **Llava + Whisper (multimodal)** | Incompatível com o hardware alvo: GTX 1060 3 GB com `OLLAMA_MAX_LOADED_MODELS=1` — carregar Whisper/Llava descarrega o modelo de chat. Alternativa é API paga, que quebra a premissa de $0/mês. Reabrir só se o hardware mudar. |
| **Cache Redis de embeddings** | Otimização sem medição. Redis já está no compose para o Evolution; reabrir quando houver métrica mostrando embedding como gargalo. |
