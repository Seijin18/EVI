## Context

- `whatsapp_contacts` (Postgres) é a identidade canônica: `display_name`, `aliases`,
  `whatsapp_label` (pushName), `phone`. Precedência atual: agenda > pushName > número
  (`contact_registry.effective_label`).
- `vcard_import.match_key()` = DDD + 8 últimos dígitos (estável com/sem o nono dígito;
  1187 chaves distintas, zero colisões no registro real). `import_vcard()` faz parse +
  casamento + escrita com dry-run.
- `set_whatsapp_contact_name` grava nome vindo do chat (o usuário disse).
- Integrações Google passam pelo Windmill com um cliente OAuth por tipo de resource
  (`gcal`, `gtasks`, `gmail`), padrão documentado em `windmill/README.md`.
- Medição (2026-10-12, 39 conversas diretas ativas em 30 dias): 9 agenda, 5 pushName,
  25 sem nome (20 telefone, 5 `@lid`; 3 `@lid` sem `remoteJidAlt`).

## Decisions

### 1. Fonte: Google People API, via Windmill

Script `f/integrations/list_contacts`: `GET people/me/connections?personFields=names,
phoneNumbers&pageSize=1000` paginado (`nextPageToken`), devolve só
`[{"name": str, "phones": [str]}]` — sem e-mail, endereço, foto ou notas (mínimo
necessário). Resource OAuth `gcontacts` (scope `contacts.readonly`), mesmo Client
ID/Secret do `gcal`; People API habilitada no projeto Google; `.env`:
`WINDMILL_GCONTACTS_RESOURCE`. Passo manual de reconexão documentado no
`windmill/README.md` (o usuário faz o consentimento).

### 2. Aplicação: importador genérico

`vcard_import` ganha `apply_entries(entries, *, source, dry_run)` — o parse de vCard vira
só um produtor de entradas. Regras:

- Casa por `match_key`; um telefone casando com dois nomes diferentes na agenda →
  ignora e reporta (ambíguo).
- **Origem do nome** guardada (`name_source`: `user` | `agenda` | `vcard`); a sincronização
  só escreve onde `name_source` ∈ {vazio, `agenda`, `vcard`}. Nome dado pelo usuário no
  chat (`user`) nunca é sobrescrito.
- pushName anterior vira alias (como no vCard).
- Contatos que sumiram da agenda: nome mantido (não apaga).

### 3. Execução

`POST /jobs/contact-names-sync` (API key) chama o script Windmill, aplica e devolve o
relatório (`casados`, `novos nomes`, `alterados`, `ambíguos`, `sem WhatsApp`).
Agendamento diário 03:15 no Windmill, antes do lote de conhecimento (03:30). Primeira
execução: `./scripts/evi-test contact-names-sync` em dry-run, revisada com o usuário.

### 4. `@lid`

Nome resolvido por `canonical_jid()` (de `evi-contact-knowledge`): `@lid` com par de
telefone herda o nome. `@lid` sem par só pode ser nomeado pelo usuário (§5).

### 5. Pergunta semanal

Seção do briefing de segunda: até 3 conversas diretas com ≥ 3 mensagens nos últimos 14
dias e sem nome (`name_source` vazio e pushName ausente ou numérico), ordenadas por
atividade. Cada uma: número/`@lid`, trecho da última mensagem do contato (`wrap_external`)
e, se houver, "talvez: <nome>". Resposta "nomeia N <nome>" → `set_whatsapp_contact_name`
(`name_source=user`). "ignora N" → não pergunta de novo por 90 dias.

Sugestão de nome: `llm_structured.run_structured("CONTACT_NAME_HINT", …)` sobre as
últimas 30 mensagens: `{"nome": str, "evidencia": str}` só quando a pessoa se apresenta
ou assina; evidência precisa estar literalmente numa mensagem do contato (validado no
código), senão descarta. Provedor default igual ao de `CONTACT_KNOWLEDGE` (OpenRouter
ZDR, aprovado pelo usuário em 2026-10-12). Teto diário compartilhado.

## Riscos

- **Escopo OAuth**: `contacts.readonly` dá leitura de toda a agenda; o script descarta
  tudo que não for nome+telefone antes de devolver. Token fica no Windmill, como os
  demais.
- **Nome errado da agenda** (ex.: "Pedro Eletricista"): é o nome que o usuário escolheu;
  ele pode renomear pelo chat (vira `user` e não é mais sobrescrito).
- **RAM**: nenhum container novo.

## Out of scope

- Escrita na agenda, participantes de grupos, CardDAV/iCloud, nome sem confirmação.
