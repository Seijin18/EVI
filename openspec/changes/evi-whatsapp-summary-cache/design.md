## Context

- Tools `list_recent_whatsapp_messages(days=1, limit=40)` e
  `summarize_whatsapp_messages(days=1)` → `whatsapp_activity.list_recent_whatsapp` /
  `summarize_whatsapp` → `evolution_discovery.fetch_recent_whatsapp_messages(days, limit)`:
  `find_chats` (até 30) + `find_messages` por conversa (15 por conversa), em série; depois
  `conversation_lines` (agrupado por `canonical_jid`, `wrap_external`) e, no resumo, `build_llm`.
- Timeline local: `contact_memory/contacts/<jid>/timeline.jsonl`, escrita pelo webhook para
  mensagens diretas recebidas e (desde 13/10) enviadas pelo usuário (`[eu] …`), por jid
  canônico; grupos não têm pasta.

## Decisions

### 1. Leitura local por período
`message_timeline.recent_rows(days, limit)` percorre as pastas de contato (diretas,
canônicas, sem `*.merged-*`), lê só as linhas com `ts` no período (leitura do fim do arquivo
para trás, parando ao passar do corte) e devolve o mesmo formato de linha que
`fetch_recent_whatsapp_messages` (jid, rótulo, from_me, ts, texto), ordenado por ts.
Ignora entradas de compromisso duplicadas (mesma regra do `contact_knowledge._window_rows`).

### 2. Quando ainda ir à Evolution
- Grupos da whitelist: sempre Evolution (não há timeline de grupo).
- `days` maior que a cobertura local (primeira linha da timeline mais antiga do que o corte?
  não — se a timeline mais antiga começa depois do corte, a cobertura é parcial): completa com
  Evolution só para as conversas sem linhas locais no período, limitado a 10 conversas.
- Chamadas à Evolution em paralelo (`ThreadPoolExecutor`, `EVI_WHATSAPP_FETCH_WORKERS`=6),
  timeout total de 8 s; o que não voltar a tempo fica de fora com uma nota "(algumas conversas
  não puderam ser lidas)".
- `EVI_WHATSAPP_LOCAL_FIRST` (padrão `true`) volta ao comportamento antigo com `false`.

### 2b. As-built
Complemento pela Evolution só para grupos da whitelist e, quando a timeline local não tem
**nenhuma** entrada no período (instalação nova, dia sem mensagens ou WhatsApp desconectado),
o caminho completo da Evolution — agora em paralelo e com orçamento de 8 s, então o pior caso
cai de ~46 s para ~8 s. Resultado incompleto não entra no cache.

### 3. Cache do resumo
Chave `(days, último ts visto)`; TTL 10 min; mensagem nova muda a chave. Só o resumo (o LLM);
a listagem local já é rápida.

### 4. Segurança
Mesma delimitação de hoje (`conversation_lines` com `wrap_external`); o cache guarda a saída
já delimitada; nada de conteúdo de terceiros fora dos marcadores.

## Riscos

- Mensagens anteriores a 13/10 enviadas pelo usuário não estão na timeline: o resumo de 7 dias
  hoje ainda mistura; some com o tempo.
- Timeline só tem conversas que passaram pelo webhook: conversa iniciada enquanto o WhatsApp
  estava desconectado não aparece até a reconexão (igual à Evolution).
- RAM: nenhuma relevante (leitura em streaming).

## Out of scope

Pré-computar resumos no lote noturno; histórico completo de grupos.
