## Context

As-built (`evi-contact-learning`, `evi-small-correctness`):

| Peça | Comportamento atual | Problema |
|---|---|---|
| `timeline.jsonl` | gravada em `process_messages`, depois do filtro `EVI_WHATSAPP_INCOMING_ONLY=true` | só mensagens recebidas |
| `learn_contact(label)` | contexto = timeline + resumos + compromissos + **perfil inteiro** → síntese livre | metadado (`created`) vira fato; resolve por nome (ambíguo com homônimos) |
| `append_profile_section` | heading `Síntese (YYYY-MM-DD, …)` novo a cada dia | arquivo só cresce; sínteses contraditórias convivem |
| `read_profile_excerpt(jid, n)` | `text[:n]` | consumidores veem cabeçalho + síntese **mais antiga** |
| `run_contact_learn_batch` | percorre `collect_known_contacts()` (até ~3000) na ordem do registro, `limit=10` | sem agendamento; ordem não prioriza quem falou por último |
| `ensure_contact` | cria pasta para qualquer jid | canais (`@newsletter`) ganham perfil |
| LLM | `build_background_llm` → Ollama `qwen2.5:3b` | modelo pequeno + texto livre = alucinação |

## Decisions

### 1. Timeline com os dois lados

`reply_debts.track_conversation` já vê toda mensagem direta, inclusive `fromMe`, antes do
filtro. Ali passa a chamar `message_timeline.record_whatsapp_message(msg)` também para
`fromMe` (o `_preview` já produz `[eu] …`; dedupe por `source_id` já existe). Nada muda na
extração: `fromMe` continua filtrado antes de `extract_commitment`.

### 2. Formato do `profile.md`

```markdown
# Contact memory
- **jid**: …            ← metadado, nunca vai ao LLM
- **label**: …
- **created**: …

## Fatos
- Trabalha na Unnawave com o usuário (2026-10-07)
- Prefere ser chamado de Fê (2026-09-30)

## Em aberto
- Usuário vai mandar a modelagem quando terminar (2026-10-11)

## Notas
(livre, do usuário; o EVI nunca escreve aqui)
```

Escrita por `contact_knowledge.write_knowledge(jid, facts, open_items)`, que substitui só
`## Fatos` e `## Em aberto`. Teto: 15 fatos, 5 itens em aberto.

### 3. Atualização incremental com saída estruturada

Entrada do LLM: nome do contato, fatos atuais, itens em aberto atuais e as mensagens
novas desde `updated_at` (máx. 60, os dois lados, `wrap_external`). Saída JSON:

```json
{"add": [{"fact": "...", "date": "YYYY-MM-DD"}], "remove": ["<fato existente>"],
 "open": [{"item": "...", "date": "YYYY-MM-DD"}]}
```

O código valida: fato sem `date` ou com data fora da janela de mensagens → descartado;
`remove` só aceita texto idêntico a um fato atual; JSON inválido → nada é escrito (o perfil
anterior fica). `temperature=0`. Saída estruturada pequena é o que um modelo 3B faz bem;
síntese narrativa livre não.

`updated_at` fica numa linha de metadado do cabeçalho (`- **knowledge_updated**: …`).

### 4. Leitura

`read_contact_knowledge(jid, max_chars=1200) -> str`: `## Fatos` + `## Em aberto` +
`## Notas`, nesta ordem, sem cabeçalho. Substitui `read_profile_excerpt` em
`contact_tool.get_contact_info`, `whatsapp_llm_extract._contact_context` e preenche o
parâmetro `knowledge` de `promise_context.conversation_context`.

### 5. Lote e agendamento

`run_contact_learn_batch` passa a: listar pastas de contato (não o registro inteiro),
selecionar as com entrada de timeline mais nova que `knowledge_updated`, ordenar pela
mais recente, `limit=15` por execução, chamar por **jid** (não por nome). Agendamento
diário 03:30 no Windmill (`f/integrations/contact_learn`), antes do briefing de 07:00.
Schedules vivem na UI: a task inclui o `schedule.yaml` se o `wmill sync` do repo
suportar, senão o passo manual documentado em `docs/` e confirmado pelo usuário.

### 6. Pastas só para conversas diretas

`ensure_contact` recusa `@g.us`, `@newsletter`, `@broadcast` (usa
`reply_debts.is_one_way_jid`). Pastas existentes desses jids ficam (sem apagar dados);
o lote as ignora.

### 7. Migração

`./scripts/evi-test contact-knowledge-migrate` (dry-run por padrão, `--apply`): move
toda seção `## Síntese (…)` de `profile.md` para `history.md` na mesma pasta, intacta.
Não gera fatos a partir dela (as sínteses atuais não são confiáveis).

### 8. Modelo

Padrão: `build_background_llm` (Ollama local) — mensagens de terceiros não saem da
máquina. `EVI_CONTACT_KNOWLEDGE_PROVIDER` permite trocar (ex.: `gemini`) se a auditoria
da janela de validação mostrar qualidade insuficiente; a troca é decisão do usuário,
porque manda conversas para fora.

## Riscos

- **Privacidade**: fatos sobre terceiros em disco local (já é o caso hoje com a timeline);
  nada sai da máquina com o provedor padrão. `data/` continua fora do git.
- **RAM/GPU**: Ollama já carregado (`OLLAMA_MAX_LOADED_MODELS=1`); 15 contatos/dia às
  03:30, fora do horário de uso. Sem container novo.
- **Fato errado persistente**: mitigado por evidência obrigatória, `remove` explícito e
  `## Notas` como canal do usuário; auditoria na janela de validação.
- **Timeline maior**: ~2× linhas por contato com `fromMe`; arquivos jsonl pequenos.

## Out of scope

- Graphiti/Neo4j, embeddings, participantes de grupos, edição de fatos pelo chat,
  remoção do `profile_updater`.
