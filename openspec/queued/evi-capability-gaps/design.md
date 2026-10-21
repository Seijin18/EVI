## Context

- `usage_signals.py` já marca `cant_do` (padrões de "não consigo…" na resposta), `correction`,
  `rephrase` e `tool_failed` por turno. `usage_report.generate_report` monta o relatório semanal
  (Telegram + markdown).
- `turn_log` guarda texto do usuário, resposta truncada, tools com `ok`/`reason` e feedback.
- Tools: registro único `tools/registry.get_all_tools()`. Allowlist por origem do turno em
  `write_guard` (turno disparado por conteúdo externo não tem tools de escrita).
- Anonimização: `testing/sim/promote.py` (`anonymize`) troca nomes, números e e-mails.

## Decisions

### 1. Tool e prompt
`report_capability_gap(request: str, missing: str, workaround: str = "") -> str` grava ou
incrementa a lacuna e devolve `#N` para o modelo citar. Regra nova no `SYSTEM_PROMPT`: "Se o
pedido exige algo que nenhuma tool faz, NÃO afirme limitação inventada nem peça para dividir o
pedido: chame `report_capability_gap` e responda que ainda não sabe, citando #N e um contorno se
houver." A tool é **interna**: entra na allowlist dos turnos do usuário (Telegram, controle,
`/chat`) e dos agendados, e é negada em turnos disparados por conteúdo externo, para que um
e-mail não encha o registro.

### 2. Registro
`capability_gaps(id serial, title, missing, workaround, example_anon, source text check in
('tool','implicit'), status text check in ('open','important','dismissed','exported','done',
'policy_refused'), count int, first_seen, last_seen, norm_key)`.
- `norm_key`: `missing` normalizado (minúsculas, sem acento, sem stopwords, tokens ordenados).
- Dedupe: Jaccard ≥ 0,6 entre os conjuntos de tokens de lacunas `open`/`important` → incrementa
  `count`; senão cria. Sem embeddings: 0 custo e determinístico.
- `example_anon` = pedido do usuário anonimizado (`promote.anonymize`), até 200 caracteres.
- Espelho `EVI_WORKSPACE/gaps/<id>.md` (título, contagem, exemplos, status), reescrito a cada
  mudança.
- `policy_refused`: `missing` que cai em lista fixa (pagar/transferir, enviar a terceiro sem
  aprovação, apagar sem confirmação, criar conta) vira esse status, nunca `open`.

### 3. Implícitos
O job diário de sinais (`usage_signals`) cria candidatos `source=implicit` para turnos com
`cant_do`, ou `ruim`/👎 + `tool_failed`, **quando o turno não chamou a tool** (evita contar
duas vezes). `missing` = texto do usuário anonimizado. Esses candidatos só aparecem no relatório
com `count ≥ 2` ou `important`.

### 4. Relatório e comandos
- Seção semanal "🧩 Pedidos que eu ainda não sei atender" (até 3, por `count` e `last_seen`),
  com botões ⭐ (important) / ✖ (dismissed), prefixo `g1:`.
- `/melhorias`: lista numerada; "importante N", "descarta N".

### 5. Exportar
`./scripts/evi-test gaps-export <id> [--slug x]` (roda no host, lê o Postgres) escreve
`openspec/proposals-inbox/<slug>/proposal.md` com `## Why` (contagem, exemplos anonimizados,
datas), `## What Changes` (TODO), `## Out of scope` (TODO) e marca `exported`. **Não** escreve
em `changes/` ou `queued/`. `openspec/proposals-inbox/README.md` explica o fluxo.

## Riscos

- **Modelo não chama a tool**: o cenário de simulação cobre o caso real (tarefas com exceção
  antes do fix virou corpus) e o sinal `cant_do` cobre o resto.
- **Ruído**: limiar `count ≥ 2` ou ⭐; descartados não voltam ao relatório.
- **Privacidade**: só exemplos anonimizados saem do Postgres para arquivos.

## Out of scope

Texto gerado por LLM; implementação automática; e-mail de lacunas.

## RAM

Sem container novo.
