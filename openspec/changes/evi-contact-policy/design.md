## Context

- Webhook Evolution (`agent/main.py`, ~l. 477–720): `parse_evolution_webhook` → laço que separa
  controle, áudio e `ingest_raw` → `track_conversation` + `capture_promises` (**antes** do filtro)
  → `filter_for_processing` (grupos, `fromMe`, idade, dedupe) → `WhatsAppProcessor` (extração
  LLM) → `message_timeline.record_whatsapp_messages` → compromissos/grafo/notificação.
- O parser já grava o alias `@lid`↔telefone (`contact_identity.record_alias_from_message`), que
  é só identidade, sem conteúdo. O JID canônico vem de `contact_identity.canonical_jid`.
- Trace `logs/evolution_webhook.jsonl`: itens descartados levam `raw_preview` (80 caracteres).
- Grupos: `EVI_WHATSAPP_SKIP_GROUPS` (padrão true) + `EVI_WHATSAPP_GROUP_WHITELIST`, lidos em
  `evolution_filter._parse_group_whitelist` e em `evolution_discovery` (l. 252/258/338).
  `setup-evolution.sh` só desliga `groupsIgnore` quando há whitelist.
- Envio: `evolution_client.send_whatsapp_text` → `messaging/evolution.py:send_text`. Hoje só é
  usado para o chat de controle, sem guarda de destinatário.
- Comandos determinísticos: `chat_commands.try_chat_command` e os `try_*_reply` do
  `telegram_handler.process_telegram_update`; confirmação com "sim" na mensagem seguinte já
  existe no fluxo de exclusão de e-mail (`evi-prompt-injection-model`).

## Decisions

### 1. Modelo
`contact_policy(jid text primary key, kind text check in ('direct','group'), ingest bool, send bool,
label text, updated_at timestamptz, updated_by text)`. A **ausência de linha = padrão**:
`direct` → `ingest=true, send=true`; `group` → `ingest=false, send=false`. `send=true` aqui só
significa "não bloqueado". Enviar a terceiros continua proibido até `evi-direct-send`; a guarda
deste change é uma camada a mais, não uma autorização. O JID é sempre o canônico
(`canonical_jid`), então `@lid` e telefone compartilham a política.

`contact_policy.py`: `ingest_allowed(jid)`, `send_allowed(jid)`, `set_policy(jid, *, ingest=None,
send=None, by)`, `list_restricted()`, cache em memória de 60 s invalidado por `set_policy`.

### 2. Portão de ingestão
No laço do webhook, **antes** de separar `ingest_raw`/áudio: se `not ingest_allowed(remote_jid)`,
a mensagem é descartada com trace `{step: drop, reason: policy, is_group, sender_hash}`, **sem**
`raw_preview` nem texto. Vale para mensagens recebidas e `fromMe` (a conversa inteira some).
O chat de controle não passa pelo portão. O filtro de grupos do `evolution_filter` passa a
perguntar a `ingest_allowed` em vez da whitelist. `EVI_WHATSAPP_SKIP_GROUPS=false` continua
significando "todos os grupos liberados" (compatibilidade), mas o padrão segue true.

### 3. Semente e Evolution
Na migração, cada JID de `EVI_WHATSAPP_GROUP_WHITELIST` vira linha `group, ingest=true,
send=false, updated_by='env-seed'`, só se ainda não existir. `setup-evolution.sh` passa a
`groupsIgnore=false` sempre: a Evolution entrega os grupos e o portão descarta. O custo é
CPU de webhook (sem LLM, sem gravação). O `.env.example` marca a whitelist como "semente
inicial; use os comandos". `evolution_discovery` lê a política.

### 4. Guarda de envio
`send_whatsapp_text(jid, text)`: se o destino não é JID de controle e `not send_allowed(jid)`,
não envia, registra `reason: policy_send_blocked` e devolve falha (`ToolResult` com `ok=False`).
Grupo sem linha = bloqueado.

### 5. Comandos (Telegram, determinísticos)
| Texto | Efeito |
|---|---|
| `para de ler <alvo>` / `volta a ler <alvo>` | `ingest` off/on |
| `não envia para <alvo>` / `pode enviar para <alvo>` | `send` off/on |
| `libera o grupo <nome>` / `bloqueia o grupo <nome>` | grupo `ingest` on/off (`send` de grupo só por comando explícito `pode enviar para o grupo <nome>`) |
| `/privacidade` | contatos com leitura ou envio bloqueado e grupos liberados |

`<alvo>`: nome (agenda/contatos conhecidos, `contact_names`), número (`+55…`, com ou sem DDI) ou
nome de grupo (`evolution_discovery`, só leitura de metadados). A resolução é feita em código.
Com 0 resultados: "não achei". Com mais de 1: lista numerada para escolher. Com exatamente 1:
pede confirmação com **nome + número/JID** e botões ✅/✖ (mesmo mecanismo de `callback_data`
do briefing, prefixo novo `p1:`). Nada muda sem o ✅.

### 6. Apagar o que já foi guardado
Ao confirmar `para de ler`, a resposta pergunta "Apagar o que já guardei de <nome>? (timeline,
perfil, pendências)". Com ✅, `contact_policy.purge(jid)`:
- remove o diretório do contato em `contact_filesystem` (timeline e `profile.md`);
- apaga as linhas do JID (e aliases) em `wa_conversation_state`, `pending_commitments`
  (`source_chat`), `awaiting_dismissed` e nos vereditos dos juízes;
- registra no trace `purge` com contagens, sem conteúdo.

Neo4j (perfil `graph`, opcional) fica fora: o change registra o JID como pendência de limpeza
manual, se o perfil estiver ativo. Snapshots de briefing já enviados não são reescritos.

### 7. Sem LLM
Nenhum passo chama modelo. A simulação usa `--llm fill`; os passos de política não geram
chamadas, então o custo só aparece se a mensagem liberada passar pela extração existente.

## Riscos

- **Mais webhooks de grupo** com `groupsIgnore=false`: são descartados antes de qualquer I/O
  pesado. Se o volume incomodar, dá para voltar a ligar `groupsIgnore` quando não houver grupo
  liberado (anotado, sem implementar).
- **Nome ambíguo** pode bloquear a pessoa errada: por isso a confirmação mostra o número.
- **Apagar é irreversível**: só com ✅ explícito na mensagem seguinte, nunca disparado por
  conteúdo externo (guarda de origem do turno).

## Out of scope

E-mail; escopo "só arquivos"; envio direto; tela; limpeza automática do Neo4j.

## RAM

Sem container novo. Tabela pequena (dezenas de linhas) + cache em memória.
