## Why

O briefing (#40) entregou a parte mínima da defesa contra injeção de prompt:
conteúdo de terceiros delimitado e regras no bootstrap. A defesa ainda depende do
modelo obedecer: `delete_emails` executa na primeira chamada, `delete_emails_by_query`
aceita qualquer `max_messages`, e as saídas de `summarize_inbox`/`list_calendar_events`
chegam ao grafo sem delimitação. Com o raciocínio do modelo limitado por custo, garantias
precisam estar no código. Roadmap: Etapa 23 (reduzido).

## What Changes

- **Confirmação em dois passos para exclusão**: `delete_emails*` primeiro devolve uma
  prévia (quantos, assuntos delimitados) e um token; a exclusão só ocorre num turno
  **seguinte** do mesmo usuário com confirmação explícita ("sim", "confirma", "pode
  apagar"), verificada no código. `max_messages` limitado a 50.
- **Allowlist de tools por origem do turno**: turnos que não vêm do usuário (jobs,
  canais de fundo) não têm tools de escrita; verificado no código, não no prompt.
- **Saídas de tools delimitadas**: assunto/remetente em `summarize_inbox` e títulos de
  eventos em `list_calendar_events` passam por `wrap_external`.
- **Corpus adversarial** em `tests/fixtures/injection/` + `evi-test injection` (offline) +
  cenários de simulação novos.

## Impact

Novo: `agent/services/write_guard.py`, `tests/fixtures/injection/`. Alterado:
`agent/tools/email_tool.py`, `agent/services/response_format.py`,
`agent/tools/calendar_tool.py`, `agent/tools/registry.py`, `agent/services/turn_log.py`,
`agent/testing/cli.py`, `EVI_WORKSPACE/AGENTS.md`, `tests/sim/scenarios/adversarial/`.
Spec: `agent-api`. Sem container novo; sem flag (correção de segurança, comportamento
visível só ao apagar e-mails).

## Validação em uso real

7 dias: nenhuma exclusão de e-mail sem turno de confirmação no `turn_log`; taxa de
sucesso dos turnos de e-mail sem queda em relação à semana anterior.

## Out of scope

- Classificador de injeção por LLM.
- Confirmação para `schedule_event`/`create_task` (reversíveis pelo usuário).
- Isolamento de memória de longo prazo contra envenenamento (perfis de contato) além da
  delimitação existente.
