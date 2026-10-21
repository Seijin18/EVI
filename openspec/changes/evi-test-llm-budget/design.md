## Context

- Cassete = `tests/sim/cassettes/<id>.jsonl`, linhas `{key, prompt_tail, response}`. A chave é o
  sha256 da requisição normalizada (`request_key` no chat, `structured_key` nas chamadas
  estruturadas). Uma chave repetida é servida na ordem gravada.
- O modo é do container: `scripts/evi-sim` exporta `EVI_SIM_LLM_PROVIDER` (`gemini`,
  `sim-record`, `sim-replay`) e `up` recria o `agent-api` quando muda. O runner anuncia o cenário
  ativo por `ctl` (nonce por tentativa) e, em replay, copia o cassete para dentro do container.
- `record` regrava a cada tentativa e guarda a última **aprovada**.
- `llm_counter` conta toda chamada de chat-model (inclusive o wrapper do cassete), mas só registra
  tokens de chamadas reais (`/tmp/evi-sim-llm-usage`).
- `llm-eval` (5 harnesses) chama `services.llm_structured.run_structured` por atributo do módulo
  em cada caso.

## Decisions

### 1. Provedor `sim-fill`
`build_sim_llm("sim-fill")` = `SimCassetteChatModel(inner=gemini, fill=True)`. No `_sync` do
modo fill, o cassete enviado é carregado em memória (`entries`) e o arquivo é zerado. Em cada
chamada:
- `try_lookup(key)` acha → devolve a resposta gravada e **copia** a linha para o arquivo novo;
- não acha (chave nova ou usada mais vezes que o gravado) → chama o modelo real e grava a linha.

Ao fim, o arquivo tem exatamente as chamadas usadas, na ordem, sem chaves mortas. Chamadas
estruturadas: `llm_structured._sim_cassette_mode()` mapeia `sim-fill` → `"fill"`, e
`structured_call("fill", …)` faz o mesmo (servir ou chamar e gravar). Falha do provedor não é
gravada, como no record.

### 2. Repetição sem reaproveitar o que acabou de ser gravado
O runner lê o cassete do host **uma vez no início do run** (snapshot por cenário) e envia esse
original em toda tentativa do modo fill. Assim, com `--repeat 3`, as chamadas que mudaram vão ao
vivo 3 vezes (a não-determinância é medida onde importa) e as que não mudaram são servidas.
A tentativa aprovada sobrescreve o cassete no host, como no record. Cenário sem cassete =
snapshot vazio = tudo ao vivo (cenário novo).

Por que confiar na resposta servida: a requisição é idêntica, byte a byte depois da normalização,
à que foi aprovada quando o cassete foi gravado. Uma resposta servida é uma amostra válida do
modelo, já verificada. Uma chamada servida só muda se o prompt, a tool ou a conversa anterior
mudarem, e nesse caso a chave muda e a chamada vai ao vivo.

### 3. Contagem
O contador ganha um tipo de linha `served` (o wrapper registra quando serviu do cassete). O
relatório mostra `LLM calls: real R · served S · tokens in/out` por tentativa e no total; o
`--max-llm-calls` conta só chamadas **reais**. Em `replay` todas são servidas.

### 4. Cache do `llm-eval`
`testing/llm_eval/cache.py`: um context manager substitui `llm_structured.run_structured`
durante `run_llm_eval`. Chave = sha256(tarefa, provedor, modelos, prompt, schema); valor = lista
de amostras. A i-ésima chamada da mesma chave **nesta execução** usa a amostra i, se existir;
senão chama o real e acrescenta. Com `--repeat N` isso dá N amostras distintas, reaproveitadas na
próxima execução. Arquivo `data/eval/cache.jsonl` (`data/` já é gitignored; pode conter casos
reais). `--no-cache` ou `EVI_LLM_EVAL_CACHE=0` desliga. Falhas (`None`) não entram no cache. O
custo reportado pelo harness continua vindo do gasto real (0 para amostras do cache).

### 5. Regra de verificação
- Verify de task de comportamento: `./scripts/evi-sim run --id <SIM-…> --repeat 3 --llm fill`
  (substitui `live` + `record`).
- Fechamento de change: `./scripts/evi-sim run --tag critical --repeat 3 --llm fill` e
  `--llm replay` (o que a CI roda).
- `--llm live` completo: só checagem de deriva do modelo (ex.: mensal ou ao trocar a versão do
  Gemini), documentada em `docs/testing.md`.
- `llm-eval`: com cache por padrão; `--no-cache` ao trocar de modelo ou em checagem de deriva.

## Riscos

- **Deriva do modelo** não aparece em chamadas servidas: mitigado pela checagem periódica `live`.
- **Ordem de chaves repetidas**: a cópia preserva a ordem de uso; uma chave usada mais vezes que o
  gravado vai ao vivo na vez excedente (mesma semântica do stale do replay).
- **Cache do eval com casos reais**: fica em `data/` (fora do git), como os casos reais.

## Out of scope

Critério de aprovação; modelos; cache em produção; CI (continua `replay`, sem chave).
