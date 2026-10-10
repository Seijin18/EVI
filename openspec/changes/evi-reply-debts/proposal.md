## Why

A extração de "compromissos" do WhatsApp teve 0 confirmações em 37 itens: chegam sem
data ("Jantar"), sem sentido ("baixeii pra te mandar") ou sem contexto para decidir, e
cada um vira uma notificação avulsa. O alvo estava errado, não o limiar. O que a pessoa
precisa saber do WhatsApp é **quem está esperando resposta dela**, **o que ela prometeu**
e **o que foi combinado com data**. Referência: Superhuman Auto Reminders. Roadmap:
Etapa 20; análise em [`docs/ux-review-2026-10.md`](../../../docs/ux-review-2026-10.md) (P3).

## What Changes

- **Esperando sua resposta** (determinístico, sem LLM): estado por conversa direta
  (última mensagem recebida × última enviada pelo usuário). Conversa cuja última
  mensagem é do contato há mais de `EVI_REPLY_DEBT_HOURS` (default 4 h) e menos de 7
  dias é uma pendência. Exige registrar mensagens `fromMe` **só para o estado** — elas
  continuam fora da extração.
- **Promessas suas**: mensagens enviadas pelo usuário com padrão de compromisso
  ("te mando amanhã", "vejo e te falo", "te aviso") viram itens `promise`, por heurística.
- **Combinados com data**: a extração atual passa a guardar como visíveis só os itens
  com data resolvida; os sem data ficam `undated` (fora do briefing e das notificações).
- O briefing troca a seção "WhatsApp" por três subseções numeradas; cada item com trecho
  (`wrap_external`), data e ação de um toque ("respondido", "feito", "confirma N",
  "dispensa N"). A notificação avulsa de captura deixa de existir.
- Tudo atrás de `EVI_REPLY_DEBTS_ENABLED` (default `false`); o registro do estado das
  conversas roda sempre, para acumular histórico.
- Taxa de confirmação por tipo no relatório semanal.

## Impact

Novo: `agent/services/reply_debts.py`, `agent/services/promises.py`,
`agent/tools/reply_debt_tools.py`, `tests/sim/scenarios/reply-debts/`,
`tests/fixtures/evolution/messages_upsert_from_me.json`.
Alterado: `agent/db.py`, `agent/main.py` (webhook), `agent/services/whatsapp_processor.py`,
`agent/services/briefing.py`, `agent/services/commitment_capture_notify.py`,
`agent/services/commitment_review/deliver.py`, `agent/tools/registry.py`,
`agent/services/usage_report.py`, `EVI_WORKSPACE/AGENTS.md`, `.env.example`.
Specs: `messaging-whatsapp`, `proactive`. Sem container novo.

## Validação em uso real

Janela de 14 dias após ligar `EVI_REPLY_DEBTS_ENABLED`, pelo relatório semanal:
- taxa de ação (respondido/feito/confirmado) por tipo ≥ 30% para "esperando resposta";
- **decisão embutida**: se promessas + combinados ficarem abaixo de 30% de confirmação,
  desligar a extração por LLM (`EVI_WHATSAPP_LLM_EXTRACT=false`) e manter só (a);
- nenhuma conversa de grupo ou do chat de controle aparece como pendência.

## Out of scope

- Responder pelo EVI no WhatsApp (envio a terceiros) — continua fora.
- Pendências em grupos.
- Extração de promessas por LLM (só heurística nesta versão).
- Apagar ou migrar os 37 compromissos antigos: ficam como estão; os sem data passam a
  `undated` só se a flag estiver ligada e um job de migração for rodado manualmente.
