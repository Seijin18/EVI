## Why

A próxima fase do EVI ("de avisa para resolve", `docs/drafts/brainstorm-assistente-2026-10-20.md`
§2) depende de um lugar único onde o que o EVI **preparou** espera o **ok** do usuário. Os changes
anteriores criam confirmações avulsas: política de contato (`p1:`), apagar dados, publicar grade,
associar material e triagem de lacunas (`g1:`). Cada uma tem seu formato e nenhuma lista o que
está pendente. Rascunhos de resposta, rascunhos de e-mail e envio direto (LLM, mais adiante)
precisam de aprovação, edição, expiração e rastro desde o primeiro dia.

## What Changes

- Modelo `proposals` (tipo, resumo, payload, origem, estado, versão, criada/expira/decidida) e
  **uma** mensagem de Telegram por proposta, com ✅ / ✏️ (quando o tipo aceita edição) / ✖ e
  `callback_data` único `a1:<id>:<v>:<ação>`.
- As confirmações dos changes anteriores passam a ser propostas (mesmo comportamento, um só
  mecanismo). Um registro de executores por tipo roda a ação **em código**, só depois do ✅.
- `/pendentes` lista o que espera o usuário. O briefing ganha "🗂 Aguardando você (N)" quando N > 0.
- Expiração por tipo (proposta vencida some com aviso no rastro, nunca executa).
- Níveis de autonomia por tipo (`L0` só avisa · `L1` prepara e espera · `L2` faz com desfazer),
  todos em `L1` neste change. O nível só muda por comando do usuário.
- API somente leitura + ação para a interface futura: `GET /v1/proposals`,
  `POST /v1/proposals/{id}/{approve|reject}` (com `X-Api-Key`).

## Impact

Novo: `agent/services/proposals.py`. Alterado: `agent/db.py`,
`agent/services/telegram_handler.py`, `agent/services/briefing.py`,
`agent/services/chat_commands.py`, `agent/main.py`, e os pontos de confirmação de
`contact_policy`, `study` e `capability_gaps`. Spec: `proactive`. Sem container novo; **sem LLM**.

## Validação em uso real

Janela de 14 dias: 100 % das confirmações passando por `proposals` (nenhum `p1:`/`g1:` avulso
restante); 0 proposta executada sem ✅ ou depois de expirar; tempo mediano até a decisão
registrado como linha de base para os rascunhos.

## Out of scope

- Produzir rascunhos (resposta, e-mail): `evi-reply-drafts`.
- Níveis `L2`/`L3` ativos para algum tipo; envio a terceiros.
- Tela de interface (só a API).
