## 1. Backup

- [ ] 1.1 `scripts/evi-backup`: dumps (`evidb`, `windmill`, globals), tar de `contact_memory` e `EVI_WORKSPACE`, `.env`, cifra GPG em pipeline, manifesto, `.partial` → rename, `--dry-run`, estado em `backup.json`
  - SCN-BKP-01
  - Files: `scripts/evi-backup`, `tests/unit/test_backup.py`, `.gitignore`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_backup.py -q`

- [ ] 1.2 Retenção 7 diários + 4 semanais, recusa sem destinatário ou com < 2 GB livres, segundo destino opcional (`EVI_BACKUP_EXTRA_DIR`)
  - SCN-BKP-02
  - Files: `scripts/evi-backup`, `tests/unit/test_backup.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_backup.py -q`

## 2. Verificação

- [ ] 2.1 `--verify`: SHA-256 + `pg_restore --list`; com chave, restaura em container descartável (`--network none`, tmpfs, 256 MB) e compara linhas com o manifesto
  - SCN-BKP-03, SCN-BKP-04
  - Files: `scripts/evi-backup`, `tests/unit/test_backup.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_backup.py -q` e `./scripts/evi-backup --verify` num backup real

- [ ] 2.2 Timers de usuário: backup diário 03:30 e verify semanal (domingo 04:30); instalação documentada
  - SCN-BKP-01
  - Files: `scripts/systemd/evi-backup.service`, `scripts/systemd/evi-backup.timer`, `scripts/systemd/evi-backup-verify.service`, `scripts/systemd/evi-backup-verify.timer`
  - Verify: `systemd-analyze --user verify scripts/systemd/evi-backup.timer scripts/systemd/evi-backup-verify.timer`

## 3. Alerta e fechamento

- [ ] 3.1 Watchdog lê `backup.json` (idade > 36 h ou verify falho → um alerta + um "normalizado"); `make status` mostra a idade
  - SCN-BKP-05
  - Files: `scripts/evi-watchdog`, `Makefile`, `tests/unit/test_watchdog.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_watchdog.py -q`

- [ ] 3.2 Runbook (restaurar, guarda da chave privada, teste de restauração) e revisão leve de segurança: threat-model, findings (F13 fechado), `evi-security-scan`
  - SCN-BKP-01
  - Files: `docs/operations.md`, `docs/security/threat-model.md`, `docs/security/findings.md`, `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `./scripts/evi-security-scan`, `openspec validate --specs`

- [ ] 3.3 Execução real: backup + verify no host, tempo e tamanho registrados; gates
  - SCN-BKP-03
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `./scripts/evi-backup && ./scripts/evi-backup --verify`, `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `ruff check agent/ --select E,W,F --ignore E501`
