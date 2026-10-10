## Ciclo

```
 uso real ──► turn_log + sinais ──► relatório semanal ──► turnos para revisar
    ▲                                                          │
    │                                              evi-sim promote <turn_id>
    │                                                          ▼
 deploy ◄── evi-sim (L2) aprova ◄── cenário anonimizado em tests/sim/scenarios/from-usage/
```

Cada falha real vira teste de regressão no nível que simula o uso real. É isso que
mantém a simulação fiel ao longo do tempo.

## `turn_log`

```sql
CREATE TABLE IF NOT EXISTS turn_log (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  session_id VARCHAR(128) NOT NULL,
  channel VARCHAR(16) NOT NULL,          -- telegram | whatsapp_control | api | job
  user_text TEXT NOT NULL,
  reply_text TEXT,                        -- truncado em 2000
  tools JSONB NOT NULL DEFAULT '[]',      -- [{name, ok, reason, ms}]
  latency_ms INTEGER,
  llm_calls INTEGER,
  error TEXT,
  is_test BOOLEAN NOT NULL DEFAULT false,
  feedback VARCHAR(8),                    -- bom | ruim
  feedback_note TEXT,
  signals JSONB NOT NULL DEFAULT '{}'     -- preenchido pelo job noturno
);
CREATE INDEX IF NOT EXISTS turn_log_ts ON turn_log (ts);
```

Ponto único de gravação: o handler de `/chat` em `agent/main.py`, por onde passam
Telegram e o canal de controle do WhatsApp. Gravação em `soft_fail` — falha de log
nunca derruba um turno.

### Resultado estruturado das tools

As tools devolvem `str` ao LangChain (decisão do #34). Para não mudar isso,
`parse_windmill_result` passa a registrar `{name, ok, reason}` num `ContextVar`
de coleta por turno, aberto pelo handler de `/chat`. Tools sem Windmill
(notas, contatos, RAG) entram com `ok: null` — desconhecido, não sucesso.

### `is_test`

`true` quando `session_id` começa com `evi-test`, `test-`, `health-check`, `tg-digest-verify`
ou a requisição traz `X-Evi-Test: 1`. Os harnesses (`evi-test`, verify scripts) passam
a enviar o cabeçalho.

## Sinais

| Sinal | Regra | Peso no "turno com sucesso" |
|---|---|---|
| `tool_failed` | alguma tool com `ok=false` | falha |
| `correction` | próximo turno da sessão em ≤ 3 min começa com/contém padrão de correção (`não`, `errado`, `não era`, `na verdade`, `não é isso`) | falha |
| `rephrase` | próximo turno em ≤ 3 min com similaridade de tokens ≥ 0,6 com este | falha |
| `cant_do` | resposta contém "não consigo"/"não tenho acesso"/"não posso" | falha |
| `feedback=ruim` | `/ruim` | falha |
| `feedback=bom` | `/bom` | sucesso forte |

Turno com sucesso = nenhum sinal de falha. Os padrões ficam em uma lista
versionada e testada; o relatório mostra quantos turnos cada regra marcou, para
calibrar falsos positivos.

## Relatório semanal

`POST /jobs/usage-report` (segunda 00:30 via Windmill, semana que acabou de fechar; período = semana ISO que contém agora−6 dias, fuso EVI_TIMEZONE).

| KPI | Fonte |
|---|---|
| Dias ativos (≥ 1 turno não-teste) | `turn_log` |
| Turnos, por canal | `turn_log` |
| Taxa de sucesso por turno | sinais |
| Falhas por tool e `reason` | `tools` |
| Taxa de correção/reformulação | sinais |
| Latência p50/p95 | `latency_ms` |
| Chamadas ao LLM por turno | `llm_calls` |
| Compromissos: confirmados/dispensados/pendentes | `pending_commitments` (sem `source='evi-test'`) |
| Sonda: dias com falha, por integração | `probe_log` |

Cada KPI com Δ contra a semana anterior e contra a **linha de base** (primeiras 2
semanas após o deploy deste change). Seção final: até 5 turnos para revisar
(prioridade: `ruim` > `tool_failed` > `correction` > `rephrase`), com id para
`evi-sim promote`.

Saída: `EVI_WORKSPACE/reports/usage-YYYY-Www.md` (adicionado ao `.gitignore` — contém
texto de conversas) + resumo de ≤ 10 linhas no Telegram.

## Sonda somente-leitura

`POST /jobs/probe` (diário, 06:30 — antes do briefing): `list_events` de hoje,
`list_tasks(max=1)`, `summarize_inbox(max=1)`, `getMe` do Telegram. Chamadas diretas
pela integração (sem LLM). Resultado em `probe_log(day, check, ok, reason, ms)`.
Falha → uma mensagem por dia por integração no Telegram, com o motivo e, para
`reason=oauth`, o caminho de reconexão no Windmill.

## Do uso real para a simulação

`./scripts/evi-sim promote <turn_id>`:
1. lê o turno, o anterior e o seguinte da sessão;
2. anonimiza com mapeamento estável por execução: nomes de contato → nomes fictícios,
   telefones → `+55 11 90000-00NN`, e-mails → `pessoaN@exemplo.com`;
3. grava `tests/sim/scenarios/from-usage/<data>-<id>.yaml` com `seed` mínimo,
   o passo `telegram:` e `expect: {}  # TODO: preencher` — a expectativa é decisão
   humana, nunca inferida;
4. o runner recusa cenário com `TODO` em `expect`.

Captura de formato do Evolution: no webhook, calcular a assinatura (conjunto
ordenado de caminhos de chaves) do payload; assinatura nova → gravar o payload com
todos os valores de texto substituídos em `data/payload_shapes/<hash>.json`. O
relatório semanal lista assinaturas novas para virarem fixture do fake Evolution.

## Regra de processo

`openspec/config.yaml` ganha, em `rules.proposal`:
"Mudança de comportamento observável declara `## Validação em uso real` com KPI,
limiar e janela (padrão 7 dias). Arquivar não espera a janela; o resultado é
registrado no BACKLOG quando a janela fecha."

## RAM

Nenhum container novo. `turn_log` cresce ~1 KB por turno — trivial no volume atual;
retenção de 180 dias pelo `log_retention` existente.

## Out of scope

Ver `proposal.md`.

## As-built (2026-10-10)

- Gravação em `_run_chat` (`agent/main.py`), não só na rota HTTP: Telegram chama `chat()`
  direto e o controle WhatsApp ganhou `_whatsapp_control_invoke_chat`. `channel=job` não é
  gravado.
- Coletor = callback LangChain mutável num `ContextVar` (sobrevive ao salto de thread do
  `ToolNode`); conta chamadas ao LLM e mede `ms` de cada tool. `parse_windmill_result(tool=...)`
  nas tools Windmill; `list_tasks` entra com `ok: null`.
- `/jobs/usage-signals` (diário) + retenção de 180 dias (`log_retention` só tratava arquivos).
- Relatório: semana ISO local que contém `agora − 6 dias`; agendado **segunda 00:30**.
  Linha de base persistida em `EVI_WORKSPACE/reports/baseline.json` (o prune a deslocaria).
- Sonda: aviso diário reivindicado atomicamente (`probe_notified`, PK `(day, check_name)`),
  liberado se o envio falhar.
- Formatos do Evolution em `./data/payload_shapes` (montado no compose).
- Testes que escrevem no banco exigem `EVI_TEST_EPHEMERAL_DB=1` (CI) e só tocam os próprios ids.
