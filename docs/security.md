# Segurança — acesso e autenticação

Estado em 2026-10-12. A revisão completa (modelo de ameaças, registro de achados,
guardas na CI) é o change [`evi-security-review`](../openspec/queued/evi-security-review/proposal.md).

## Exposição de rede

Todas as portas publicadas pelo `docker-compose.yml` ficam em `127.0.0.1`, exceto o
Windmill (ver pendências):

| Serviço | Host | Quem chama |
|---|---|---|
| agent-api | `127.0.0.1:8002` | scripts no host, watchdog; Windmill e Evolution usam a rede Docker (`http://agent-api:8000`) |
| windmill-server | `0.0.0.0:8001` | UI e triggers (pendente: restringir) |
| evolution-api | `127.0.0.1:8082` | `setup-evolution.sh`, Manager |
| postgres / qdrant / neo4j | `127.0.0.1` | agente, Windmill |

Até 2026-10-12 o `agent-api` publicava em `0.0.0.0:8002` com `EVI_API_KEY` vazio:
qualquer aparelho da rede local ou da Tailscale chamava `/chat`, `/run-task` e
`/webhooks/evolution` sem autenticação. O Docker publica portas por fora do `ufw`, então
o firewall do host não protegia. Os logs disponíveis (desde a recriação do container
no mesmo dia) não mostraram acesso externo.

Para conferir de outro aparelho: `http://<ip-do-host>:8002/tools` deve **não abrir**.

## Chave da API (`EVI_API_KEY`)

- Obrigatória: `.env` com `EVI_API_KEY` (64 hex) e `EVI_REQUIRE_API_KEY=true`; sem a
  chave o agente não sobe. Toda rota além de `/` e `/health` exige `X-Api-Key`.
- `.env` com permissão `600`.
- Quem envia a chave:
  - **Windmill**: o `windmill-worker` recebe `EVI_API_KEY` do `.env` e repassa aos jobs
    (`WHITELIST_ENVS=EVI_API_KEY`); os scripts leem `os.environ["EVI_API_KEY"]`.
  - **Evolution**: o webhook da instância (`/webhook/set/<instância>`) leva o cabeçalho
    `X-Api-Key`; `scripts/setup-evolution.sh` faz isso quando a chave está no `.env`.
  - **Scripts no host** (`watch_and_ingest.sh`, chamadas manuais com `curl`): precisam
    mandar `-H "X-Api-Key: $EVI_API_KEY"`.

### Trocar a chave

1. Gerar e gravar sem exibir:
   `sed -i "s/^EVI_API_KEY=.*/EVI_API_KEY=$(openssl rand -hex 32)/" .env`
2. Atualizar o webhook da Evolution **antes** de recriar o agente (o agente antigo
   ignora o cabeçalho, então nada se perde no meio): rodar só o trecho
   "Setting webhook on instance" de `scripts/setup-evolution.sh` ou o script inteiro
   **sem** `--reset` (o `--reset` apaga a instância e pede QR de novo).
