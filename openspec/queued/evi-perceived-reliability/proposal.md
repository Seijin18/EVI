## Why

A stack ficou ~6 semanas parada sem ninguém notar; quando uma tool demora (Gmail até
180 s) o usuário não sabe se o EVI travou; "o que você pode fazer?" depende do humor do
modelo. Itens pequenos e independentes que mudam a confiança no dia a dia. A sonda
diária (#46) já avisa OAuth expirado às 06:30; falta o aviso no momento em que o usuário
esbarra nele. Roadmap: Etapa 22.

## What Changes

- **Alerta "EVI fora do ar"**: `scripts/evi-watchdog` (fora do compose, timer systemd
  de usuário) chama `/health`; após 2 falhas seguidas manda direto pela API do Telegram,
  e avisa uma vez quando volta. Não depende do próprio EVI.
- **`/ajuda`** (e "o que você pode fazer?"): resposta curta e estável com 6–8 exemplos
  reais, montada sem LLM a partir das features ligadas.
- **Ack imediato**: tool que passa de `EVI_SLOW_ACK_SEC` (default 0 = desligado; sugerido
  5) manda "⏳ fazendo…" uma vez por turno, antes do resultado.
- **OAuth expirado no turno**: quando uma tool volta `reason=oauth`, o aviso com o
  caminho de reconexão do Windmill sai na hora, uma vez por integração por dia
  (mesmo controle da sonda).

## Impact

Novo: `scripts/evi-watchdog`, `scripts/systemd/evi-watchdog.service`,
`scripts/systemd/evi-watchdog.timer`, `agent/services/help_text.py`,
`agent/services/slow_ack.py`. Alterado: `agent/services/chat_commands.py`,
`agent/services/turn_log.py`, `agent/services/tool_result.py`, `agent/services/probe.py`,
`EVI_WORKSPACE/AGENTS.md`, `.env.example`, `docs/`. Spec: `agent-api`. Sem container novo.

## Validação em uso real

7 dias após instalar o timer e ligar `EVI_SLOW_ACK_SEC`:
- uma parada induzida (`docker compose stop agent-api`) gera alerta em ≤ 3 min e aviso
  de volta;
- turnos com tool > 5 s recebem ack em 100% dos casos (`turn_log`);
- `/ajuda` usado ao menos uma vez sem reclamação (`/ruim`).

## Out of scope

- Tarefas longas desacopladas do turno (é o #38, condicional).
- Monitoramento de Windmill/Evolution além do que o `/health` já cobre.
- Alertas por outro canal que não o Telegram.
