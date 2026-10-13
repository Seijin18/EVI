## 1. Contenção

- [x] 1.1 F1 (hotfix aplicado em 2026-10-12, ver design §1): `agent-api` em `127.0.0.1:8002`, `EVI_API_KEY` gerado + `EVI_REQUIRE_API_KEY=true`, chave na variável secreta do Windmill; decidir com o usuário o acesso remoto (Tailscale + chave)
  - SCN-AUTH-01, SCN-SEC-01
  - Files: `docker-compose.yml`, `.env.example`, `windmill/README.md`, `docs/security/findings.md`
  - Verify: `./scripts/evi-container-smoke.sh` e, de outra máquina da rede, `curl -s -o /dev/null -w '%{http_code}' http://192.168.15.32:8002/health` não responde

- [x] 1.2 (aplicado 2026-10-13, sessão WhatsApp seguiu `open`; Verify de 24 h vira pendência) Desligar o webhook global da Evolution (`WEBHOOK_GLOBAL_ENABLED=false`): sem cabeçalho de chave, ele só gera 401 (eventos de contato/presença) e duplicava `messages.upsert`; exige recriar o container da Evolution — combinar janela com o usuário (risco de pedir QR)
  - SCN-SEC-01
  - Files: `docker-compose.yml`, `docs/security/findings.md`
  - Verify: `docker logs evi-agent-api-1` sem `/webhooks/evolution ... 401` por 24 h e mensagens chegando (`logs/evolution_webhook.jsonl`)

## 2. Revisão

- [ ] 2.1 Modelo de ameaças (ativos, fronteiras, atacantes, superfícies, decisões de acesso remoto)
  - SCN-SEC-02
  - Files: `docs/security/threat-model.md`
  - Verify: revisão com o usuário (documento aprovado no chat)

- [ ] 2.2 `scripts/evi-security-scan` (pip-audit, segredos no histórico, `ruff --select S`, binds, permissões, rotas sem auth) e primeira execução
  - SCN-SEC-03
  - Files: `scripts/evi-security-scan`, `agent/testing/security_scan.py`, `tests/unit/test_security_scan.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_security_scan.py -q` e `./scripts/evi-security-scan`

- [ ] 2.3 Checklist §2.1–2.9 do design executado; `docs/security/findings.md` com todos os achados, evidência e severidade
  - SCN-SEC-02
  - Files: `docs/security/findings.md`, `docs/security/threat-model.md`
  - Verify: todo item do checklist tem evidência e resultado; revisão com o usuário

## 3. Correções (críticos/altos)

- [ ] 3.1 Rede e Windmill: `127.0.0.1:8001` (ou Tailscale com auth), credenciais do Windmill verificadas pelo usuário, `DOCKER-USER`/firewall conforme threat model
  - SCN-SEC-01
  - Files: `docker-compose.yml`, `docs/security/findings.md`, `docs/remote-access.md`
  - Verify: `./scripts/evi-security-scan` (binds) e `./scripts/evi-test smoke`

- [ ] 3.2 Segredos: trocar padrões (`evi-dev-key`, `changeme`, `windmill`), chave do Qdrant, permissões 600/700 em `.env`, `data/`, `logs/`; procedimento de rotação documentado
  - SCN-SEC-04
  - Files: `docker-compose.yml`, `.env.example`, `scripts/evi-rotate-secrets`, `docs/security/findings.md`
  - Verify: `./scripts/evi-security-scan` sem segredo padrão e `./scripts/evi-container-smoke.sh`

- [ ] 3.3 Demais achados críticos/altos do registro (um commit por achado; médios/baixos → BACKLOG)
  - SCN-SEC-02
  - Files: `docs/security/findings.md`, `openspec/BACKLOG.md`
  - Verify: `docs/security/findings.md` sem crítico/alto aberto

## 4. Guardas de regressão

- [ ] 4.1 Guarda de inicialização (sem chave → não sobe) + teste "toda rota não pública exige chave" + teste "nenhuma porta publicada sem 127.0.0.1"
  - SCN-SEC-05, SCN-AUTH-01
  - Files: `agent/main.py`, `tests/unit/test_security_guards.py`, `tests/unit/test_main_auth.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_security_guards.py tests/unit/test_main_auth.py -q`

- [ ] 4.2 CI: `pip-audit`, `ruff --select S` (exceções justificadas), varredura de segredos; smoke de container verifica 401; imagens com versão fixa
  - SCN-SEC-03, SCN-SEC-06
  - Files: `.github/workflows/ci.yml`, `scripts/evi-container-smoke.sh`, `docker-compose.yml`, `pyproject.toml`
  - Verify: CI verde no push; `./scripts/evi-container-smoke.sh`

## 5. Fechamento

- [ ] 5.1 Rotina de revisão leve por change no `openspec/config.yaml`; gates finais; BACKLOG + Progress
  - SCN-SEC-02
  - Files: `openspec/config.yaml`, `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `./scripts/evi-sim run --tag critical --llm replay`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