3. `docker compose up -d agent-api windmill-worker`
4. Verificar: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8002/tools` → `401`;
   com `-H "X-Api-Key: …"` → `200`; uma mensagem de WhatsApp aparece em
   `logs/evolution_webhook.jsonl`.

## Rotação de segredos

Cobre `EVOLUTION_API_KEY`, `POSTGRES_PASSWORD`, `WINDMILL_DB_PASSWORD`, `NEO4J_PASSWORD` e
`QDRANT__SERVICE__API_KEY` (o agente recebe a do Qdrant como `QDRANT_API_KEY`). O
`docker-compose.yml` não tem mais valores padrão para eles (`${VAR:?…}`): sem a variável no
`.env` o compose recusa subir. `.env.example` traz só `CHANGE_ME_…`.

- **Quando:** instalação nova (substitui os `CHANGE_ME`), suspeita de vazamento (log, print,
  repositório), troca de máquina/pessoa com acesso, ou a cada 6–12 meses.
- **Comando:** `scripts/evi-rotate-secrets` (simulação: só nomes, serviços e passos) e depois
  `scripts/evi-rotate-secrets --apply`. `--only NOME[,NOME]` rotaciona um subconjunto
  (`QDRANT` é alias). `EVI_API_KEY` tem procedimento próprio (seção acima).
- **O que `--apply` faz:** exige o Postgres saudável; `pg_dumpall` e cópia do `.env` em
  `data/backups/` (`pre-rotate-<ts>.sql`, `env-pre-rotate-<ts>`, modo `600`, aborta se o
  dump vier vazio); `ALTER ROLE` dentro do Postgres (senha via stdin do `psql`, nunca em
  argumentos); reescreve o `.env` de forma atômica (`600`), mexendo só nas chaves alvo e na
  senha dentro de `DATABASE_URL`; recria só os serviços afetados; verifica `/health` do
  agente, Evolution (chave nova aceita, inválida recusada), Windmill e Qdrant (200 com chave,
  401 sem). Valores gerados com `secrets.token_urlsafe(32)`; nenhum é impresso.
- **Fora do `.env`:** a simulação lista arquivos do repositório que contenham o valor atual
  (por caminho) e lembra que variáveis/recursos criados na UI do Windmill ficam no banco do
  Windmill e precisam ser conferidos à mão.
- **Neo4j parado:** só o `.env` muda; o `NEO4J_AUTH` só vale num diretório de dados novo. Se
  `data/neo4j` já existe, rode `ALTER CURRENT USER SET PASSWORD` depois de subir o serviço.
- **Rollback (nunca automático):** se uma verificação falhar o comando sai com código 1 e
  mostra os passos. Restaurar `cp -p data/backups/env-pre-rotate-<ts> .env`; para os papéis do
  banco já alterados, voltar a senha antiga (que está nessa cópia do `.env`) com
  `docker compose exec -T postgres psql -U <superusuário> -d postgres` e, no stdin,
  `\set ON_ERROR_STOP on`, `\set rot_role '<papel>'`, `\set rot_pw '<senha antiga>'`,
  `SELECT format('ALTER ROLE %I PASSWORD %L', :'rot_role', :'rot_pw') \gexec`; depois
  `docker compose up -d --force-recreate --no-deps <serviços>`. O dump só serve se houver dano
  nos dados. Apague as cópias em `data/backups/` quando não precisar mais delas: guardam as
  senhas antigas.

- **Imagens fixas:** `qdrant/qdrant:v1.18.0` e Windmill por digest (`main@sha256:…`, o build em
  execução). O `evi-security-scan` aceita digest como fixação (`@sha256:` vale mesmo com tag
  `main`). Antes de alterar qualquer coisa, `--apply` confere que as imagens existem
  localmente (sem `pull`); se só falta a tag fixada do Qdrant e `qdrant/qdrant:latest` é a mesma
  versão (label), faz `docker tag` local. Antes de qualquer `ALTER ROLE` ele também grava
  `data/backups/env-post-rotate-<ts>` (`600`, só os valores NOVOS) para não perdê-los se o
  processo cair no meio; após verificação bem-sucedida esse arquivo (segredos novos em texto puro) é apagado, e os backups `pre-rotate` ficam. Se uma execução parar no meio, o `--apply` seguinte recusa (há `env-post-rotate-*` mais novo que o `.env`) até você copiar os valores para o `.env` e recriar os serviços, ou passar `--force-new-secrets`. A mensagem de falha indica a etapa e o comando exato de recuperação.

## Saída de dados para LLMs na nuvem

Tarefas de fundo que leem conversas (avaliação de promessas, conhecimento de contato)
só podem usar endpoints com retenção zero (OpenRouter `provider.zdr=true` +
`data_collection: "deny"`), aprovado pelo usuário em 2026-10-12. O tier gratuito da
Gemini API usa os dados para melhorar produtos — não usar para conteúdo pessoal.

## Gates de CI

O job `security` de `.github/workflows/ci.yml` roda, em todo push/PR:

| Gate | O que verifica |
|---|---|
| `ruff check agent/ --select S102,S307,S602,S604,S605,S608` | sem `eval`/`exec`/`shell=True`/SQL montado por string; exceções só com `# noqa: Sxxx — motivo` |
| `./scripts/evi-security-scan --ci` | portas do compose em `127.0.0.1`, imagens com versão fixa, rotas exigindo a chave, sem arquivos proibidos rastreados nem segredos no histórico git (placeholders FAKE de testes em `HISTORY_ALLOW`), `pip-audit` (vulnerabilidade com correção disponível reprova; rede indisponível vira SKIP) |
| `scripts/evi-container-smoke.sh` (job `container`) | `POST /chat` sem chave devolve 401 no stack composto |

O modo `--ci` ignora o que depende do `.env`, do host ou do docker (`secrets.env`, `binds.host`,
`perms.*`, trivy); isso só roda no scan completo. Localmente:

```bash
./scripts/evi-security-scan --ci    # o mesmo que o CI (exit 1 em FAIL)
./scripts/evi-security-scan         # scan completo, inclui .env, permissões e portas do host
```

## Pendências conhecidas

Registro completo em [`docs/security/findings.md`](security/findings.md). Em aberto, dependem do usuário:

| Item | Onde |
|---|---|
| Ollama escuta em `0.0.0.0:11434` sem autenticação (bind em `172.17.0.1`, sudo) | F5 |
| Plano da chave do Gemini (tier gratuito pode treinar com os dados) | F6 |
| SSH por senha, ufw desligado; portas do WhatBot em `0.0.0.0`; escopos OAuth; login do Windmill; Tailscale serve antigo | F9–F12, F26 |
