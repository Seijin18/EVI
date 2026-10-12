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

## Saída de dados para LLMs na nuvem

Tarefas de fundo que leem conversas (avaliação de promessas, conhecimento de contato)
só podem usar endpoints com retenção zero (OpenRouter `provider.zdr=true` +
`data_collection: "deny"`), aprovado pelo usuário em 2026-10-12. O tier gratuito da
Gemini API usa os dados para melhorar produtos — não usar para conteúdo pessoal.

## Pendências conhecidas

| Item | Onde |
|---|---|
| Webhook **global** da Evolution não manda cabeçalho e recebe 401 (eventos de contato/presença, não usados); desligar exige recriar o container da Evolution | `evi-security-review` task 1.2 |
| Windmill publicado em `0.0.0.0:8001` (guarda tokens OAuth de Gmail/Calendar/Tasks) | `evi-security-review` |
| Segredos padrão: `EVOLUTION_API_KEY`, `POSTGRES_PASSWORD`, `WINDMILL_DB_PASSWORD`; Qdrant sem chave | `evi-security-review` |
| Imagens sem versão fixa (`qdrant:latest`, `windmill:main`) | `evi-security-review` |
