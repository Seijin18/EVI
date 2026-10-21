## Why

O achado F13 (`docs/security/findings.md`, severidade média) segue aberto: **não existe backup do
que tem estado**. O Postgres (`evidb` — turnos, lembretes, dívidas, políticas — e `windmill`), a
memória por contato, o `EVI_WORKSPACE` e o `.env` vivem num único disco; o incidente de 12/08
(banco corrompido, `postgres.broken-*`) já mostrou que isso acontece. Hoje a recuperação seria
"torcer para existir uma cópia". Produto: o EVI só é confiável como assistente pessoal se não
perder o que aprendeu e o que prometeu.

## What Changes

- `scripts/evi-backup`: backup diário (timer de usuário do systemd, fora do EVI) de `pg_dump -Fc`
  de `evidb` e `windmill`, `pg_dumpall --globals-only`, `data/contact_memory/`, `EVI_WORKSPACE/` e
  `.env`, **cifrado com GPG (chave pública)**, com manifesto de SHA-256 e retenção 7 diários + 4
  semanais. Cópia opcional para um segundo destino (`EVI_BACKUP_EXTRA_DIR`, ex.: disco externo).
- `scripts/evi-backup --verify`: restaura o último backup num Postgres **descartável** (container
  sem rede, `tmpfs`) e confere tabelas/linhas contra o manifesto; roda semanalmente.
- O watchdog existente alerta no Telegram se o último backup bem-sucedido tem mais de 36 h ou se
  o último `--verify` falhou; `make status` mostra a idade do backup.
- Runbook de restauração e de guarda da chave em `docs/operations.md`.

## Impact

Novo: `scripts/evi-backup`, `scripts/systemd/evi-backup.{service,timer}`,
`scripts/systemd/evi-backup-verify.{service,timer}`. Alterado: `scripts/evi-watchdog`, `Makefile`,
`docs/operations.md`, `docs/security/{findings,threat-model}.md`, `.gitignore`. Spec:
`remote-access`. Sem container permanente; **sem LLM**; RAM: ~80 MB só durante o `--verify`.

## Validação em uso real

Janela de 14 dias: 14/14 backups concluídos (ou alerta recebido no Telegram quando não);
≥ 2 `--verify` com sucesso; tempo de restauração medido e registrado no BACKLOG.

## Out of scope

- Qdrant (reconstruível a partir dos documentos) e Neo4j (perfil opcional `graph`).
- Backup remoto/nuvem automático; a cópia para disco externo é só um diretório configurável.
- Restauração automática (o runbook é manual de propósito).
