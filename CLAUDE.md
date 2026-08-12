# EVI — instruções para agentes de código

Assistente pessoal local-first: FastAPI + LangGraph ReAct, Windmill como hub de
integrações Google, WhatsApp via Evolution API, Telegram. Ver [`README.md`](README.md)
para arquitetura e [`openspec/specs/`](openspec/specs/) para requisitos normativos.

As instruções globais em `~/.claude/CLAUDE.md` valem aqui; este arquivo detalha
como aplicá-las neste repositório.

## OpenSpec — fonte de verdade do planejamento

Este projeto usa OpenSpec (`openspec/`). CLI instalado: `openspec`.

- **Antes de qualquer mudança não-trivial:** ler [`openspec/AGENTS.md`](openspec/AGENTS.md)
  e [`openspec/config.yaml`](openspec/config.yaml) (contexto, regras de proposal/tasks/design).
- **Um change ativo por vez.** `openspec list` deve estar vazio antes de
  `openspec new change <slug-kebab>`.
- Fluxo: propor (`proposal.md` + `tasks.md` + specs delta) → implementar marcando
  tasks `[x]` conforme o Verify passa → sincronizar specs com o as-built →
  `openspec archive` para `openspec/changes/archive/YYYY-MM-DD-<slug>/`.
- Cada task deve trazer `SCN-*` (quando aplicável), `Files:` (máx. 5 paths) e
  `Verify:` (comando `./scripts/evi-test <feature>`).
- Ao arquivar, atualizar [`openspec/BACKLOG.md`](openspec/BACKLOG.md) e
  [`Progress.md`](Progress.md) (etapa + matriz de features).
- `openspec validate --specs` deve passar (9 specs) antes de fechar um change.

Fonte de verdade é `openspec/specs/`, **não** `Progress.md` nem `README.md` —
esses são resumo/overview e podem estar defasados.

## MCP: codebase-memory

Servidor declarado em [`.mcp.json`](.mcp.json). Projeto no grafo:
`home-marshibs-Projects-EVI` (repo `/home/marshibs/Projects/EVI`).

Use para perguntas **estruturais** — "quem chama X", "quais tools existem",
"quem depende deste módulo", visão de arquitetura — em vez de grep arquivo a
arquivo ou de disparar um agente de exploração:

1. `index_status` — confirmar que o índice existe e não está defasado em relação
   ao HEAD. Se vazio: `index_repository(repo_path="/home/marshibs/Projects/EVI", mode="fast")`.
   Não reindexar a cada mensagem; só após refactor grande ou pedido explícito.
2. `get_architecture` — visão geral (rotas FastAPI, pacotes, hotspots) antes de
   mexer em área desconhecida.
3. `search_code` / `search_graph` — localizar símbolos por significado.
4. `query_graph` / `trace_path` — "quem chama quem", caminho entre X e Y.
5. `get_code_snippet` — validar o trecho real antes de citar um path num plano.

`Read`/`grep` continuam para busca literal (uma string, um TODO), diffs finos e
arquivos fora do índice (`.md`, `.env.example`, `scripts/`, `windmill/`).

## MCP: context-mode

Servidor declarado em [`.mcp.json`](.mcp.json). Prefira
`mcp__context-mode__ctx_execute` / `ctx_batch_execute` a `Bash` quando o comando
gerar **saída grande** e o objetivo for derivar uma resposta dela (filtrar,
contar, resumir) — só o que for impresso explicitamente entra na conversa.

Casos típicos neste repo:

- agregar `logs/evolution_webhook.jsonl` (milhares de linhas) por `step`/`reason`;
- varrer `EVI_WORKSPACE/memory/*.md` ou `data/contact_memory/**/timeline.jsonl`;
- contar/classificar em massa sobre `agent/**/*.py` ou a suíte de testes.

**Não usar** para comando único e curto (`git status`, `docker compose ps`,
`openspec list`) nem quando o conteúdo bruto exato é necessário no passo
seguinte (ler um arquivo antes de editar — use `Read`).

## Convenções do código

- Tools LangGraph em `agent/tools/`; **sempre** registrar em
  [`agent/tools/registry.py`](agent/tools/registry.py) (registro único —
  `main.py` e `graph.py` consomem `get_all_tools()`).
- Serviços em `agent/services/`; providers plugáveis em `agent/llm.py`,
  `agent/integrations/`, `agent/messaging/`.
- Segredos só em `.env` (gitignored). Nunca commitar `.env`, `data/`,
  `logs/`, `EVI_WORKSPACE/MEMORY.md`, `EVI_WORKSPACE/USER.md`.
- Memória de chat é limitada (`BoundedMemory`, 8 pares) — não assumir histórico longo.
- Alvo de hardware: 16 GB RAM / GTX 1060 3 GB. Novo container precisa de
  justificativa de RAM no `design.md` do change.

## Verificação

```bash
PYTHONPATH=agent python3 -m pytest tests/unit -q   # Tier 1 (~280 testes)
./scripts/evi-test smoke                            # Tier 2 offline
./scripts/evi-test runtime-v3 && ./scripts/evi-test inbox-ux
openspec validate --specs
ruff check agent/ --select E,W,F --ignore E501      # mesmo gate do CI
```

CI (`.github/workflows/ci.yml`) roda ruff + unit + smoke + tier-2 offline, e um
job `container` separado com `./scripts/evi-container-smoke.sh`.
Não fechar um change com CI vermelho.

## Commits

Pré-autorizado criar commits locais ao fechar uma unidade coerente de trabalho
(um `tasks.md` concluído, um bug corrigido e verificado). `push` continua
exigindo pedido explícito. Seguir o estilo do `git log` (`feat(escopo):`,
`fix(escopo):`, `chore:`, `docs:`).
