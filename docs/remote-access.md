# Acesso remoto ao EVI

Desde o change `evi-security-review` (2026-10-12/13), **nenhuma porta do EVI é publicada
fora do host**: todas as portas do `docker-compose.yml` têm bind `127.0.0.1`
(requisito da spec `remote-access`, SCN-SEC-01; decisão do usuário registrada em
[`security/threat-model.md`](security/threat-model.md) §6, opção A).

| Porta no host | Serviço | Autenticação |
|---|---|---|
| `127.0.0.1:8001` | Windmill (UI + API; guarda os tokens OAuth do Google) | login do Windmill |
| `127.0.0.1:8002` | `agent-api` (FastAPI) | `X-Api-Key: $EVI_API_KEY` em todas as rotas exceto `/` e `/health` |
| `127.0.0.1:8082` | Evolution API | `apikey` |
| `127.0.0.1:5433`, `:6333`, `:7474/7687` | Postgres, Qdrant, Neo4j | senha/chave próprias |

O uso diário **não precisa** de acesso remoto: Telegram funciona por long polling (sem
porta de entrada) e o WhatsApp chega pela Evolution dentro da rede Docker. Acesso remoto
serve só para abrir a UI do Windmill ou chamar a API do agente de outro dispositivo.

Há duas formas aprovadas. Em ambas o agente **continua exigindo `EVI_API_KEY`** — o túnel
não substitui a chave.

## 1. Túnel SSH (sob demanda)

```bash
# Windmill em http://localhost:8001 no dispositivo remoto
ssh -N -L 8001:127.0.0.1:8001 marshibs@<host>

# agent-api em http://localhost:8002 no dispositivo remoto
ssh -N -L 8002:127.0.0.1:8002 marshibs@<host>
curl -H "X-Api-Key: $EVI_API_KEY" http://localhost:8002/tools
```

`<host>` é o IP da LAN (`192.168.15.32`) ou o nome/IP da tailnet. Use autenticação por
chave no SSH (ver `security/findings.md`, F9).

Para **reconectar OAuth do Google** no Windmill use o túnel SSH: o `BASE_URL` do Windmill e
os redirects cadastrados no Google Cloud Console são `http://localhost:8001/...`, que só
funcionam com o túnel na porta local 8001.

## 2. `tailscale serve` (só para a tailnet)

`tailscale serve` publica um serviço local **apenas para os dispositivos da sua tailnet**
(HTTPS com certificado da tailnet; nada vai para a internet — isso seria `tailscale
funnel`, que não deve ser usado aqui).

```bash
# Windmill em https://<nome-do-host>.<tailnet>.ts.net:8443
tailscale serve --bg --https=8443 http://127.0.0.1:8001

# agent-api em https://<nome-do-host>.<tailnet>.ts.net:8444 (continua exigindo X-Api-Key)
tailscale serve --bg --https=8444 http://127.0.0.1:8002

tailscale serve status                 # conferir o que está publicado
tailscale serve --https=8443 off       # remover
tailscale serve --https=8444 off
```

Notas:

- Qualquer nó da tailnet alcança o que for servido — confira as ACLs no console da
  Tailscale antes de ativar.
- O `agent-api` exposto assim ainda responde `401` sem `X-Api-Key`; o Windmill ainda pede
  login.
- Não use bind direto na interface `tailscale0` (`100.x.y.z:8001:8000` no compose): a spec
  exige `127.0.0.1` em todo bind e o Docker publica por fora do firewall do host.

## Verificação

```bash
ss -ltn | grep -E ':(8001|8002|8082|5433|6333)\b'     # todos em 127.0.0.1
./scripts/evi-security-scan                            # binds.compose / binds.host PASS
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8002/tools   # 401 sem chave
# de outro dispositivo da LAN/tailnet (sem túnel/serve): conexão recusada
curl -m3 -s -o /dev/null -w '%{http_code}\n' http://192.168.15.32:8002/health   # 000
```
