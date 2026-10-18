## Why

Lembretes e voz existem desde 10/10 e tiveram **zero** uso na primeira semana (validações de
17/10 não atingidas, `docs/product-review-2026-10-18.md`). Não é falha técnica: o usuário não
sabe que pode. Na Zapia (referência) lembrete e áudio são o mínimo esperado; o Google CC e o
ChatGPT Pulse mostram que a prévia do dia seguinte é parte do hábito. A prévia da noite já
existe no código (`kind=evening`) e nunca foi agendada.

## What Changes

- **Dica rotativa** numa linha no rodapé do briefing da manhã: uma capacidade que o usuário
  ainda não usou (ou não usa há 14 dias) — lembrete, áudio, "o que você sabe sobre X",
  tarefas agendadas quando existirem — com uma frase de exemplo pronta para copiar. Some
  depois que a capacidade é usada.
- **Prévia da noite às 21h** (schedule ligado, decisão do usuário em 18/10): o briefing
  `kind=evening` com o que vence amanhã e, para itens com prazo amanhã, um botão/frase
  "me lembra amanhã às 9h de …".
- Flags `EVI_BRIEFING_TIPS` e o schedule `briefing_evening` (ligados).

## Impact

Alterado: `agent/services/briefing.py`, novo `agent/services/discovery_tips.py`,
`agent/db.py` (consulta de uso por capacidade no `turn_log`), `windmill/f/integrations/`
(`briefing_evening.schedule.yaml`), testes e simulação. Specs: `proactive`. Sem container novo;
sem LLM.

## Validação em uso real

Janela de 7 dias: ≥ 3 lembretes criados e ≥ 1 turno por voz; prévia da noite entregue em
≥ 6/7 dias.

## Out of scope

- Onboarding interativo; mudar o `/ajuda`.
