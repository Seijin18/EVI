# Registro de achados de segurança — EVI

Change `evi-security-review`, task 2.3 (checklist do design §2, itens 1–9). Revisão
executada em 2026-10-13 sobre o sistema em execução, só leitura: nenhum segredo lido para
fora do processo que o usa (só presença, tamanho e permissões). Modelo de ameaças:
[`threat-model.md`](threat-model.md). Ferramenta: `./scripts/evi-security-scan`.

## Critério de severidade

| Severidade | Critério | Tratamento |
|---|---|---|
| **crítico** | Alcançável sem autenticação da rede (LAN/tailnet) **e** permite agir como o usuário ou ler dados pessoais/tokens | Corrigir imediatamente (hotfix), dentro do change |
| **alto** | Alcançável da rede sem autenticação com impacto em disponibilidade/recursos do host, **ou** exposição de dados pessoais a terceiro fora da política aprovada, **ou** caminho de tomada de tokens que depende só de um controle não verificado | Corrigir dentro do change; não arquivar com alto aberto sem decisão registrada |
| **médio** | Exige uma pré-condição (acesso local, chave, erro de configuração, outro projeto comprometido) e o impacto seria alto; ou falta de defesa em profundidade em controle importante | Corrigir no change se barato; senão BACKLOG |
| **baixo** | Impacto limitado ou pré-condição forte (acesso ao host, chave da API); higiene | BACKLOG ou guarda já prevista |
| **info** | Observação, falso positivo, risco aceito documentado | Registrar |

