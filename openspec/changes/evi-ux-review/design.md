## Context

- `briefing.assemble_briefing()` monta o texto sem LLM e envolve todo campo de terceiro
  com `wrap_external` — porque o briefing é gravado na sessão do Telegram e as respostas
  ("feito 8") passam pelo LLM depois. A mesma string vai ao Telegram: os marcadores
  aparecem para o usuário.
- Telegram é enviado como texto puro (nenhum `parse_mode` no código).
- Numeração contínua 1..N entre seções (spec `proactive`) — é o que permite "feito 8".
- Exemplo real (2026-10-12): 3 dívidas, 10+13 promessas; nomes ausentes; fechamentos
  listados como dívida.

## Decisions

### 1. Duas renderizações

`Briefing` passa a ter `text_user` (limpo) e `text_model` (marcado). Envio usa
`text_user`; sessão/histórico grava `text_model`. Regra geral, aplicada também a listas
e respostas diretas (`telegram_list`): **o que vai ao usuário nunca passa por
`wrap_external`; o que volta ao LLM sempre passa.** Guarda: `telegram_notify.send()`
remove marcadores residuais e registra `soft_fail` se encontrar algum (detecta
regressão sem expor ao usuário).

Texto de terceiros no `text_user` é escapado para HTML do Telegram (`&`, `<`, `>`) —
conteúdo do contato nunca vira formatação.

### 2. Formato do briefing (HTML do Telegram)

```
<b>Bom dia!</b> Segunda, 12/10

<b>📅 Agenda</b>
1. 12:00–13:00 Entrega lote 2 Isla
2. 13:30–14:30 Monitoria lab CD

<b>✉️ E-mail</b>
3. <b>Link</b> · Novo login no dispositivo Linux
4. <b>Ruchika Mitbander</b> · Re: mDoc Github

<b>💬 Esperando sua resposta</b>
5. <b>Davi Giuberti</b> · 5 d · "entrou?"

<b>🤝 Suas promessas</b>
6. <b>Eliana</b> · mandar a modelagem · até sex
7. <b>Fernando</b> · preencher o contrato do MEI
+11 promessas → "promessas"

Responda: feito 6 · respondido 5 · dispensa 7
```

- **Quem primeiro, em negrito**; depois o quê; metadados curtos (`5 d`, `até sex`).
- Remetente de e-mail só com o nome (sem `<endereço>`).
- Rodapé com os 2–3 comandos válidos para os itens mostrados.
- `+N` diz o tipo e o comando que lista o resto.
- Texto do contato entre aspas, cortado em ~60 caracteres na palavra.

### 3. Volume

Tetos por seção mantidos (spec atual) mais regra de resumo: se uma seção tiver mais que
o teto, mostra os itens prioritários (datados/mais antigos primeiro) e uma linha
"+N … → comando". Briefing inteiro ≤ ~25 linhas; acima disso, seções de menor
prioridade viram uma linha-resumo ("✉️ 9 e-mails, 2 parecem pedir ação → 'emails'").

### 4. Fechamentos

`CLOSING_VERSION = 2`: + "joia", "jóia", "tranquilo", "fechou", "certo", "perfeito",
"show de bola", "valeu demais", emojis de aprovação; e agradecimento seguido de vocativo
curto (≤ 2 palavras com inicial maiúscula + pontuação: "obrigado, Marcão!"). Testes com
os casos reais do briefing de 12/10.

### 5. Revisão das outras superfícies

`docs/ux/review-2026-10.md`: para cada superfície, 2–3 amostras reais (de
`logs/telegram.jsonl`, briefings salvos, lembretes) avaliadas no checklist — cabe numa
tela de celular? o primeiro elemento é o que importa? dá para agir sem abrir outra
coisa? há jargão interno (JIDs, ids, nomes de tool, marcadores)? erros dizem o que fazer?
Achados viram correções nas tasks 3.x (no máximo 3) ou BACKLOG.

## Riscos

- **HTML inválido** derruba o envio no Telegram: escape centralizado + teste com
  caracteres especiais; falha de parse → reenvia em texto puro.
- **LLM perder o contexto** dos itens: `text_model` continua igual ao de hoje.
- Sem container novo.

## Out of scope

- Botões inline, app/web, critérios de seleção do briefing, prompts do agente.
