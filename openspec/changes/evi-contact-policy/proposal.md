## Why

O usuário quer decidir **de quem o EVI lê e para quem pode enviar**, por contato e por grupo,
e quer **todo grupo fora** até pedir para liberar (decisão de 20/10, `docs/drafts/brainstorm-assistente-2026-10-20.md` §11).
Hoje só existe `EVI_WHATSAPP_SKIP_GROUPS` + `EVI_WHATSAPP_GROUP_WHITELIST` no `.env` (estático,
exige reiniciar). Contato individual não tem controle nenhum. O webhook grava estado de
conversa, promessas e um trecho do texto no trace **antes** do filtro. E o caminho de envio
(`send_whatsapp_text`) não tem nenhuma guarda de destinatário. Isso é pré-requisito de
privacidade para o envio direto que vem depois na fila.
Prioridade: primeiro da fila de 20/10 (0 chamadas de LLM).

## What Changes

- Tabela `contact_policy` (JID canônico ou grupo; `ingest`, `send`; quem mudou e quando).
  Padrão: contato direto lê e pode receber; **grupo não lê e não recebe** até ser liberado.
- **Portão de ingestão** logo após o parse do webhook, antes de estado de conversa, promessas,
  timeline, extração e trace com texto. A mensagem bloqueada é descartada com `reason: policy`
  e **sem trecho do texto**.
- **Guarda de envio** em `send_whatsapp_text`: recusa destinatário com `send` desligado ou grupo
  não liberado. O chat de controle continua sempre permitido.
- **Comandos determinísticos no Telegram**, sem LLM e com confirmação mostrando nome + número:
  parar/voltar a ler, bloquear/permitir envio, liberar/bloquear grupo, `/privacidade`.
- Bloquear a leitura **oferece apagar** o que já foi guardado do contato. Só apaga com "sim".
- `EVI_WHATSAPP_GROUP_WHITELIST` vira semente da tabela; a Evolution passa a entregar grupos e
  o EVI filtra.

## Impact

Novo: `agent/services/contact_policy.py`. Alterado: `agent/db.py`, `agent/main.py` (webhook),
`agent/services/evolution_filter.py`, `agent/services/evolution_discovery.py`,
`agent/services/evolution_client.py`, `agent/services/telegram_handler.py`,
`agent/services/chat_commands.py`, `scripts/setup-evolution.sh`, docs. Specs:
`messaging-whatsapp`. Sem container novo; **sem LLM**.

## Validação em uso real

Janela de 7 dias: 0 linhas novas de JID bloqueado em qualquer armazenamento (timeline,
`wa_conversation_state`, `pending_commitments`), conferido pela sonda diária; 0 envio a JID
bloqueado; comandos de política resolvidos sem LLM em 100 % das vezes.

## Out of scope

- Política de e-mail por remetente/domínio (change próprio, se aparecer como lacuna).
- Escopo "só arquivos" para grupo (depende do tratamento de arquivos; ver `evi-study-calendar`).
- Envio direto a terceiros (`evi-direct-send`, mais adiante na fila).
- Tela de configuração (planejada na interface futura).
