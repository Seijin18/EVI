## 1. Grade

- [ ] 1.1 `study_csv.parse` (delimitador, datas, tipos, erros por linha, chave estável) + `/grade modelo`
  - SCN-STUDY-01
  - Files: `agent/services/study_csv.py`, `tests/unit/test_study_csv.py`, `tests/fixtures/study/grade_exemplo.csv`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_study_csv.py -q`

- [ ] 1.2 Tabelas `study_sessions` e `study_material`; diff de reimportação (criar/atualizar/remover com pergunta)
  - SCN-STUDY-02
  - Files: `agent/db.py`, `agent/services/study.py`, `tests/unit/test_study.py`, `tests/unit/test_db.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_study.py tests/unit/test_db.py -q`

- [ ] 1.3 Scripts Windmill `update_event` e `delete_event` + operações no integration + fakes da simulação
  - SCN-STUDY-02
  - Files: `windmill/f/integrations/update_event.py`, `windmill/f/integrations/delete_event.py`, `agent/integrations/windmill.py`, `agent/testing/sim/fake_google.py`, `tests/unit/test_sim_fake_windmill.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_fake_windmill.py -q` e `./scripts/evi-test calendar`

- [ ] 1.4 Fluxo no Telegram: `.csv` recebido → relatório + choques → ✅ publica na agenda "Estudos" → lembretes de prova/entrega
  - SCN-STUDY-01, SCN-STUDY-02, SCN-STUDY-03
  - Files: `agent/services/telegram_handler.py`, `agent/services/study.py`, `agent/services/reminders.py`, `tests/unit/test_study.py`, `tests/unit/test_telegram_handler.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_study.py tests/unit/test_telegram_handler.py -q`

## 2. Material

- [ ] 2.1 Documento/foto do Telegram: download (≤ 20 MB), hash, associação à aula pela grade/legenda, confirmação com botões, gravação em `watched_folders/estudos/...`
  - SCN-STUDY-04, SCN-STUDY-05
  - Files: `agent/services/telegram_handler.py`, `agent/services/study.py`, `agent/services/telegram_poller.py`, `tests/unit/test_study.py`, `tests/unit/test_telegram_handler.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_study.py tests/unit/test_telegram_handler.py -q`

- [ ] 2.2 Extração de texto (PDF/DOCX/PPTX) e indexação no RAG com metadados de disciplina/data/tipo
  - SCN-STUDY-06
  - Files: `agent/tools/rag_tool.py`, `agent/services/study.py`, `agent/requirements.txt`, `tests/unit/test_study.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_study.py -q` e `./scripts/evi-test rag`

## 3. Briefing, comandos e fechamento

- [ ] 3.1 Linha "📚" no briefing da manhã em dia de aula; `/estudos`; `/ajuda`
  - SCN-STUDY-07
  - Files: `agent/services/briefing.py`, `agent/services/chat_commands.py`, `tests/unit/test_briefing.py`, `tests/unit/test_chat_commands.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py tests/unit/test_chat_commands.py -q` e `./scripts/evi-test briefing`

- [ ] 3.2 Revisão leve de segurança (novo canal de entrada: arquivos do Telegram; escrita em disco; novos scripts de agenda)
  - SCN-STUDY-04
  - Files: `docs/security/threat-model.md`, `docs/security/findings.md`
  - Verify: `./scripts/evi-security-scan`

- [ ] 3.3 Cenários `SIM-STUDY-01` (CSV → publicar → briefing do dia) e `SIM-STUDY-02` (PDF sem legenda → aula de hoje → ✅ → `/estudos`)
  - SCN-STUDY-01, SCN-STUDY-04, SCN-STUDY-07
  - Files: `tests/sim/scenarios/study/`, `tests/sim/cassettes/`, `agent/testing/sim/schema.py`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag study --repeat 3 --llm fill` e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.4 Gates, docs (`docs/testing.md`, README de estudos), BACKLOG + Progress
  - SCN-STUDY-01
  - Files: `openspec/BACKLOG.md`, `Progress.md`, `README.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `./scripts/evi-sim run --tag critical --repeat 3 --llm fill`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
