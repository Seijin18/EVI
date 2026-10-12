## Context

Sistema montado (`docker-compose.yml`): `agent-api` (FastAPI), `windmill-server`/
`worker`, `evolution-api` (WhatsApp não oficial), `postgres`, `redis`, `qdrant`, `neo4j`
(opcional), Ollama no host; Telegram por long polling (sem porta de entrada); Tailscale
no host. Dados: `data/` (Postgres, Qdrant, memória de contato com conversas de
terceiros), `logs/` (`telegram.jsonl`, `evolution_webhook.jsonl` com conteúdo integral),
`EVI_WORKSPACE/` (memória do usuário). Saídas: Google (via Windmill), Telegram, Gemini,
OpenRouter (ZDR).

Varredura inicial (2026-10-12, sem login em nada, só leitura de config e `ss`):

| Porta | Serviço | Bind | Autenticação |
|---|---|---|---|
| 8002 | agent-api | `0.0.0.0` / `[::]` | `EVI_API_KEY` **vazio** → aberta |
| 8001 | Windmill | `0.0.0.0` / `[::]` | login próprio (credenciais não verificadas) |
| 8082 | Evolution | `127.0.0.1` | `evi-dev-key` (padrão) |
| 5433 | Postgres | `127.0.0.1` | `changeme` (padrão) |
| 6333 | Qdrant | `127.0.0.1` | nenhuma |
| 7474/7687 | Neo4j | `127.0.0.1` | senha definida |

Interfaces do host: LAN `192.168.15.32/24`, Tailscale `100.73.36.18`. O Windmill chama o
agente pela rede Docker (`http://agent-api:8000`), não pela porta do host.

## Decisions

### 1. Contenção imediata de F1 (antes do resto, pode ir como hotfix)

`ports: ["127.0.0.1:8002:8000"]` e `EVI_API_KEY` gerado (≥ 32 bytes aleatórios) +
`EVI_REQUIRE_API_KEY=true`; a mesma chave na variável secreta do Windmill usada pelos
scripts. Acesso remoto pretendido (spec `remote-access`) passa a ser só pela Tailscale com
`tailscale serve` ou bind explícito na interface `tailscale0` **e** chave — decisão do
usuário registrada no threat model.

### 2. Método da revisão

Checklist por superfície (derivado de OWASP ASVS nível 1 + OWASP Top 10 para aplicações
LLM), cada item com evidência (comando/arquivo) e resultado:

1. **Rede**: binds, firewall do host (`ufw`), Tailscale ACLs, Docker publicando portas
   por cima do firewall (iptables `DOCKER-USER`).
2. **Autenticação/autorização**: todo endpoint do `agent-api` (tabela rota × proteção);
   `/run-task` e `/jobs/*` exigem chave; webhook da Evolution autenticado; allowlist do
   Telegram (`_chat_allowed`); chat de controle do WhatsApp (`parse_control_jids`).
3. **Segredos**: `.env` fora do git (e do histórico — varredura), padrões fracos,
   rotação, chaves em logs, permissões de arquivo (`.env`, `data/`, `logs/` = 600/700).
4. **Dependências e imagens**: `pip-audit` sobre `requirements.txt`; imagens com versão
   fixa e digest; varredura de CVEs das imagens (ferramenta a confirmar com o usuário —
   download).
5. **Código**: regras `S` (bandit) do ruff; `subprocess`/`shell=True`, SQL montado com
   string, desserialização, `eval`, caminhos vindos de entrada (`/jobs/import-contacts`
   recebe path).
6. **LLM**: allowlist de tools por origem cobre as tarefas novas (`llm_structured`);
   conteúdo de terceiros sempre `wrap_external`; saída para nuvem só ZDR; teto de custo.
7. **Dados em repouso e logs**: o que fica em `logs/*.jsonl` (conteúdo integral de
   conversas), retenção, backups (`data/backups`), quem lê.
8. **Integrações**: escopos OAuth mínimos (Gmail `modify` é necessário?), Windmill
   (usuários, tokens de API, workspace), Evolution (instância, webhook URL).
9. **Disponibilidade/abuso**: limites de taxa nos webhooks, tamanho de payload,
   watchdog, custo de LLM.

### 3. Registro de achados

`docs/security/findings.md`: `ID | superfície | severidade (crítico/alto/médio/baixo,
critério escrito no topo) | evidência | correção | status`. Crítico/alto: corrigido no
change, com teste de regressão quando automatizável. Médio/baixo: item no BACKLOG.

### 4. Ferramentas

`scripts/evi-security-scan` (offline, sem tocar contas): `pip-audit`, varredura de
segredos no histórico git, `ruff check --select S`, listagem de binds (`ss`) e permissões
de arquivos, checagem de rotas sem dependência de autenticação (introspecção do app
FastAPI). Ferramentas que exigem download (ex.: varredor de imagens) só com aprovação do
usuário, com nome/origem/tamanho.

### 5. Guardas de regressão

- `agent-api` na inicialização: se `EVI_REQUIRE_API_KEY` não for `true` e `EVI_API_KEY`
  estiver vazio → erro fatal (fim do modo "aberto silencioso").
- Teste unitário: toda rota não listada em `PUBLIC_ROUTES` (`/health`, `/`) depende de
  `verify_api_key`.
- `evi-container-smoke.sh`: `POST /chat` sem chave → 401.
- CI: `pip-audit` + `ruff --select S` (com exceções justificadas) + varredura de segredos.
- `docker-compose.yml`: nenhuma porta sem `127.0.0.1:` (teste lê o arquivo).

## Riscos

- **Quebrar acessos legítimos**: algum cliente usa `:8002` pela LAN/tailnet (ex.:
  celular)? Levantado no threat model antes de fechar; a contenção (§1) pede confirmação.
- **Falsos positivos de ferramenta**: exceções documentadas no registro, não silenciadas.
- **RAM**: nenhum container novo.

## Out of scope

- Pentest externo, criptografia de disco, reescrita do modelo de prompt injection.
