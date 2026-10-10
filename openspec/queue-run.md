# Execução da fila — iniciada 2026-10-10
## Estado
- Change atual: evi-usage-validation (fase: implementar) — task 1.1
- Ordem: evi-sim-harness → evi-usage-validation → evi-morning-briefing → evi-reminders → evi-reply-debts → evi-voice-input → evi-perceived-reliability → evi-prompt-injection-model
- Concluídos: evi-sim-harness (arquivado 2026-10-10, commits 346030b..a5a8da5)
- Pulados: evi-background-execution (#38) — condicional: "abrir só se o ack imediato do #44 não bastar na prática"; exige dados de uso real
## Decisões tomadas sem o usuário
- 2026-10-10 fila: agentes de projeto (`.claude/agents/`) não estão registrados nesta sessão; usados via `general-purpose` com `model` equivalente (haiku/sonnet/opus) e instrução de seguir o arquivo do agente.
- 2026-10-10 evi-sim-harness: (decisão do usuário no preflight) sem chave Gemini separada; `evi-sim` usa `EVI_SIM_GEMINI_API_KEY` se definida, senão repassa `GEMINI_API_KEY` do `.env` com aviso. Cota de produção compartilhada → `--max-llm-calls` mantido.
- 2026-10-10 evi-sim-harness 2.2: achados do fake Windmill — (a) `delete_emails.py` engole o corpo do erro do Google ("HTTP 401") e OAuth expirado vira `upstream_error`; (b) HTTP 500 do Windmill chega ao `parse_windmill_result` como `unparseable`. Corrigir na 3.4 (cenários de falha) se o cenário exigir.
- 2026-10-10 evi-sim-harness 3.3: fake Windmill passava `action` (sempre enviado pelo cliente) ao `main()` do script → TypeError; corrigido no fake (Windmill real descarta chaves não declaradas).
- 2026-10-10 evi-sim-harness 3.3: SIM-RU-09 reescrito ("reunião de condomínio" → "reunião com o síndico") porque o extrator heurístico descarta título genérico "Reunião" e o fallback Ollama está desligado na sim. Comportamento do extrator fica para `evi-reply-debts` (#42), que repensa a extração.
- 2026-10-10 evi-sim-harness 3.3: SIM-RU-08 1/3 — modelo pedia número completo em vez de chamar `set_whatsapp_contact_name` com final; docstring da tool ajustada (aceita últimos dígitos, chamar direto).
- 2026-10-10 evi-sim-harness: SIM-RU-05 travou 1/3 live (uma chamada ao Gemini sem retorno em 90 s) → `EVI_LLM_TIMEOUT_SEC` (default 60) no cliente Gemini. Muda produção: turno que antes travava agora tem retry após 60 s.
- 2026-10-10 evi-usage-validation (sync): nome e telefone reais em SCN-USE-04/07 trocados por fictícios; Verify de 1.1 com PG efêmero em container descartável (`evi-unit-pg`); cenários SIM-USE-01/02 adicionados às tasks 1.2 e 2.1.
## Pendências do usuário (não bloqueantes)
- [ ] Criar projeto Gemini separado e definir `EVI_SIM_GEMINI_API_KEY` no `.env` — a simulação hoje consome a cota de produção — `.env`
- [ ] `EVI_WORKSPACE/agenda.vcf` (não versionado, não ignorado) contém contatos reais — mover para fora do repo ou adicionar ao `.gitignore`; nunca foi staged pela fila — `EVI_WORKSPACE/agenda.vcf`
## Bloqueios
- —
