## Why

Estudo é uma das três coisas da semana do usuário (graduação e mestrado, ambos com aulas). Hoje
só existe a tarefa "do mestrado" no Google Tasks. As grades variam muito entre disciplinas e
semestres, e os materiais chegam por canais diferentes. Decisões de 20/10
(`docs/drafts/brainstorm-assistente-2026-10-20.md` §12):
- **grade em CSV padronizado**, uma linha por encontro;
- **material enviado manualmente pelo Telegram**;
- **resumo só quando o usuário tocar [resumo]**, o que fica para `evi-study-summaries`.
Este change entrega a parte **sem LLM**: grade, agenda, material associado à aula e o dia de
aula no briefing.

## What Changes

- **Importar a grade por CSV** (`disciplina;data;inicio;fim;descricao;tipo;local;curso`) enviado
  no Telegram. Aceita `;` ou `,` e datas `DD/MM/AAAA` ou ISO. Validação por linha e resumo antes de
  publicar. Só publica com ✅. Reimportar é idempotente (chave `disciplina+data+inicio`) e pergunta
  antes de remover. `/grade modelo` devolve o exemplo.
- **Agenda "Estudos"** no Google Calendar (escolhida pelo nome) recebe as aulas. Novos scripts
  Windmill `update_event`/`delete_event`. A fonte de verdade local é a tabela `study_sessions`.
- **Material pelo Telegram**: documento ou foto → associação à aula pela grade (sem legenda: hoje
  ou a mais próxima em ±3 dias; legenda `disciplina [DD/MM] [tipo]`) com ✅ / outra aula / outra
  disciplina / não é de estudo. Salvo em `watched_folders/estudos/<curso>/<disciplina>/<data>/`,
  com dedupe por hash. Texto de PDF/DOCX/PPTX indexado no RAG com disciplina e data.
- **Briefing**: linha "📚 19h Metodologia — tema" nos dias de aula, com o material já recebido.
  Prova e entrega viram lembretes (7 dias e 1 dia antes). `/estudos` lista as disciplinas e as
  aulas sem material.

## Impact

Novo: `agent/services/study.py`, `agent/services/study_csv.py`,
`windmill/f/integrations/{update_event,delete_event}.*`. Alterado: `agent/db.py`,
`agent/services/telegram_handler.py` (documentos), `agent/services/briefing.py`,
`agent/services/chat_commands.py`, `agent/tools/rag_tool.py` (metadados),
`agent/requirements.txt` (`python-docx`, `python-pptx`). Spec: `tools-productivity`. Sem
container novo; **sem LLM**. O embedding do RAG usa o provedor configurado (padrão Ollama local).

## Validação em uso real

Janela de 4 semanas: grade importada e publicada sem correção manual na agenda; ≥ 50 % das aulas
com material associado; 0 material associado à aula errada sem o usuário corrigir.

## Out of scope

- Resumos, perguntas, plano de ensino → prazos, revisão (`evi-study-summaries`, LLM sob demanda).
- Integração com Moodle/Classroom; ingestão do grupo da turma.
- Arquivos acima de 20 MB pelo Telegram (avisar e usar a pasta).
