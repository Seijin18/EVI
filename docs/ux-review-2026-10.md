# Revisão de produto — o EVI no dia a dia (Out 2026)

> Escopo: avaliar o EVI pelo fluxo de uso de uma pessoa, não pela arquitetura.
> Insumo para o próximo ciclo de changes OpenSpec. Fonte de verdade de requisitos
> continua sendo `openspec/specs/`.

## 1. O que os dados de uso dizem

Consulta ao Postgres em 2026-10-10:

| Sinal | Valor | Leitura |
|---|---|---|
| Mensagens no `/chat` | 520 em jun · 66 em ago · 0 em set/out | Uso caiu junto com o fim do desenvolvimento ativo |
| Canal | Telegram 247 · WhatsApp control 42 | Telegram é o canal real de conversa |
| Compromissos extraídos do WhatsApp | 37 no total · **0 confirmados** · 31 dispensados · 6 pendentes | O recurso mais diferenciado não converteu nenhuma vez |
| Stack parada | `agent-api`/`postgres` com `Exited (0)` há ~6 semanas (`restart: unless-stopped`) | Foi parada manualmente e ninguém sentiu falta |

Pedidos reais mais frequentes: listar/criar evento no calendário, resumir e limpar
e-mails, "o que você sabe sobre <contato>", revisar compromissos, e — repetidas
vezes — "O que você pode fazer?".

Exemplos de compromissos extraídos: "baixeii pra te mandar", "Mandar arrumar ele
mesmo", "Jantar" (sem data), "Teste digest Telegram". A precisão é baixa e o item
chega sem contexto suficiente para decidir.

**Diagnóstico:** o EVI hoje é uma interface conversacional sobre Google Calendar,
Tasks e Gmail, mais um extrator de compromissos que gera trabalho de revisão em vez
de tirar trabalho. Ele só age quando chamado, e o que faz sozinho (heartbeat,
daily summary por JID) é manutenção interna, não algo que a pessoa recebe e usa.
As últimas etapas (12–14, 17) foram de robustez e testes — necessárias, mas não
mudaram nada que o usuário percebe.

## 2. Um dia comum, momento a momento

| Momento | O que a pessoa precisa | O EVI hoje | Lacuna |
|---|---|---|---|
| **Acordar** | "O que tenho hoje? Algo urgente?" | Responde se perguntado, em 3 pedidos separados (agenda, tarefas, e-mail) | **Nada chega sozinho.** Sem briefing matinal |
| **Deslocamento** | Mandar áudio: "me lembra de pagar o boleto às 18h" | Não entende áudio; não existe lembrete que dispara do próprio EVI | **Áudio** e **lembrete com horário** — os dois recursos mais básicos de assistentes no WhatsApp |
| **Durante o dia** | Saber quem está esperando resposta; não esquecer o que prometeu | Extrai "compromissos" com baixa precisão; revisão é uma tarefa a mais | Falta foco em **"pendências de resposta"** e **promessas feitas por mim** |
| **Combinou algo no grupo** | "Vôlei quinta 19h" vira evento com 1 toque | O item chega sem data/contexto e exige conversa para confirmar | Confirmação de **um toque**, com data já resolvida e trecho da conversa |
| **Fim do dia** | "O que ficou para amanhã?" | Não existe | Fechamento do dia / prévia de amanhã |
| **Semana** | Visão da semana, aniversários, contas a vencer | Não existe | Revisão semanal (opcional, depois) |
| **Quando falha** | Saber que o assistente está fora | Fica fora em silêncio | **Alerta de indisponibilidade** |
| **Primeiro uso** | Entender o que pedir | "O que você pode fazer?" sem resposta boa | Cartão de capacidades com exemplos |

Sobre "pessoa comum": instalar o EVI exige Docker, OAuth no Windmill e QR code do
Evolution. Para um terceiro isso é a maior barreira de todas. Este documento assume
o EVI como assistente de um usuário técnico (o próprio autor) e não trata
empacotamento para terceiros.

## 3. Referências

