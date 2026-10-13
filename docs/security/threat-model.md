# Modelo de ameaças — EVI

Change `evi-security-review`, task 2.1. Estado em 2026-10-13. Evidências de rede vêm
de `docker-compose.yml`, `ss -ltn` e `docker ps` no host nessa data; o resto, do código.
O que não foi verificado está marcado **a verificar** (resolver na task 2.3).
Achados registrados em [`findings.md`](findings.md) (IDs `F*`); método em
`openspec/changes/evi-security-review/design.md` §2 (itens 2.1–2.9).

## 1. Escopo e arquitetura

Escopo: o sistema montado em um único host Linux (16 GB, LAN `192.168.15.0/24`,
Tailscale `100.x`), `docker-compose.yml` + Ollama no host + timers de usuário (watchdog).

```
   [Telegram API] <--long polling (saída)--+            [Contatos WhatsApp]
                                           |                    |
 ======== Internet / terceiros ============|====================|=========
   [Gemini API] [OpenRouter ZDR] [Google APIs (Gmail/Cal/Tasks)] [WhatsApp]
        ^             ^                    ^                       ^
        |  HTTPS      |                    | OAuth (tokens no WM)  | sessão
 ======== Host (fronteira: rede local / tailnet) =========================
   SSH :22 (0.0.0.0)          Ollama :11434 (*, OLLAMA_HOST=0.0.0.0)
   Windmill UI :8001 (0.0.0.0)   <-- LAN / tailnet alcançam
   ---------------- 127.0.0.1 ----------------
   agent-api :8002   Evolution :8082   Postgres :5433   Qdrant :6333
   Neo4j :7474/7687 (perfil graph)
 ======== Rede Docker (compose) ==========================================
   agent-api:8000 <-- Windmill worker (X-Api-Key)  <-- Evolution webhook (X-Api-Key)
   agent-api --> windmill-server:8000 (WINDMILL_TOKEN) --> Google
   agent-api --> postgres, qdrant, redis (sem porta no host), evolution-api:8080
 ======== Disco ==========================================================
   data/ (postgres, qdrant, contact_memory, payload_shapes, backups)
   logs/*.jsonl (conteúdo integral)   EVI_WORKSPACE/ (memória do usuário)   .env
```

Fronteiras de confiança: **TB1** Internet ↔ host; **TB2** LAN/tailnet ↔ portas do host;
**TB3** host ↔ rede Docker; **TB4** conteúdo de terceiros ↔ prompt do LLM (dado vs.
instrução); **TB5** processo ↔ disco.

## 2. Ativos

