## Context

- Dados com estado: Postgres `postgres:15-alpine` (`./data/postgres`), bancos `evidb` (agent +
  Evolution; `POSTGRES_DB`) e `windmill` (+ roles de RLS criadas por `scripts/postgres-init/`);
  `./data/contact_memory`; `./EVI_WORKSPACE` (memória, `USER.md`, relatórios); `.env` (segredos).
- O watchdog (`scripts/evi-watchdog`) já roda fora do EVI a cada minuto, lê só chaves permitidas
  do `.env` e alerta no Telegram com estado em `XDG_STATE_HOME`. Reaproveitar o padrão.
- Disco: 85 GB livres; banco ~125 MB + ~23 MB; cada backup cifrado deve ficar < 200 MB.
- `age` não está instalado; `gpg` está.

## Decisions

### 1. Cifra com chave pública
`gpg --encrypt --recipient $EVI_BACKUP_GPG_RECIPIENT`. Só a chave **pública** fica na máquina; a
privada o usuário guarda fora dela (gerenciador de senhas / pendrive). Quem roubar o disco não lê
os dumps (contêm WhatsApp, e-mails, `.env`). O script recusa rodar sem destinatário e nunca grava
dump em claro em disco: `pg_dump | gpg > arquivo.gpg`.

### 2. O que entra
`docker compose exec -T postgres pg_dump -Fc -U $POSTGRES_USER <db>` para `evidb` e `windmill`;
`pg_dumpall --globals-only` (roles, necessárias para restaurar o Windmill); `tar` de
`data/contact_memory` e `EVI_WORKSPACE`; `.env` copiado. Tudo num diretório
`data/backups/daily/AAAAMMDD-HHMM/` (0700, arquivos 0600) com `MANIFEST.json`
(nome, bytes, sha256, linhas por tabela principal de `evidb`, versão do Postgres).

### 3. Retenção e espaço
Mantém os 7 diários mais recentes e 1 por semana (domingo) das últimas 4. Recusa começar com
< 2 GB livres (alerta). Falha em qualquer parte → não promove o diretório (`.partial` →
renomeado no fim), nada é apagado nessa execução.

### 4. Segundo destino
`EVI_BACKUP_EXTRA_DIR` (opcional): `rsync -a` do diretório do dia para lá; ausente/desmontado →
aviso, não falha o backup local. Sem credencial de nuvem.

### 5. Verificação de restauração
`--verify` decifra (precisa da chave privada **ou** `--verify-key`; sem ela, só confere SHA-256 e
formato e avisa "restauração não provada") num container `postgres:15-alpine` com
`--network none`, `--tmpfs`, limite de 256 MB, `pg_restore` de `evidb` e `windmill` e compara
contagem de linhas com o manifesto (±0). Como a chave privada não deve ficar na máquina, a
verificação semanal usa, por padrão, uma **chave de verificação** separada
(`EVI_BACKUP_VERIFY_KEY`), também listada como destinatária; o usuário decide se a instala.
Sem ela, o modo é "integridade" (sha256 + `pg_restore --list`), que já pega arquivo truncado.

### 6. Alerta
Cada script grava `~/.local/state/evi/backup.json` (`last_ok_at`, `last_verify_ok_at`,
`last_error`). O watchdog lê o arquivo: backup > 36 h ou verify falho → **um** alerta, e **um**
"✅ backup normalizado" depois. `make status` imprime a idade.

### 7. Segurança
Sem rota nova, sem porta, sem segredo novo no EVI; o script lê do `.env` só as chaves que usa
(padrão do watchdog) e nunca imprime valores. Os arquivos ficam fora do git (`.gitignore`).

## Out of scope
Sem container novo permanente (o do verify vive segundos, 256 MB, `--rm`); sem portas.
