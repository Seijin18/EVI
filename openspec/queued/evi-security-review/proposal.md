## Why

O EVI lê e age sobre e-mail, agenda, tarefas e WhatsApp do usuário, guarda conversas de
terceiros em disco e agora manda trechos para LLMs na nuvem. Nunca houve revisão de
segurança do sistema montado. Uma varredura inicial (2026-10-12) já achou exposição real:

- **F1 (crítico)**: `agent-api` publicado em `0.0.0.0:8002` com `EVI_API_KEY` vazio —
  qualquer máquina da rede local (192.168.15.0/24) ou da tailnet chama `/chat`,
  `/run-task` (executa qualquer tool registrada: apagar e-mails, criar eventos…),
  `/webhooks/evolution` (injeta mensagens falsas de WhatsApp) e `/jobs/*` sem autenticação.
- **F2 (alto)**: Windmill em `0.0.0.0:8001` — guarda os tokens OAuth de Gmail (modify),
  Calendar e Tasks; credenciais de login não verificadas.
- **F3 (médio)**: segredos padrão em uso (`EVOLUTION_API_KEY=evi-dev-key`,
  `POSTGRES_PASSWORD=changeme`, `WINDMILL_DB_PASSWORD=windmill`), Qdrant sem chave —
  hoje só em `127.0.0.1`, mas sem defesa em profundidade.
- **F4 (médio)**: imagens sem versão fixa (`qdrant:latest`, `windmill:main`).

Prioridade: confiabilidade e confiança são pré-requisito de tudo que o EVI faz por conta
própria (briefing, promessas, conhecimento de contato).

## What Changes

- **Modelo de ameaças** do sistema montado (`docs/security/threat-model.md`): ativos,
  fronteiras de confiança, atacantes (rede local/tailnet, contato malicioso no WhatsApp,
  e-mail malicioso, dependência comprometida, provedor de LLM), superfícies.
- **Revisão guiada por checklist** + ferramentas (dependências, segredos no histórico,
  regras de segurança do ruff, imagens) → **registro de achados**
  (`docs/security/findings.md`) com severidade, evidência e decisão.
- **Correção de todo achado crítico/alto dentro do change**; médios/baixos viram itens do
  BACKLOG com dono e prazo.
- **Guardas de regressão**: o agente recusa subir publicado fora de `127.0.0.1` sem
  `EVI_API_KEY`; CI ganha `pip-audit`, varredura de segredos e regras `S` do ruff; o
  container smoke verifica 401 sem chave.
- Rotina: revisão leve a cada change que adicione superfície (registrado no
  `openspec/config.yaml`).

## Impact

Novo: `docs/security/threat-model.md`, `docs/security/findings.md`,
`scripts/evi-security-scan`, `tests/unit/test_security_guards.py`. Alterado:
`docker-compose.yml`, `agent/main.py` (guarda de inicialização), `.env.example`,
`.github/workflows/ci.yml`, `scripts/evi-container-smoke.sh`, `openspec/config.yaml`.
Specs: `remote-access`, `testing`. Sem container novo.

## Validação em uso real

- Varredura de portas a partir de outra máquina da rede/tailnet: nenhuma porta do EVI
  responde sem autenticação (antes: 8001, 8002).
- 0 achados críticos/altos abertos no registro ao arquivar.
- CI verde com os novos gates por 7 dias.

## Out of scope

- Pentest externo profissional.
- Criptografia de disco/volumes (responsabilidade do SO; registrar como recomendação).
- Reescrever o modelo de prompt injection (`evi-prompt-injection-model`, arquivado) —
  só verificar se as tools/tarefas novas respeitam a allowlist por origem.
