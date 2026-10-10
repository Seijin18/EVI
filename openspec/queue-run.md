# Execução da fila — iniciada 2026-10-10
## Estado
- Change atual: evi-sim-harness (fase: implementar) — task 1.2 (2.1 em paralelo)
- Ordem: evi-sim-harness → evi-usage-validation → evi-morning-briefing → evi-reminders → evi-reply-debts → evi-voice-input → evi-perceived-reliability → evi-prompt-injection-model
- Concluídos: —
- Pulados: evi-background-execution (#38) — condicional: "abrir só se o ack imediato do #44 não bastar na prática"; exige dados de uso real
## Decisões tomadas sem o usuário
- 2026-10-10 fila: agentes de projeto (`.claude/agents/`) não estão registrados nesta sessão; usados via `general-purpose` com `model` equivalente (haiku/sonnet/opus) e instrução de seguir o arquivo do agente.
- 2026-10-10 evi-sim-harness: (decisão do usuário no preflight) sem chave Gemini separada; `evi-sim` usa `EVI_SIM_GEMINI_API_KEY` se definida, senão repassa `GEMINI_API_KEY` do `.env` com aviso. Cota de produção compartilhada → `--max-llm-calls` mantido.
- 2026-10-10 evi-sim-harness 2.2: achados do fake Windmill — (a) `delete_emails.py` engole o corpo do erro do Google ("HTTP 401") e OAuth expirado vira `upstream_error`; (b) HTTP 500 do Windmill chega ao `parse_windmill_result` como `unparseable`. Corrigir na 3.4 (cenários de falha) se o cenário exigir.
## Pendências do usuário (não bloqueantes)
- [ ] Criar projeto Gemini separado e definir `EVI_SIM_GEMINI_API_KEY` no `.env` — a simulação hoje consome a cota de produção — `.env`
## Bloqueios
- —