| Produto/projeto | O que ele faz que interessa | Lição para o EVI |
|---|---|---|
| [Google CC (Labs)](https://labs.google/cc) | E-mail "Your Day Ahead" toda manhã com Gmail+Calendar+Drive; você **responde ao e-mail** para corrigir, ensinar ou criar to-do; 👍/👎 em cada mensagem | Briefing matinal é o produto. Responder ao briefing é a interface. Feedback embutido |
| ChatGPT Pulse | Briefing proativo diário | Mesmo padrão; validação de mercado |
| [Poke](https://www.mintlify.com/x1xhlol/system-prompts-and-models-of-ai-tools/commercial/poke) | Assistente por mensagem que **sinaliza e-mail que precisa de resposta**, conflitos de agenda, voo próximo; "recipes" de automação | Proatividade sobre o que *exige ação*, não resumo de tudo. Críticas: triagem que enterra o urgente, lembretes no horário errado — precisão e pontualidade são o que define confiança |
| [Superhuman Auto Reminders](https://help.superhuman.com/hc/en-us/articles/45270478397203-Reminders-on-Autopilot) | Detecta mensagens **que você enviou e não tiveram resposta** e lembra de dar follow-up | "Pendências de resposta" é um alvo de extração mais fácil e mais útil que "eventos" |
| [Zapia](https://mercadoeconsumo.com.br/05/01/2025/inovacao/zapia-amplia-recursos-do-whatsapp-com-agendamento-de-compromissos/) | Assistente brasileiro no WhatsApp: lembretes recorrentes, sync Google Calendar, **transcrição de áudio** | No Brasil, áudio e lembrete são o mínimo esperado |
| [Perplexity no WhatsApp](https://www.business-standard.com/technology/tech-news/perplexity-ai-whatsapp-chatbot-adds-schedule-task-feature-how-it-works-125062500758_1.html) | "Me manda X todo dia às 8h" vira tarefa agendada | Tarefas agendadas em linguagem natural |
| [OpenClaw](https://docs.openclaw.ai/start/openclaw) | Assistente self-hosted: heartbeat para monitoramento, **cron para o que é recorrente**, skills em `SKILL.md`; recomenda **número de WhatsApp dedicado** | Mesma arquitetura do EVI (workspace, heartbeat, skills). Separar heartbeat (vigiar) de cron (entregar) |

### Risco de plataforma

- [Meta proibiu chatbots de uso geral na WhatsApp Business API desde 15/01/2026](https://respond.io/blog/whatsapp-general-purpose-chatbots-ban)
  (ChatGPT, Perplexity, Luzia e Poke saíram). O EVI não usa a Business API — usa
  Evolution/Baileys sobre o número pessoal —, então a regra não se aplica
  diretamente, mas o caminho não-oficial [tem risco de banimento](https://zenvanriel.com/ai-engineer-blog/openclaw-whatsapp-risks-engineers-guide/)
  decidido por heurística (quem você contata, taxa de bloqueio).
- **Consequência de produto:** manter o WhatsApp como fonte de leitura + canal de
  controle de baixo volume, e o **Telegram como canal de saída proativa**
  (briefing, lembretes). Não enviar mensagens a terceiros automaticamente.

## 4. Proposta

Princípio: **o EVI deve chegar até a pessoa no momento certo com o que exige ação**,
em vez de esperar ser perguntado. Cada item abaixo vira um change OpenSpec.

### P1 — Briefing matinal no Telegram *(maior valor, baixo custo)*

Uma mensagem às 7h (configurável) com:
1. agenda de hoje (e conflitos);
2. tarefas vencendo hoje/atrasadas;
3. até 3 e-mails que parecem exigir ação (não resumo da caixa);
4. pendências do WhatsApp (ver P3), numeradas.

Responder ao briefing age sobre ele ("confirma 2", "apaga as promoções",
"move a reunião para 15h"). 👍/👎 por item para medir utilidade.

- Reaproveita tools existentes (`list_calendar_events`, `list_tasks`,
  `summarize_inbox`, `list_pending_commitments`) + agendamento no Windmill.
- Substitui o heartbeat atual, cujas mensagens ("contatos precisando de síntese")
  são manutenção, não valor para o usuário.
- Prévia de amanhã às 21h como variante opcional do mesmo mecanismo.

### P2 — Lembretes que disparam *(o básico que falta)*

"Me lembra às 18h de pagar o boleto" / "toda segunda às 9h, revisar finanças".
Hoje impossível: o EVI só cria evento no Google Calendar e depende da notificação
de outro app.

- Tabela `reminders` (Postgres) + tick periódico que envia no Telegram.
- Recorrência simples (diária, semanal, mensal) com `rrule`.
- "Adiar 1h" / "feito" como resposta.
- Mesmo mecanismo de agendamento do P1 — fazer P1 e P2 sobre a mesma base.

### P3 — Trocar "compromissos" por "pendências de resposta e promessas"

Os números (0 de 37) justificam repensar, não ajustar limiar.

- **Alvo novo:** (a) mensagens diretas a você sem resposta há mais de N horas;
  (b) promessas suas ("te mando amanhã", "vejo e te falo"); (c) combinados com
  data explícita.
- (a) é determinístico (último remetente da conversa), sem LLM — alta precisão.
- Cada item chega com o trecho da conversa, a data já resolvida e ação de um toque.
- Entra no briefing (P1) em vez de notificação avulsa.
- **Métrica:** taxa de confirmação. Se ficar abaixo de ~30% após duas semanas,
  desligar a extração por LLM e manter só (a).

### P4 — Mensagens de voz no canal de controle

Áudio para o EVI no Telegram/WhatsApp control → transcrição → mesmo fluxo do texto.

- O corte de "Whisper/Llava" no roadmap tratava de rodar **localmente** na GTX 1060.
  O Gemini já aceita áudio como entrada ([docs](https://ai.google.dev/gemini-api/docs/audio)),
  então isso cabe na premissa de $0/mês sem GPU. Reabrir o item com essa abordagem.
- Ressalva: no tier gratuito, o conteúdo pode ser usado pelo Google para treino.
  Aceitável para comandos ditados ao próprio assistente; **não** transcrever áudios
  de terceiros por padrão.

### P5 — Confiabilidade percebida

- Alerta "EVI fora do ar" fora do próprio EVI (ex.: cron do host chamando `/health`
  e mandando direto na API do Telegram se falhar).
- Resposta curta e fixa para "o que você pode fazer?" com 6–8 exemplos reais.
- Ack imediato ("agendando…") quando uma tool demora — é o núcleo do #38 e pode
  entrar aqui de forma mínima.

### O que muda no backlog atual

| Item | Recomendação |
|---|---|
| #37 prompt injection | **Manter e casar com P1/P3.** O briefing coloca conteúdo de terceiros no grafo principal com tools de escrita ligadas. Delimitar conteúdo externo antes de ligar o P1 em produção |
| #38 background execution | Reduzir ao ack imediato (P5). O resto depois |
| #34b snapshots estruturados | Adiar; sem efeito percebido |
| Adapter Meta/Twilio | Continua adiado; a Business API proíbe exatamente este caso de uso |
| Multimodal | Reabrir só a parte de **áudio via Gemini** (P4) |

### Sequência sugerida

1. **P1 + guarda mínima do #37** — um change: briefing matinal no Telegram com conteúdo
   de terceiros delimitado.
2. **P2** — lembretes, sobre o mesmo agendador.
3. **P3** — pendências de resposta, alimentando o briefing.
4. **P4** — áudio.
5. **P5** — em paralelo, itens pequenos.

### Como saber se funcionou

- Uso volta a acontecer sem desenvolvimento ativo: mensagens/semana no Telegram > 0
  de forma contínua por um mês.
- Briefing: % de dias com pelo menos uma resposta ou 👍.
- Pendências: taxa de confirmação ≥ 30%.
- Se a stack cair, você fica sabendo em minutos.