| Ativo | Onde | Impacto se comprometido |
|---|---|---|
| Tokens OAuth Google (Gmail `modify`, Calendar, Tasks) | Windmill (Postgres `windmill`) | Ler/apagar e-mail, criar/alterar eventos e tarefas; tomada de contas via reset de senha por e-mail |
| Sessão do WhatsApp | Evolution (Postgres + volume) | Ler e enviar mensagens como o usuário |
| Capacidade de agir do agente | `agent/tools/` (`delete_emails*`, `schedule_event`, `create_task`, envio Telegram/WhatsApp) | Ação em nome do usuário sem pedido dele |
| Conversas de terceiros | `data/contact_memory/`, Postgres, `logs/evolution_webhook.jsonl` | Vazamento de dados pessoais de terceiros (LGPD) |
| Memória do usuário | `EVI_WORKSPACE/` (`USER.md`, `MEMORY.md`), Postgres | Perfil íntimo do usuário; envenenamento de memória |
| Chaves e segredos | `.env` (600) | `EVI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `WINDMILL_TOKEN`, senhas de banco → pivô para todos os ativos acima; custo de LLM |
| Disponibilidade | todos os containers | Lembretes/briefing não chegam (confiabilidade) |

## 3. Fluxos que cruzam a fronteira para fora (TB1)

| Destino | O que sai | Quando | Política |
|---|---|---|---|
| Gemini API | Turnos de chat (mensagem do usuário + contexto, incl. trechos `wrap_external` de e-mail/WhatsApp), embeddings se `EVI_EMBED_PROVIDER=gemini` | `EVI_LLM_PROVIDER=gemini` | Tier gratuito retém para treino → não usar com conteúdo pessoal (`docs/security.md`). Tier da chave de produção: **a verificar** |
| OpenRouter | Prompts das tarefas de fundo (`llm_structured`: promessas, conhecimento de contato) | `EVI_LLM_TASK_<T>_PROVIDER=openrouter` | Forçado em código: `provider.zdr=true`, `data_collection="deny"`; teto diário `EVI_LLM_TASK_DAILY_USD` (fail-closed). **Decisão do usuário 2026-10-12** (teto US$ 5/mês) |
| Google APIs | Consultas/escritas de e-mail, agenda, tarefas | Via Windmill | Escopos OAuth mínimos: **a verificar** (2.8) |
| Telegram | Respostas, briefing, alertas do watchdog | Saída HTTPS; entrada por long polling (sem porta) | Bot com allowlist de chat |
| WhatsApp (Evolution) | Respostas no chat de controle | Saída | Só para `EVI_WHATSAPP_CONTROL_JIDS` — outras rotas de envio: **a verificar** |
| Tailscale | Tráfego da tailnet até o host | Sempre ativo | ACLs da tailnet: **a verificar** (2.1) |
| Ollama (local) | Nada sai do host | Fallback/tarefas locais | — |

## 4. Atacantes

| # | Atacante | Capacidade | Objetivo | Caminho principal |
|---|---|---|---|---|
| A | Outro dispositivo na LAN/tailnet | Conecta em qualquer porta publicada em `0.0.0.0` | Agir como o EVI, roubar tokens | Windmill `:8001` (F2), Ollama `:11434`, SSH; antes de 2026-10-12, `agent-api :8002` aberto (F1, contido). O Docker publica por fora do `ufw` |
| B | Contato malicioso no WhatsApp/Telegram | Envia texto/áudio que chega ao prompt | Fazer o agente apagar e-mail, enviar mensagem, envenenar memória | Webhook Evolution → ingest → `pending_commitments`/memória de contato → contexto do LLM (TB4); Telegram só se o chat estiver na allowlist |
| C | Remetente de e-mail malicioso | Controla assunto/corpo lido pelo agente | Idem B; exfiltrar via tool de saída | `search_emails`/briefing → contexto do LLM |
| D | Dependência/imagem comprometida | Código roda dentro de containers com `.env` | Roubar segredos, persistir | `requirements.txt` sem auditoria, `qdrant:latest`, `windmill:main` (F4) |
| E | Provedor de LLM/infra | Vê os prompts | Reter/treinar com dados pessoais | Gemini (tier), OpenRouter (mitigado por ZDR), resposta maliciosa do modelo |
| F | Acesso físico/malware no host | Tudo | — | **Fora de escopo** (registrado, §7) |

## 5. Superfícies e controles

| Superfície | Exposição (verificada) | Controle atual | Lacuna / achado |
|---|---|---|---|
| agent-api | `127.0.0.1:8002`; rede Docker `agent-api:8000` | `verify_api_key` (`X-Api-Key`) em todas as rotas exceto `/`, `/health`, `/metrics`; `EVI_REQUIRE_API_KEY=true` no `.env` (hotfix) | F1 contido. Compose ainda tem default `EVI_REQUIRE_API_KEY=false` e `verify_api_key` é no-op sem chave (task 4.1). Comparação com `!=`, não constante (baixo). `/metrics` público — spec delta só permite `/` e `/health` |
| `/run-task` | idem | Chave; executa **qualquer** tool registrada com params livres | Sem turno → canal `None` → `check_write` libera escrita; deleção ainda exige token+confirmação do turno (sem turno, recusa) — confirmar em 2.3 |
| `/jobs/*` | idem | Chave | `/jobs/import-contacts` lê `request.path` sem restrição de diretório (qualquer arquivo visível no container; conteúdo não volta inteiro) — baixo |
| Webhook Evolution `/webhooks/evolution` | rede Docker | `X-Api-Key` no webhook da instância; filtros (`INCOMING_ONLY`, `SKIP_GROUPS`, dedupe, idade, `MAX_PER_WEBHOOK`) | Webhook global: `WEBHOOK_GLOBAL_ENABLED=false` no compose (2026-10-13, ainda não commitado; recriação do container: **a verificar**, task 1.2). Limite de taxa/tamanho: **a verificar** (2.9) |
| Webhook Telegram / polling | sem porta (polling) | `_chat_allowed`: `TELEGRAM_CHAT_ID` + `TELEGRAM_ALLOWED_CHAT_IDS` | **Fail-open**: sem `TELEGRAM_CHAT_ID` aceita qualquer chat (só loga aviso) |
| Chat de controle WhatsApp | via webhook | `parse_control_jids()` (`EVI_WHATSAPP_CONTROL_JIDS`) → `/chat` com canal `whatsapp_control` | Confiança no JID informado pela Evolution; spoofing de `fromMe`/JID: **a verificar** |
| Ferramentas de escrita | LLM | `write_guard`: allowlist por canal (`WRITE_TOOLS` × `USER_CHANNELS`={telegram, whatsapp_control, api}); deleção em duas etapas (token, turno seguinte, confirmação literal, TTL 10 min, máx. 50) | Tools de envio de mensagem fora de `WRITE_TOOLS`? Tarefas novas (`llm_structured`) sem tools? — **a verificar** (2.6) |
| Conteúdo de terceiros no prompt | LLM | `wrap_external` (marcadores neutralizados, NFKC, controle removido, truncado) | Cobertura em todos os caminhos (briefing, promessas, contato): **a verificar** (2.6) |
| Windmill | **`0.0.0.0:8001`** (LAN + tailnet) | Login próprio | **F2 (alto)** aberto; credenciais/usuários/tokens: **a verificar** (2.8). `BASE_URL=http://localhost:8001` |
| Evolution API | `127.0.0.1:8082` | `AUTHENTICATION_API_KEY` | F3: default `evi-dev-key` no compose |
| Postgres | `127.0.0.1:5433` | senha | F3: default `changeme`/`windmill` no exemplo; Windmill DB default `windmill` |
| Qdrant | `127.0.0.1:6333` | `QDRANT__SERVICE__API_KEY` opcional | F3: sem chave hoje; F4: `latest` |
| Neo4j | `127.0.0.1` (perfil `graph`) | senha | default `changeme` no compose |
| Redis (EVI) | só rede Docker | nenhuma | Sem senha (aceitável sem porta) |
| Redis de outro projeto (`whatbot-redis-1`) | **`0.0.0.0:6379`** | nenhuma (**a verificar**) | Fora do EVI mas no mesmo host/LAN — registrar |
| Ollama (host) | **`*:11434`** (`OLLAMA_HOST=0.0.0.0`) | nenhuma | Qualquer um na LAN/tailnet usa GPU/modelos; sem dados persistentes. Necessário para a rede Docker — restringir à bridge |
| SSH | `0.0.0.0:22` | **a verificar** (chave vs. senha) | Fora do compose; relevante para o túnel (§6) |
| Firewall | `ufw` instalado | Docker ignora `ufw` em portas publicadas | Regras/`DOCKER-USER`: **a verificar** (2.1) |
| Logs em disco | `logs/` (775) | gitignored | `telegram.jsonl`, `evolution_webhook.jsonl` com conteúdo integral; sem retenção; permissões abertas ao grupo (spec: 700) |
| Dados em disco | `data/`, `EVI_WORKSPACE/` (775) | gitignored | Permissões (spec: 700); backups em `data/backups/` sem cifra |
| `.env` | 600 | gitignored | Presença no histórico git: **a verificar** (2.3) |
| Imagens | Docker Hub/GHCR | — | F4: `qdrant:latest`, `windmill:main`; `redis:7-alpine`, `neo4j:5-community` sem patch fixo |

## 6. Acesso remoto (Tailscale)

| Opção | Como | Prós | Contras |
|---|---|---|---|
| A — nada exposto | Todas as portas em `127.0.0.1`; acesso remoto sob demanda por `ssh -L` ou `tailscale serve` | Superfície zero na LAN/tailnet; `tailscale serve` adiciona identidade da tailnet | Exige túnel ativo para usar a UI |
| B — bind na `tailscale0` | `ports: ["100.x.y.z:8001:8000"]` + autenticação | Acesso direto da tailnet | IP muda se o nó for recriado; qualquer nó da tailnet alcança; Docker publica por fora do `ufw`; spec exige `127.0.0.1` em todo bind |

### Decisões do usuário

| Data | Decisão |
|---|---|
| 2026-10-12 | `agent-api` só em loopback (`127.0.0.1:8002`) **e** com `EVI_API_KEY` + `EVI_REQUIRE_API_KEY=true` (hotfix aplicado, verificado: LAN/tailnet recusam, sem chave → 401) |
| 2026-10-12 | **Windmill só em `127.0.0.1:8001`**; acesso remoto por túnel SSH ou `tailscale serve` (opção A) — implementar na task 3.1 |
| 2026-10-12 | Conversas podem ir para a nuvem só via OpenRouter com ZDR + `data_collection=deny`; teto US$ 5/mês |
| 2026-10-12 | Rotação de senhas padrão, chave do Qdrant e webhook global da Evolution executadas durante a fila; se a Evolution pedir QR, parar e chamar o usuário |
| 2026-10-12 | Ferramentas autorizadas: `pip-audit` (pinado) e `trivy` (imagem oficial, versão fixa) |
| 2026-10-13 | Webhook global da Evolution desligado (`WEBHOOK_GLOBAL_ENABLED=false`) |

Pendente de confirmação do usuário: nenhum cliente legítimo (celular etc.) usava `:8002`
ou `:8001` pela LAN/tailnet (design, Riscos).

## 7. Riscos residuais aceitos e fora de escopo

| Item | Situação |
|---|---|
| Host comprometido / acesso físico / malware | Fora de escopo: tem `.env` e todos os dados |
| Cifra de disco/volumes | Fora de escopo; recomendação ao SO (LUKS) |
| Pentest externo | Fora de escopo |
| Prompt injection residual | Aceito: mitigado por allowlist em código + confirmação em duas etapas, não eliminado; modelo não será reescrito |
| Evolution é API não oficial do WhatsApp | Aceito: risco de banimento/quebra da sessão |
| Gemini/OpenRouter veem os prompts | Aceito sob ZDR (OpenRouter); Gemini conforme tier (a verificar) |
| Teto de custo pode ser ultrapassado por chamadas concorrentes | Aceito (documentado em `llm_structured.py`) |

## 8. Rotina — quando reabrir este modelo

Revisão leve (registrar no change e atualizar §2/§5) sempre que um change:

- publicar uma porta nova ou mudar um bind/rede (`docker-compose.yml`, Tailscale);
- adicionar tool de escrita/envio ou rota HTTP nova (conferir `WRITE_TOOLS`, `verify_api_key`);
- adicionar provedor de LLM ou mudar o que é enviado a um (conferir ZDR/tier);
- adicionar canal de entrada (novo webhook, novo mensageiro, pasta vigiada);
- passar a gravar nova categoria de dado de terceiros em disco ou log;
- adicionar container/imagem ou integração OAuth com escopo novo.

## Hipóteses a validar na revisão (2.3)

1. Docker publica `:8001` por fora do `ufw`; `DOCKER-USER` vazio; ACLs da tailnet permitem todos os nós ao host (§2 item 1).
2. Ollama `0.0.0.0:11434`, SSH `:22` e `whatbot-redis` `:6379` respondem da LAN/tailnet; SSH aceita senha? (§2 item 1).
3. Nenhuma rota além de `/`, `/health` (e `/metrics`) responde sem chave; `/metrics` não expõe dado sensível (§2 item 2).
4. `/run-task` sem turno não executa `delete_emails*` sem confirmação e não permite envio arbitrário (§2 item 2 e 6).
5. `TELEGRAM_CHAT_ID` está definido em produção (allowlist não está em fail-open) (§2 item 2).
6. JID de controle não pode ser forjado por mensagem de terceiro (`fromMe`/`remoteJidAlt`) (§2 item 2).
7. `.env` nunca entrou no histórico git; nenhum segredo aparece em `logs/*.jsonl` (§2 item 3).
8. Senhas padrão (`evi-dev-key`, `changeme`, `windmill`) seguem em uso; `logs/`, `data/`, `EVI_WORKSPACE/` estão 775 (§2 item 3).
9. `pip-audit`/`trivy` acham CVE alto em dependências ou imagens `latest`/`main` (§2 item 4).
10. `/jobs/import-contacts` aceita qualquer path legível no container; não há `shell=True`/SQL por string em entrada externa (§2 item 5).
11. Todo conteúdo de terceiros que chega ao LLM passa por `wrap_external`; tarefas `llm_structured` não chamam tools; chave Gemini de produção não é tier gratuito (§2 item 6).
12. Escopo Gmail `modify` é necessário; Windmill sem usuários/tokens sobrando; webhooks sem limite de taxa/tamanho (§2 itens 8 e 9).
