## Context

- `assemble_briefing(kind)`: `kind="evening"` monta a prévia de amanhã (agenda e tarefas de
  amanhã; sem atrasadas). `deliver_briefing` é idempotente por (dia, tipo). Só o schedule
  `briefing_morning` (07:00) existe.
- Uso por capacidade dá para medir no `turn_log`: `tools` (nomes das tools chamadas, ex.
  `create_reminder`, `get_whatsapp_contact_info`), `input_kind` (`voice`, `button`).
- Botões do briefing (`evi-briefing-buttons`) e o teto de 25 linhas.

## Decisions

### 1. Catálogo de dicas
`discovery_tips.TIPS`: lista ordenada de `(id, detector, texto)`:
1. `reminder` — usado se `create_reminder` apareceu nos últimos 14 dias; texto
   "💡 Dica: diga \"me lembra às 18h de pagar o boleto\" e eu aviso aqui."
2. `voice` — usado se houve `input_kind='voice'`; "💡 Dica: pode mandar áudio — eu entendo."
3. `contact` — `get_whatsapp_contact_info`; "💡 Dica: pergunte \"o que você sabe sobre a Ana?\""
4. `buttons` — `input_kind='button'`; "💡 Dica: toque ✅ ou ✖ nos itens para resolver sem digitar."
A primeira não usada aparece; rotação por dia entre as não usadas; nenhuma → sem linha.
Conta no teto de linhas (última a sair quando falta espaço).

### 2. Prévia da noite
Schedule `briefing_evening` às 21:00 (`kind=evening`), **ligado**. Itens com prazo amanhã
(tarefas, promessas, combinados) ganham a ação "🔔 lembrar amanhã 9h" (botão quando os
botões estão ligados; senão a frase "responda 'lembra N'"). O toque cria um lembrete pelo
mesmo código de `create_reminder` (amanhã 09:00 local, texto = título do item, sem conteúdo
de terceiros além do título já mostrado). Noite sem itens: "Amanhã está livre." (uma linha).

### 3. Flags
`EVI_BRIEFING_TIPS` (padrão `true`). A prévia da noite é controlada pelo schedule (Windmill).

## Riscos

- Dica repetitiva: só aparece enquanto a capacidade não foi usada; uma linha.
- Mensagem a mais por dia (noite): decisão do usuário; desligável no schedule.

## Out of scope

Onboarding; mudanças no `/ajuda`.
