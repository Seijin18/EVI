## Why

Na primeira semana o briefing chegou 8/8 manhãs e foi respondido em 2 (25 %; meta 50 %),
e só 1 de 7 dívidas de resposta teve ação (`docs/product-review-2026-10-18.md`). Agir hoje
exige digitar "respondido 2" ou "confirma 3". No Google CC (referência), a pessoa age sobre
o briefing com um toque e dá 👍/👎 em cada mensagem. O `evi-ux-review` deixou botões como
recomendação; os dados agora justificam.

## What Changes

- **Botões inline** nos itens acionáveis do briefing: dívida de resposta (✅ respondido ·
  ✖ ignorar), promessa/combinado (✅ confirmar · ✖ dispensar), conversa sem nome
  (✖ ignorar). Uma linha de botões por item visível, rótulo com o número do item.
- **👍 / 👎** no rodapé do briefing, gravados no `briefing_log`.
- O toque executa o **mesmo código determinístico** das respostas por número (sem LLM),
  confirma com um aviso curto e troca os botões do item por "✓ feito".
- `callback_query` só do chat do usuário; o dado do botão é curto (dia + número + ação),
  resolvido pelo snapshot do briefing; nunca carrega texto de terceiros.
- Flag `EVI_BRIEFING_BUTTONS` (padrão ligado — decisão do usuário em 18/10).

## Impact

Alterado: `agent/services/telegram_notify.py` (reply_markup, answerCallbackQuery,
editMessageReplyMarkup), `agent/services/telegram_poller.py` (`allowed_updates`),
`agent/services/telegram_handler.py` (callback), `agent/services/briefing.py`
(teclado), `agent/db.py` (`briefing_log.feedback`), fake do Telegram na simulação.
Specs: `proactive`. Sem container novo; sem LLM.

## Validação em uso real

Janela de 7 dias: briefing com resposta (texto ou toque) em ≥ 50 % dos dias; ação em
dívidas de resposta ≥ 30 %; ≥ 3 avaliações 👍/👎.

## Out of scope

- Botões fora do briefing (listas, lembretes) — próximo passo se funcionar.
- Agendar evento por botão com escolha de horário (só confirmação simples).
