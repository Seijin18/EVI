## Why

O WhatsApp nunca entrega o nome da agenda do celular — só o `pushName` que a própria
pessoa escolheu (`evi-contact-vcard-import`). O import de vCard foi feito uma vez: 222 de
1536 contatos têm nome. Nas 39 conversas diretas ativas nos últimos 30 dias (medido em
2026-10-12), só 9 têm nome da agenda, 5 têm nome de perfil e **25 aparecem como número**
(5 delas `@lid`, 3 sem telefone conhecido). Resumos, dívidas de resposta, promessas e o
conhecimento de contato (`evi-contact-knowledge`) ficam ilegíveis sem nome. O celular do
usuário é Android: a agenda já está sincronizada com a conta Google.

## What Changes

- **Sincronização diária da agenda Google** (People API, só leitura) via Windmill
  (`f/integrations/list_contacts`, OAuth `gcontacts` com `contacts.readonly`); o agente
  aplica pelo mesmo casamento do vCard (DDD + 8 últimos dígitos). Contato salvo no
  celular aparece no EVI no dia seguinte. Nome definido pelo usuário no chat nunca é
  sobrescrito.
- **Nome por identidade canônica**: `@lid` herda o nome do telefone pareado
  (`wa_jid_alias`, de `evi-contact-knowledge`).
- **Pergunta semanal só do que sobrar**: no briefing de segunda, até 3 conversas ativas
  sem nome, com trecho da última mensagem; responder "nomeia 2 Hollmann" grava o nome.
  Sugestão opcional de nome extraída da conversa (pessoa se apresentou/assinou) via
  `llm_structured` (OpenRouter ZDR) — nunca gravada sem confirmação.
- Sem LLM no import; dry-run na primeira execução.

## Impact

Novo: `windmill/f/integrations/list_contacts.{py,script.yaml}`,
`agent/services/contact_names.py`, `tests/unit/test_contact_names.py`,
`tests/fixtures/google/people_connections.json`. Alterado:
`agent/services/vcard_import.py` (importador genérico de entradas nome+telefones),
`agent/services/briefing.py`, `agent/main.py` (`/jobs/contact-names-sync`),
`windmill/README.md`, `.env.example`. Specs: `data-long-memory`, `proactive`.
Sem container novo. Depende de `evi-contact-knowledge` (identidade canônica).

## Validação em uso real

Janela de 7 dias após a primeira sincronização:
- ≥ 90% das conversas diretas ativas (30 dias) com nome de agenda ou do usuário
  (hoje 9/39 ≈ 23%);
- 0 nomes definidos pelo usuário sobrescritos pela sincronização.

## Out of scope

- Escrever na agenda Google (só leitura).
- Contatos de grupos (participantes).
- iCloud/CardDAV (usuário é Android).
- Adivinhar nome sem confirmação.
