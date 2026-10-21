## Context

- Telegram: só voz é baixada hoje (`telegram_handler` l. ~165 com `telegram_poller.get_file_path` +
  `download_file`); documento e foto não são tratados. A Bot API baixa até 20 MB.
- Calendar via Windmill: `schedule_event` (cria, aceita `calendar_id`), `list_events`,
  `list_calendars`. **Não há** atualizar/apagar evento.
- RAG: `rag_tool.ingest_university_pdf` (PyMuPDF, chunks de 512, Qdrant, embeddings de
  `llm.build_embeddings`, padrão Ollama `nomic-embed-text`).
- Lembretes: `services/reminders.py` + loop in-process. Briefing: `briefing.assemble_briefing`
  monta as seções. Mount do host: `./watched_folders:/watched_folders`.
- Confirmação por botão: padrão `callback_data` do briefing (`b1:`) e da política (`p1:`).

## Decisions

### 1. CSV
`study_csv.parse(text) -> (rows, errors)`. Delimitador detectado (`;` ou `,`), UTF-8 com/sem BOM.
Colunas obrigatórias `disciplina`, `data`; `inicio`/`fim` obrigatórios para `aula`/`prova`.
Colunas extras são ignoradas com aviso. `tipo` ∈ `aula, prova, entrega, seminario, sem_aula`
(padrão `aula`) e `curso` ∈ `graduacao, mestrado` (opcional). Erros: data inválida, `fim ≤ inicio`,
duplicata da chave, `sem_aula` sem aula correspondente (aviso). A chave estável é
`sha1(disciplina normalizada + data + inicio)`.

### 2. Importar e publicar
1. CSV recebido (documento `.csv`) → `parse` → relatório:
   "3 disciplinas, 41 aulas, 2 provas, 3 entregas, 1 sem aula · 2 erros (linhas 7, 19) · choques
   com a agenda: 1". Os choques são consultados uma vez com `list_events` no intervalo.
2. Botões ✅ publicar / ✖. Com erros, publica só as linhas válidas e diz quais ficaram de fora.
3. Diff contra `study_sessions`: cria, atualiza (campos mudaram) e **pergunta** antes de remover
   linhas que sumiram ("5 encontros não estão mais no CSV — remover da agenda?").
4. Eventos na agenda cujo nome contém "Estudos" (via `list_calendars`). Se não existir, pede ao
   usuário para criá-la (o EVI não cria agendas: menos escopo de OAuth). O id do evento é
   guardado em `study_sessions.gcal_event_id`, e a chave vai na descrição do evento.
5. `sem_aula` remove o evento daquela data. `prova`/`entrega` criam lembretes 7 d e 1 d antes
   (09:00) via `reminders`.

Tabela `study_sessions(key pk, discipline, course, date, start_time, end_time, kind, description,
location, gcal_event_id, updated_at)`.

### 3. Windmill
`update_event(calendar_id, event_id, fields)` e `delete_event(calendar_id, event_id)`, com o mesmo
padrão e envelope de `schedule_event`; operações no `integrations/windmill.py`; fakes da simulação.

### 4. Material
Documento ou foto no chat do usuário (não `.csv`) → baixa (≤ 20 MB; acima, avisa e sugere a pasta)
→ `sha256` (já existe → oferece só reassociar). Associação:
- legenda vazia: aula de hoje; senão a mais próxima em ±3 dias (anterior preferida); senão "qual
  disciplina?" com botões das disciplinas;
- legenda `disciplina [DD/MM] [tipo]`: casamento por prefixo/apelido (sem acento, minúsculas);
- tipo ∈ `aula` (padrão), `leitura`, `plano`, `enunciado`, `anotacao`.

A confirmação traz botões ✅ · outra aula · outra disciplina · não é de estudo. Com ✅, o arquivo
vai para `/watched_folders/estudos/<curso>/<disciplina>/<AAAA-MM-DD>/<nome>` e é gravado em
`study_material(hash pk, session_key, discipline, kind, path, original_name, received_at)`.
Extração de texto: PDF (PyMuPDF), DOCX (`python-docx`), PPTX (`python-pptx`); imagem e outros são
só guardados. O texto vai ao Qdrant (coleção da universidade) com metadados `discipline`,
`session_date`, `kind`. `plano` e `enunciado` só ficam marcados: transformar em prazo é
`evi-study-summaries`. Um álbum (vários arquivos) recebe uma confirmação só.

### 5. Briefing e comandos
- Manhã, dia com aula: "📚 19:00 Metodologia — Revisão bibliográfica · 2 materiais" (sem material:
  "sem material ainda"). Vem antes das dívidas e conta no teto de linhas.
- `/estudos`: por disciplina, as próximas aulas e quantas das passadas estão sem material.
- `/grade modelo`: envia o CSV de exemplo como documento.

### 6. Sem LLM
Parse, associação, briefing e comandos são determinísticos. O único custo externo é o embedding
(local por padrão) e as chamadas Windmill ao Google.

## Riscos

- **CSV mal formatado**: o relatório por linha + publicação parcial evitam importar lixo.
- **Associação errada**: sempre confirmada; "outra aula" corrige.
- **Agenda errada**: o EVI só mexe em eventos com a chave na descrição e na agenda "Estudos".

## Out of scope

Resumos e LLM; Moodle/Classroom; grupo da turma; criar agenda; arquivos > 20 MB pelo Telegram.

## RAM

Sem container novo. `python-docx`/`python-pptx` são puros Python (poucos MB).
