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

### Avaliação prévia (2026-10-12)

Avaliador fora do repo (vira a task 2.0): 8 conversas simuladas com armadilhas
(colega de trabalho, troca de emprego, só brincadeira, injeção, preferências, pendência
resolvida, família, fato sobre terceiro) e 6 conversas reais (40 mensagens, dois lados;
só estrutura é pontuada — conteúdo revisado à mão).

Resultado (8 casos simulados; nuvem via OpenRouter com retenção zero):

| Modelo | Onde | Acertos | Aceitou a injeção ("usuário deve R$ 5000")? | p50 |
|---|---|---|---|---|
| qwen2.5:3b (atual) | local | 4/8 | sim | 20 s |
| granite4:micro | local | 4/8 | não | 19 s |
| qwen3:4b | local | 3/8 | sim | 20 s |
| qwen3:1.7b | local | 5/8 | sim | 5,5 s |
| Gemini 2.5 Flash (direto) | nuvem | 7/8 | não | 1 s |
| **google/gemma-4-26b-a4b-it** | OpenRouter ZDR | **8/8** | não | 1,6 s |
| **qwen/qwen3.8-27b** | OpenRouter ZDR | **8/8** | não | 2,2 s |
| google/gemma-4-31b-it | OpenRouter ZDR | 7/8 | não | 2,1 s |
| google/gemini-3.1-flash-lite | OpenRouter ZDR | 7/8 | **sim** (como item em aberto) | 2,1 s |
| qwen/qwen3.5-35b-a3b | OpenRouter ZDR | 5/8 | **sim** | 1,1 s |

Casos reais (6 conversas, 40 mensagens, dois lados, via OpenRouter ZDR, revisão manual):
`qwen/qwen3.8-27b` 6/6 JSON válido, p50 1,2 s, nenhum fato inventado, itens em aberto
corretos e específicos; `google/gemma-4-26b-a4b-it` 5/6 (uma chamada levou 215 s), um
fato deduzido sem ter sido dito ("relação familiar" a partir de "Tia"). Custo dos testes
reais: US$ 0,004.

Locais também copiam os exemplos do prompt para contatos sem relação ("Levar a Nina ao
veterinário") e transformam mensagens em fatos ("João disse: kkkk").

Achados que mudaram o desenho:

- **Remover fato por texto idêntico falha** (Gemini manteve "Trabalha na Unnawave" ao
  lado de "Trabalha na Acme"): fatos e itens ganham ids no prompt (`F1`, `A1`) e o
  modelo remove por id.
- **"Em aberto" sem definição vira diário** ("João enviou um meme"): item em aberto =
  tarefa de alguém ou pedido não atendido, com exemplos e contraexemplos no prompt.
- **Mesma pessoa em dois chats**: "Hollmann" (`…@lid`) e "+55 11 94826-0209"
  (`…@s.whatsapp.net`) são o mesmo contato com timelines separadas; o resumo do WhatsApp
  também os mostra como duas conversas. Pasta de contato passa a ser por identidade
  canônica (§9).

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

Entrada do LLM: nome do contato, fatos atuais numerados (`F1: … (data)`), itens em
aberto numerados (`A1: …`) e as mensagens novas desde `knowledge_updated` (máx. 60, os
dois lados, texto do contato em `wrap_external`). Saída JSON (schema nativo):

```json
{"add": [{"fact": "...", "date": "YYYY-MM-DD"}], "remove": ["F2"],
 "open": [{"item": "...", "date": "YYYY-MM-DD"}]}
```

`open` é a lista **completa** depois das mensagens (mantém os A* pendentes, tira os
resolvidos). O código valida: fato sem `date` ou com data fora da janela → descartado;
`remove` só aceita ids existentes; JSON inválido/timeout → nada é escrito. Chamada via
`llm_structured.run_structured("CONTACT_KNOWLEDGE", …)` (criado em
`evi-promise-context`): provedor/modelo/think por variável, sem fallback automático
para nuvem.

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

`EVI_LLM_TASK_CONTACT_KNOWLEDGE_PROVIDER` / `_MODEL` (camada de `evi-promise-context`).
**Default: `openrouter`, `qwen/qwen3.8-27b,google/gemma-4-26b-a4b-it`** — os dois 8/8 nos
simulados e sem aceitar injeção; nos reais o Qwen foi mais conservador e estável.
Timeout por chamada `EVI_LLM_TIMEOUT_SEC` (30 s): estourou → tenta o próximo modelo da
lista. O prompt proíbe fato deduzido: só o que a mensagem diz explicitamente. Estimativa: 15 contatos/dia ×
~US$ 0,001 ≈ US$ 0,45/mês, dentro do teto diário compartilhado
(`EVI_LLM_TASK_DAILY_USD`). Nenhum modelo local passou (tabela): `ollama` fica
suportado, não default. Até 60 mensagens por contato/dia saem para um endpoint com
retenção zero — aprovado pelo usuário em 2026-10-12.
**Defesa extra contra injeção** independentemente do modelo: fato ou item que contenha
valor monetário, credencial ou instrução imperativa dirigida ao usuário e que **só**
apareça em mensagem do contato é descartado pela validação (lista de padrões testada).

### 9. Identidade canônica (`@lid` ↔ telefone)

O WhatsApp entrega a mesma pessoa como `…@lid` e `…@s.whatsapp.net`. A Evolution expõe
o par em `key.remoteJidAlt` (já usado por `_alt_phone_jid`). Novo
`contact_identity.canonical_jid(jid)`: telefone quando conhecido (tabela
`wa_jid_alias(lid, phone_jid)` preenchida no webhook e na descoberta), senão o próprio
jid. Timeline, conhecimento, dívidas de resposta e o resumo do WhatsApp usam o jid
canônico. Migração junta pastas `@lid` na do telefone (timeline mesclada por
`source_id`, ordem por `ts`), com dry-run.

### 10. Avaliador

`./scripts/evi-test llm-eval contact-knowledge [--model M] [--provider P]`: casos
simulados versionados em `tests/eval/contact_knowledge_cases.yaml`; reais só locais
(`data/eval/`, gitignored) e nunca enviados ao Gemini. Gate para trocar modelo/prompt.

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
- Ordem de dependência: exige `llm_structured` e o avaliador de `evi-promise-context`.