Status: `aberto` · `corrigido (<task/data>)` · `em correção (<task>)` · `BACKLOG` · `aceito`.
**ação do usuário** = depende de `sudo`, outro projeto, console externo ou login; comando em
[Ações do usuário](#ações-do-usuário).

## Resumo

| Severidade | Qtde | Abertos |
|---|---|---|
| crítico | 1 | — (F1 corrigido) |
| alto | 3 | F6 provisório — ação do usuário (F2 e F5 corrigidos) |
| médio | 9 | ver tabela |
| baixo | 9 | F13, F18, F20, F22 (BACKLOG) |
| info | 6 | ver tabela |

## Achados

| ID | Título | Sev. | Status | Evidência | Decisão |
|---|---|---|---|---|---|
| F1 | `agent-api` em `0.0.0.0:8002` sem `EVI_API_KEY` | crítico | corrigido (1.1, 2026-10-12) | `ss -ltn`: só `127.0.0.1:8002`; `curl localhost:8002/tools` sem chave → 401; `192.168.15.32:8002` e `100.73.36.18:8002` → recusada; container: `EVI_API_KEY` len 64 | Feito; resíduo em F8. Ação do usuário: confirmar de outra máquina |
| F2 | Windmill em `0.0.0.0:8001` (tokens OAuth Google) | alto | corrigido (3.1, 2026-10-13) | compose `127.0.0.1:8001:8000`; LAN/tailnet → recusada | Acesso remoto em `docs/remote-access.md`; credenciais: F12 |
| F3 | Segredos padrão; Qdrant sem chave | médio | corrigido (3.2, rotação aplicada 2026-10-13) | scan `secrets.env` FAIL (`EVOLUTION_API_KEY`, `POSTGRES_PASSWORD`, `WINDMILL_DB_PASSWORD`); fallbacks no compose; tudo em loopback/rede Docker | `scripts/evi-rotate-secrets` |
| F4 | Imagens sem versão fixa | médio | corrigido (3.2/4.2: qdrant v1.18.0, windmill por digest; redis/neo4j/postgres por tag major) | `qdrant:latest`, `windmill:main`; flutuantes: `redis:7-alpine`, `neo4j:5-community`, `postgres:15-alpine`. trivy (HIGH/CRITICAL): evolution C11/H253, windmill C33/H1121, neo4j C6/H548, postgres C1/H35, qdrant C7/H127, redis H4 — SO base, nada exposto fora do host | Fixar por tag/digest; SCN-SEC-06 aceita digest |
| F5 | Ollama em `*:11434` sem auth, LAN + tailnet | alto | corrigido (2026-10-19, `./scripts/evi-host-hardening ollama`: escuta só em `172.17.0.1`; LAN/tailnet/loopback recusam, container responde 200) | `OLLAMA_HOST=0.0.0.0` (override.conf do systemd); `/api/tags` responde da LAN e da tailnet; ufw desligado; API permite pull/delete e uso de GPU; EVI usa Ollama em tarefas de fundo | Bind em `172.17.0.1` (host-gateway dos containers EVI e WhatBot); sudo |
| F6 | Chat principal + embeddings via Gemini, plano da chave não verificado | alto (provisório) | aberto — ação do usuário | `EVI_LLM_PROVIDER=gemini`, `EVI_EMBED_PROVIDER=google`; prompts com e-mail/WhatsApp de terceiros; tier gratuito pode treinar com os dados; a decisão de 2026-10-12 só aprovou nuvem via OpenRouter ZDR | Usuário verifica o plano; pago → aceito; gratuito → faturamento ou trocar provedor |
| F7 | Chat de controle do WhatsApp é um grupo; qualquer participante comanda o agente | médio | corrigido (3.3: só `from_me` no grupo de controle) | `EVI_WHATSAPP_CONTROL_JIDS`: 1 JID `@g.us`; `evolution_parser.py` `sender = remoteJid`; canal `whatsapp_control` ∈ `USER_CHANNELS`; grupo hoje com 1 participante | 3.3: exigir `from_me=True` (ou participante = dono) + teste |
| F8 | `EVI_REQUIRE_API_KEY` default `false`; `verify_api_key` é no-op sem chave | médio | corrigido (4.1) | compose `EVI_REQUIRE_API_KEY` default false; `agent/auth.py` | 4.1: default true + recusa de subir sem chave |
| F9 | SSH aceita senha; firewall do host desligado | médio | aberto — ação do usuário | `PreferredAuthentications=none` lista `publickey,password`; `ssh.socket` em `0.0.0.0:22`; sem `authorized_keys`; ufw `ENABLED=no` | Chave + `PasswordAuthentication no`; ufw (bind 127.0.0.1 segue como controle principal: Docker passa por fora do ufw) |
| F10 | WhatBot publica portas em `0.0.0.0` no mesmo host | médio | aberto — ação do usuário (fora do EVI) | `whatbot-redis-1` 6379 sem senha, `windmill_server` 8000, `evolution_api` 8080, `whatbot_ingress` 8090 | Prefixar `127.0.0.1:` no compose do WhatBot |
| F11 | Escopos OAuth Google além do necessário | médio | aberto — ação do usuário | resource `u/shiba144/stupendous_gcloud` (`cloud-platform`) sem uso em código; Gmail `modify` é necessário (`messages.trash`); Calendar via conector padrão (escopo amplo) | Apagar resource gcloud e variável; conferir conta Google; Calendar mínimo → BACKLOG |
| F12 | Windmill: login/usuários/tokens não verificados | médio | aberto — ação do usuário | Windmill CE cria `admin@windmill.dev` com senha padrão; token `WINDMILL_TOKEN` amplo; rota `telegram_to_evi` sem uso (`TELEGRAM_MODE=polling`); só loopback agora | Usuário verifica; se a senha padrão valer → alto até trocar |
| F13 | Sem backup de dados com estado; cópias antigas sem cifra | médio | BACKLOG | nenhum `pg_dump`/timer; `data/postgres.bak-20260812-*` e `data/postgres.broken-20260812` | BACKLOG: `pg_dump` diário + teste de restore; usuário decide sobre cópias antigas |
| F14 | `/metrics` sem chave; rótulo `path` com cardinalidade ilimitada | baixo | corrigido (4.1) | `curl localhost:8002/metrics` → 200; sem PII; `request.url.path` cru | 4.1: exigir chave e rotular por rota |
| F15 | `verify_api_key` com `!=` | baixo | corrigido (4.1) | `agent/auth.py` | `hmac.compare_digest` |
| F16 | Allowlist do Telegram fail-open | baixo | corrigido (4.1) | `telegram_handler.py` `_chat_allowed` aceita tudo se `TELEGRAM_CHAT_ID` vazio; em produção está definido | 4.1: fail-closed |
| F17 | Permissões abertas em data/logs/EVI_WORKSPACE | baixo | corrigido (2026-10-13: 750 nos diretórios; arquivos root-owned dentro seguem 644 — `sudo chown`) | 775 nos diretórios; `USER.md`/`MEMORY.md` 664; `logs/*.jsonl` 644 root:root | 3.2 (+ `sudo chown` para o que é root) |
| F18 | `agent-api` roda como root | baixo | BACKLOG | `docker exec … id` → uid=0 | `user: "1000:1000"` + posse dos volumes |
| F19 | 5 CVEs Python (pip-audit) | baixo | corrigido (3.3: pins bumpados; pip-audit limpo) | langgraph-sdk 0.4.2, multidict 6.7.1, urllib3 2.7.0 ×3; nenhuma alcançável neste uso | Bump compatível: sdk 0.4.4, multidict 6.9.1, urllib3 2.8.0 |
| F20 | `/jobs/import-contacts` lê qualquer path | baixo | BACKLOG | `vcard_import.py`; exige chave; não-vCard não devolve conteúdo | Restringir a `/workspace`, `/watched_folders` + `.vcf` |
| F21 | Logs com conteúdo integral | baixo | aceito | `evolution_webhook.jsonl`, `telegram.jsonl`; retenção 7 d / 5000 linhas; 0 linhas com padrão de segredo | Aceito |
| F22 | Resumo diário com LLM sem `wrap_external` | baixo | BACKLOG | `daily_summary.py`; só com `EVI_DAILY_SUMMARY_LLM=true` (desligado); sem tools | Envolver timeline |
| F23 | ruff `S` bloqueantes = falsos positivos | info | corrigido (4.2) | S608 em `db.py` (4) e `testing/cleanup.py` (4), `sim/runner.py` (2): interpolam constantes; S324 md5 de nome de arquivo | `noqa` com motivo; `usedforsecurity=False`; sem shell=True/eval/pickle/yaml.load no runtime |
| F24 | Histórico git: 2 falsos positivos (fixtures) | info | corrigido (4.2: allowlist) | fixture `sk-THIS…FAKE` em teste do scanner; `.env` nunca commitado | Allowlist no scanner |
| F25 | Pequenas exposições de informação | info | aceito | `/health` público: contagem de contatos, provedores; `/run-task`/`/insight` devolvem `str(e)` | Aceito (loopback + chave) |
| F26 | Tailscale: `serve` antigo; ACLs não verificadas | info | aberto — ação do usuário | `serve` em 443 → `:8094` (nada escuta); funnel off | Revisar/remover; ACLs no console |
| F27 | Spec base `remote-access` contradiz o delta | info | corrigido (5.1: MODIFIED no delta) | SCN-OPS-04 permite agent-api/windmill sem host IP | MODIFIED no delta antes do archive |
| F28 | Webhooks sem limite de taxa/tamanho | info | aceito | chave + só rede Docker/loopback; `MAX_PER_WEBHOOK`, dedupe, idade 2 h | Aceito |

## Checklist (design §2)

1. **Rede** — Compose só em loopback: OK (scan `binds.compose`). LAN/tailnet → 8001/8002: recusada (testado do próprio host; confirmar de outra máquina). Fora do compose: F5, F9, F10. Tailscale: F26.
2. **Autenticação/autorização** — Públicas: `/`, `/health` (F25), `/metrics` (F14). Todo o resto exige chave (scan `routes.auth`). `/run-task`: sem turno, o guard de canal libera escritas por desenho, mas a exclusão de e-mail exige sessão/turno + confirmação e não há tool de envio de mensagem; a chave é a fronteira. Webhook da Evolution: header `X-Api-Key`, só `MESSAGES_UPSERT`, webhook global desligado em 2026-10-13. Telegram: F16. Controle WhatsApp: F7.
3. **Segredos** — `.env` 600, nunca no histórico; padrões em uso (F3); permissões (F17); 0 segredos nos logs.
4. **Dependências e imagens** — F19, F4.
5. **Código** — Sem `shell=True`/`eval`/`pickle`/`yaml.load` no runtime; `subprocess` só em `testing/`; SQL só com constantes (F23); path livre em F20.
6. **LLM** — 17 tools `@guarded_write` = `WRITE_TOOLS`; só `graph.py` faz `bind_tools`, tarefas de fundo não têm tools; `wrap_external` nos caminhos de conteúdo de terceiros (lacuna F22); OpenRouter ZDR + deny fixos no código e teto diário fail-closed; Gemini F6.
7. **Dados em repouso e logs** — F21, F13, F17, F18.
8. **Integrações** — F11, F12; scripts Windmill: busca só lê, exclusão só `trash`.
9. **Operação** — `restart: unless-stopped` nos serviços; watchdog ativo; teto OpenRouter em código, chat Gemini sem teto (F6); backups F13.

## Correções propostas

F3, F17 → 3.2 · F7, F19 → 3.3 · F8, F14, F15, F16 → 4.1 · F4, F23, F24 → 4.2 · F27 → 5.1 ·
BACKLOG: F13, F18, F20, F22, F11 (Calendar).

## Ações do usuário

1. **F5** (sudo): `sudo systemctl edit ollama` → em `[Unit]`: `After=docker.service` e `Wants=docker.service`; em `[Service]`: `Environment="OLLAMA_HOST=172.17.0.1:11434"` (substitui o `0.0.0.0`); `sudo systemctl restart ollama`. Verificar: `ss -ltn 'sport = :11434'`; de dentro do container, `http://host.docker.internal:11434/api/version` responde 200; `curl -m3 http://192.168.15.32:11434/api/tags` falha. CLI no host: `export OLLAMA_HOST=172.17.0.1:11434`.
2. **F6**: ver o plano da chave em https://aistudio.google.com/apikey e informar (pago → aceito; gratuito → ativar faturamento ou trocar de provedor).
3. **F9** (sudo): instalar chave SSH primeiro (`ssh-copy-id`); depois `echo 'PasswordAuthentication no' | sudo tee /etc/ssh/sshd_config.d/10-evi-hardening.conf && sudo sshd -t && sudo systemctl restart ssh.socket`; ufw: `sudo ufw default deny incoming; sudo ufw allow from 192.168.15.0/24 to any port 22 proto tcp; sudo ufw allow in on tailscale0 to any port 22 proto tcp; sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp; sudo ufw enable`.
4. **F10**: no `docker-compose.yml` do WhatBot prefixar `127.0.0.1:` nas portas 6379/8000/8080/8090/11434 (e pôr senha no Redis); recriar.
5. **F11**: conferir https://myaccount.google.com/connections (sem `gmail.send` nem acesso total); apagar o resource `u/shiba144/stupendous_gcloud` no Windmill e `WINDMILL_GCLOUD_RESOURCE` do `.env`.
6. **F12**: no Windmill (via túnel, ver `docs/remote-access.md`): a senha padrão de `admin@windmill.dev` não funciona; só o seu usuário existe; só tokens em uso; desativar o trigger `telegram_to_evi`.
7. **F1/F2**: de outro dispositivo da LAN/tailnet, `curl -m3 -s -o /dev/null -w '%{http_code}\n' http://192.168.15.32:8002/health` e `:8001/` devem dar `000`.
8. **F26**: `tailscale serve status`; se sem uso, `tailscale serve --https=443 off`; ACLs em https://login.tailscale.com/admin/acls.
9. Definir limite de crédito na chave do OpenRouter (https://openrouter.ai/settings/keys).

## Estado ao arquivar (2026-10-13)

Corrigidos: F1, F2, F3, F4, F7, F8, F14–F17, F19, F23, F24, F27. BACKLOG: F13, F18, F20, F22, F11
(Calendar mínimo). Aceitos: F21, F25, F28. **Abertos, dependem do usuário:** F5 (alto, Ollama),
F6 (alto provisório, plano do Gemini), F9, F10, F11, F12, F26. Revisão de código adicional
(Opus) em 3.2 (2 rodadas) e 3.3/4.1; a revisão leve passa a ser regra em `openspec/config.yaml`.
Notas das revisões: um contato 1:1 que seja o JID de controle ainda comanda o agente (por
desenho — o JID de controle é confiável), e texto encaminhado dentro de uma mensagem `from_me`
é tratado como comando.

## Atualização de 2026-10-19

- **F11 (parcial):** o app OAuth foi publicado em **Produção** (fim da expiração de 7 dias; ver
  [`docs/google-oauth.md`](../google-oauth.md)). Os recursos Google foram recriados
  (`calendar`, `gtasks`, `gmail`); `gmail.modify` segue necessário e inclui, tecnicamente, a permissão
  de enviar — **risco aceito** (o EVI não tem ferramenta de envio). Reapareceu um recurso `gcloud`
  (`cloud-platform`) sem uso: apagar no Windmill e remover `WINDMILL_GCLOUD_RESOURCE` do `.env`.
- **Exposição pública:** o repositório `Seijin18/EVI` é público; só a branch `gh-pages` (página inicial e
  política de privacidade) foi publicada. **Não** dar `push` da `main` sem revisar: ela contém este
  registro, o modelo de ameaças e as revisões de uso.
- **Incidente operacional:** ao gravar as configurações OAuth da instância do Windmill com o formato
  errado do corpo (`{...}` em vez de `{"value": {...}}`), a configuração foi zerada por ~1 min e
  restaurada da cópia (`data/backups/windmill-oauths-pre-gmail-scopes-*`, 0600). Procedimento correto
  em `docs/google-oauth.md`.
- **F5 corrigido** no mesmo dia (o drop-in precisa se chamar `zz-evi-bind.conf`: o systemd lê em ordem alfabética e o `override.conf` com `0.0.0.0` vencia a primeira versão). No host, o CLI do Ollama passa a precisar de `export OLLAMA_HOST=172.17.0.1:11434`.
- **Abertos:** F6 (plano do Gemini: projetos Capy/EvolvingVirtualInteligence/WhatBot têm faturamento; o erro de teto de gasto de 13/10 só existe em projeto pago — falta confirmar qual projeto é dono da chave), F9, F10 (patch do WhatBot), F12, F26.
