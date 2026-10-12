## Why

O briefing de 12/10 mostrou que o que o EVI entrega não se lê de relance:

- os marcadores de segurança `«externo:…» … «/externo»` (feitos para o LLM) aparecem
  para o usuário em cada linha;
- promessas mostram a frase do usuário ("Pode deixar") e um número cru
  (`128947870277756@lid`) em vez de **quem** e **o quê**;
- dívidas de resposta incluem fechamentos ("Joia", "obrigado, Marcão!");
- `+13` não diz o que esconde nem como ver;
- com mais itens, agenda e e-mail viram uma parede de texto (sem hierarquia visual — o
  Telegram recebe texto puro).

Os changes anteriores da fila consertam o **conteúdo** (títulos de promessa, nomes de
contato); este conserta a **apresentação** e revisa as outras superfícies com o mesmo
olhar. Prioridade de produto: entrega proativa no Telegram é a primeira.

## What Changes

- **Revisão curta** das superfícies que o usuário lê (briefing manhã/noite, listas de
  pendências, respostas de comandos, lembretes, avisos de erro/indisponibilidade,
  `/ajuda`), com amostras reais e um checklist de legibilidade (`docs/ux/review-2026-10.md`).
- **Duas visões do mesmo conteúdo**: o usuário recebe texto limpo; o histórico que vai
  ao LLM guarda a versão marcada (`wrap_external`). Nenhum marcador chega ao Telegram.
- **Briefing reformatado** para leitura rápida no celular: formatação do Telegram (HTML),
  pessoa em destaque antes do assunto, uma linha por item, idade curta, prazo visível,
  `+N` com o comando para ver o resto; teto por seção e resumo quando houver muito.
- **Fechamentos** fora das dívidas de resposta: vocabulário ampliado ("joia",
  "tranquilo", "fechou", 👍) e agradecimento seguido de nome ("obrigado, Marcão!").
- Correções pequenas que a revisão achar nas outras superfícies (até o limite das tasks).

## Impact

Alterado: `agent/services/briefing.py`, `agent/services/telegram_notify.py`,
`agent/services/untrusted.py`, `agent/services/reply_debts.py`,
`agent/services/telegram_list.py`, testes correspondentes; novo
`docs/ux/review-2026-10.md`. Specs: `proactive`, `messaging-whatsapp`. Sem container novo.
Depende do conteúdo de `evi-promise-context`, `evi-contact-knowledge` e
`evi-contact-names` (por isso vem por último).

## Validação em uso real

Janela de 7 dias:
- 0 mensagens ao Telegram contendo `«externo` (checado no log de envio);
- taxa de ação sobre itens do briefing (relatório semanal) não cai e, em promessas e
  dívidas, sobe em relação à semana anterior;
- o usuário avalia 3 briefings como "dá para ler em 10 s" (pergunta única no fim da
  semana).

## Out of scope

- Mudar o que entra no briefing (critérios de seleção) além dos fechamentos.
- Interface nova (app, web); botões inline do Telegram ficam como recomendação.
- Reescrever prompts do agente conversacional.
