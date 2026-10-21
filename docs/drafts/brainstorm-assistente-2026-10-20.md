# Brainstorm — de "avisa" para "resolve" (2026-10-20)

> **Status: RASCUNHO.** Documento de exploração, não normativo. As decisões aqui viram
> changes em `openspec/changes/` e `openspec/queued/`; quando divergirem, vale o change.
>
> Insumo para a próxima fila. Não é requisito: a fonte de verdade continua sendo
> `openspec/specs/`. Baseado em [`product-review-2026-10-18.md`](../product-review-2026-10-18.md),
> [`openspec/specs/roadmap.md`](../../openspec/specs/roadmap.md) e no BACKLOG.

## 1. Onde o EVI está

As etapas 18–36 resolveram **perceber**: briefing às 7h e às 21h, dívidas de resposta,
quem não respondeu você, lembretes, tarefas agendadas só de leitura, alertas de fonte fora,
botões inline. O que o EVI **faz** ainda é pouco: criar evento/tarefa, concluir tarefa
(change ativo `evi-task-complete`), apagar e-mail com confirmação, organizar `inbox/`.

Em quase todo item do briefing o trabalho continua com você. "Fulano espera sua resposta há
2 dias" vira: abrir o WhatsApp, lembrar do contexto, escrever. Os dados mostram isso
(ação em dívidas 14 %, briefing respondido 25 %). O EVI acha a tarefa, mas não deixa nada
adiantado.

**Proposta de princípio para a próxima fase:**

> Todo item que o EVI te mostra vem com o próximo passo **já preparado**: um rascunho,
> um arquivo, um horário proposto. Você aprova, edita ou descarta com um toque.

Isso é o padrão "ambient agent + agent inbox" (LangChain): o agente trabalha em segundo
plano a partir de eventos e entrega propostas numa caixa de aprovação, e o humano aprova,
edita ou responde perguntas. O Google CC e o Superhuman fazem o mesmo para e-mail.

## 2. A peça central: caixa de aprovação

Antes de qualquer recurso novo, uma infraestrutura única para "proposta aguardando você":

| Elemento | Como seria |
|---|---|
| **Proposta** | Registro `proposals(id, kind, origem, resumo, payload, status, criado_em, expira_em)`. Tipos: `whatsapp_reply`, `gmail_draft`, `calendar_reply`, `file_job`, `code_job`… |
| **Entrega** | Uma mensagem no Telegram por proposta, com prévia e botões **✅ aprovar · ✏️ editar · ✖ descartar**. Também entram numa seção "🗂 Preparei para você (N)" no briefing |
| **Editar** | Responder à mensagem com o texto corrigido ou com uma instrução ("mais curto", "diz que só sexta") gera nova versão |
| **Níveis de autonomia** por tipo | `L0` só avisa · `L1` prepara e espera (padrão) · `L2` faz e avisa com **desfazer** por X min · `L3` faz em silêncio e entra no relatório. Depois de N aprovações seguidas **sem edição**, o EVI *pergunta* se pode subir aquele tipo de nível. Nunca sobe sozinho |
| **Expiração** | Proposta que perdeu sentido (a pessoa já respondeu, a reunião passou) some sozinha, para não virar outra fila de culpa |
| **Medição** | Taxa de aprovação sem edição por tipo = sinal de qualidade (encaixa no `turn_log`/relatório semanal do V2) |

A guarda de escrita por origem do turno (`write_guard`) e o allowlist já existentes
continuam valendo: **proposta pode nascer de conteúdo externo, execução só com o seu toque.**
É isso que deixa o EVI ser proativo sem abrir uma porta de injeção.

## 3. Ideias de funcionalidade, pelo dia a dia

### A. Rascunhos prontos (sem VM, maior retorno)

1. **Resposta de WhatsApp pré-escrita.** Para cada dívida de resposta, o EVI prepara a resposta
   com o contexto (timeline + perfil do contato) e oferece um link `wa.me/<número>?text=…`.
   Um toque abre o WhatsApp com o texto preenchido, e **você** aperta enviar. Mantém a regra de
   não enviar a terceiros e tira o atrito que provavelmente explica os 14 %.
2. **Rascunhos no Gmail.** E-mails que pedem ação viram rascunho no próprio Gmail (Drafts API
   via Windmill). Briefing: "deixei 3 rascunhos no Gmail". Enviar continua sendo com você.
   Num segundo passo, opcional: aprovar pelo Telegram envia.
3. **Cobrança pronta** para "esperando resposta deles": rascunho educado de follow-up no
   mesmo formato `wa.me`.
4. **Convites e agendamento.** Pedido de reunião (e-mail/WhatsApp) leva o EVI a cruzar com
   a agenda e propor 2–3 horários livres já redigidos. Convite recebido: "aceito? conflita com X".
5. **Promessas que se cumprem sozinhas.** "Te mando o PDF amanhã": o EVI procura o arquivo
   (Drive/pastas locais) e deixa o envio preparado. Liga as promessas (Etapa 25) a uma ação.

### B. Antes de cada compromisso

6. **Ficha de reunião** 30 min antes de cada evento com pessoas: quem é (perfil do contato,
   Etapa 26), últimas conversas, e-mails e pendências entre vocês, o que você prometeu. É só
   leitura, usa dados que já existem e é dos recursos mais citados em assistentes executivos.
7. **Logística do dia**: evento com endereço → hora de sair (rota/tempo), "leve o documento X".

### C. Captura sem esforço

8. **Encaminhe qualquer coisa ao EVI** (mensagem, foto, PDF, link, áudio) e ele classifica:
   tarefa, lembrete, nota, arquivo para guardar, conta a pagar. Hoje a voz existe e não foi
   descoberta. Encaminhar é um gesto que já faz parte do hábito.
9. **Boletos e contas.** PDF/foto de boleto ou e-mail de fatura → extrai valor e vencimento →
   lembrete 2 dias antes + item no briefing. **Nunca paga**, só organiza. Visão via Gemini,
   pelo mesmo raciocínio que reabriu o áudio (não usa a GPU local).

### D. Trabalho de verdade num ambiente isolado (a ideia da VM)

É aqui que a ideia da VM entra (decidido: container só com arquivos e CLI, motor OpenRouter ZDR). Antes, convém olhar o histórico.

**O que já aconteceu:** o *dev bridge* (Etapa 11) foi **removido** em 12/08. Ele nunca rodou
no container, e consertá-lo exigiria repo montado em escrita + CLI de edição, com a fronteira
de confiança sendo um JID de WhatsApp. A ideia nova só vale se resolver exatamente esses
três pontos.

**Desenho sugerido: "oficina" isolada, não acesso ao computador.**

| Decisão | Proposta | Por quê |
|---|---|---|
| VM ou container | **Container dedicado e descartável** (Docker rootless; gVisor/`runsc` se quiser isolamento extra), não VM | Host com 15 GB e ~8 GB já usados, 4 núcleos. Uma VM com 2–4 GB fixos pesa; container sob demanda com `--memory 2g --cpus 2` e timeout custa ~0 quando ocioso. VM só se precisar de GUI/Windows |
| O que ele enxerga | Só `~/EVI-Oficina/` (`entrada/`, `saida/<job>/`, `modelos/`) e, por job, cópias do que você mandou. **Nunca** `.env`, `data/`, `~/.ssh`, home | O incidente do Postgres corrompido no #32 mostra que mount amplo vira acidente |
| Rede | Desligada por padrão; ligada por job ("pesquisa") com saída só HTTP(S) | Job com rede + conteúdo hostil + shell é o pior cenário de injeção |
| Quem dispara | **Só você**, pelo chat do Telegram (o allowlist de origem já garante). Turno vindo de e-mail/WhatsApp pode *sugerir* um job (vira proposta), nunca iniciar | Corrige a fronteira de confiança que matou o dev bridge |
| Resultado | Sempre em `saida/<job>/` + resumo + lista de arquivos/diff. Ir para o destino real (Drive, pasta, repo, PR) é uma **proposta** na caixa de aprovação | Você revisa antes de qualquer coisa sair da oficina |
| Execução | Assíncrona: ack, roda em background, entrega depois (é a Etapa 24 `evi-background-execution`, que agora teria motivo para abrir) | Jobs de minutos não cabem no turno |
| Motor | Loop agêntico próprio (LangGraph, já no projeto) com modelo do **OpenRouter ZDR**; limite de passos, tempo e US$ por job | Decidido em 20/10, rodada 3: sem Claude CLI. Modelo na §8 |

**O que a oficina resolveria no dia a dia:**

- **Arquivos**: "junta esses 3 PDFs", "converte para Word", "renomeia as fotos por data",
  "comprime esse vídeo", "extrai a tabela desse PDF para planilha". Arquivo entra pelo
  Telegram e volta pelo Telegram.
- **Documentos a partir de modelos**: ofício, recibo, proposta, relatório, formatação ABNT.
  Você deixa os modelos em `modelos/`.
- **Pesquisa com entrega**: "compara preço/specs de X, Y, Z e me manda uma tabela". Rede
  ligada só nesse job.
- **Mestrado/estudos** (vi uma tarefa "do mestrado" no relato do change ativo): resumo de
  artigos que você manda, fichamento, bibliografia em BibTeX/ABNT, revisão de texto.
- **Código pessoal**: "cria um script que faz X", "corrige o bug Y no repo Z". Roda num
  clone/worktree dentro da oficina e o resultado é **PR em rascunho** ou patch. Nunca push direto.
- **Organizar pastas** (Downloads, Documentos): o `organize_inbox` já existe em dry-run.
  Generalizar para "plano de organização" como proposta e mover só ao aprovar.

### E. Turno da noite

10. **O EVI trabalha enquanto você dorme.** No lote das 03:30, para o que está no dia seguinte,
    ele prepara rascunhos (A), fichas de reunião (B) e jobs óbvios (D). O briefing das 7h deixa
    de ser uma lista do que você tem que fazer e vira "fiz isto, aprova?". O briefing
    da noite (21h) pode perguntar: "amanhã você tem X, quer que eu prepare Y?".

### F. Mostrar o valor

11. **Relatório semanal "o que fiz por você"**: N rascunhos aprovados, N arquivos gerados,
    N lembretes cumpridos, tempo estimado poupado. Reforça o hábito e é a métrica de produto.
12. **Memória de preferências de escrita**: aprender com suas edições nos rascunhos (tom,
    tamanho, cumprimento por contato) e guardar no perfil do contato/`USER.md`.

## 4. Riscos e o que os dados ensinam

- **Recurso que ninguém descobre não existe.** Lembretes e voz tiveram 0 uso. Tudo acima deve
  **nascer dentro do briefing ou de uma notificação**, nunca depender de você lembrar de pedir.
  A caixa de aprovação resolve isso por construção.
- **Proposta ruim é pior que nenhuma.** Rascunho genérico gera descarte e o hábito morre (como as
  37 promessas com 0 confirmações). Começar por **poucos tipos com bom contexto**, medir a
  aprovação sem edição e cortar o tipo que ficar abaixo do limiar.
- **Privacidade**: rascunhos usam conversas pessoais. Seguir a regra existente: conversa só
  vai para nuvem via OpenRouter **ZDR**. Isso vale também para a oficina (§8), que terá
  orçamento próprio além do teto atual de US$ 5/mês das tarefas estruturadas.
- **RAM**: nada de serviço novo sempre ligado. Container da oficina sob demanda.

## 5. Decisões do usuário (20/10)

| Tema | Decisão |
|---|---|
| Automelhoramento | O que o EVI não consegue fazer vira registro interno e depois change OpenSpec (§7) |
| Motor da oficina | **Só OpenRouter (ZDR).** Claude CLI descartado (§8) |
| Envio a terceiros | **Direto, com sua autorização**, quando o sistema estiver estabelecido. **WhatsApp e e-mail juntos** (você manda poucos e-mails) (§9). Isso **revoga, por etapas**, o princípio do roadmap "o EVI não envia mensagens a terceiros por conta própria"; o change precisa editar `roadmap.md` e a spec `messaging-whatsapp` explicitamente |
| Oficina | **Só arquivos e linha de comando.** Sem navegador e sem interface gráfica |
| Interface própria | Só planejar agora (desktop + Android); implementar no futuro (§10) |
| Contatos e grupos | Nenhum contato restrito hoje, mas **controle por contato de ingestão e de envio**. **Todo grupo fica fora de ingestão e envio** e só é liberado quando você pedir (§11) |
| Rotina semanal | Organizar tarefas da rotina, **pedidos que chegam pelo WhatsApp** e **estudo** (faculdade/mestrado) (§12) |

## 6. Sequência sugerida (revisada)

| # | Change candidato | Depende de | Por que nessa ordem |
|---|---|---|---|
| 1 | `evi-contact-policy`: ingestão/envio por contato e grupo, grupos fora por padrão, comandos no Telegram, apagar o que já foi guardado | — | Pré-requisito de privacidade de tudo que lê ou envia; pequeno |
| 2 | `evi-capability-gaps`: tool `report_capability_gap`, sinais implícitos, registro com dedupe, seção no relatório semanal | V2 (`turn_log`) | Pequeno, sem risco, e alimenta a fila com evidência real |
| 3 | `evi-approval-inbox`: modelo `proposals`, mensagem com botões, seção no briefing, níveis L0–L2 | Botões (#31) | Toda a fase depende dela |
| 4 | `evi-incoming-requests`: pedido recebido no WhatsApp vira proposta "criar tarefa + resposta confirmando" | 1, 3 | É uma das três coisas da sua semana |
| 5 | `evi-reply-drafts`: rascunho de resposta (WhatsApp `wa.me` + rascunho no Gmail) — envio fase 0 | 3 | Mede a qualidade dos rascunhos **antes** de liberar envio direto |
| 6 | `evi-study-calendar`: grade por CSV → agenda "Estudos", envio de material pelo Telegram com associação à aula, briefing do dia de aula | — | A terceira coisa da sua semana; começa só com leitura e lembrete |
| 7 | `evi-workshop-sandbox`: oficina em container, só arquivos e CLI, modelo OpenRouter ZDR, jobs assíncronos (absorve a Etapa 24) | 3 | Habilita resumo de aula de PDF/slides e as tarefas de arquivo |
| 8 | `evi-study-summaries`: resumo de material e da aula, revisão, prazos do plano de ensino | 6, 7 | Fecha o ciclo de estudo |
| 9 | `evi-direct-send` fase 1 (WhatsApp + e-mail, aprovar cada envio) | 5 com aprovação sem edição ≥ 70 % | Só depois de os rascunhos provarem qualidade |
| 10 | `evi-gap-to-proposal`: lacuna recorrente vira rascunho de change gerado na oficina | 2, 7 | Fecha o ciclo de automelhoramento |
| 11 | `evi-meeting-prep`, `evi-capture-forward`, `evi-night-shift`, relatório "o que fiz por você" | 3–7 | Junta tudo |
| 12 | `evi-console` (interface desktop/Android, §10) | 3, API de leitura | Quando houver bastante coisa para ver e operar |

## 7. Automelhoramento: lacunas de capacidade → changes

**Caso real que motiva.** Em 21/10, "finalize todas as tarefas em aberto, exceto a do
mestrado": o EVI **inventou uma restrição** ("não consigo várias de uma vez com exceção") em
vez de dizer que não existia tool para concluir tarefa. A lacuna só apareceu porque você
percebeu e investigou.

### Fluxo

```
pedido que o EVI não atende
  ├─ explícito: o modelo chama report_capability_gap(pedido, o_que_falta, contorno)
  └─ implícito: /ruim, 👎, reformulação, correção, resposta "não consigo/não tenho acesso",
                tool inexistente pedida, erro de tool repetido
        ↓
registro de lacunas (Postgres + EVI_WORKSPACE/gaps/<slug>.md)
  dedupe por similaridade (Qdrant já existe) → contador, exemplos anonimizados, 1ª/última vez
        ↓
relatório semanal: "3 coisas que você pediu e eu não sei fazer" + botão [virar proposta]
        ↓  (você toca)
oficina (§D, modelo OpenRouter ZDR) com cópia SÓ LEITURA do repo gera
  openspec/proposals-inbox/<slug>/proposal.md (Why com a evidência, What, Impact, Out of scope)
  + cenário de simulação vermelho (como o `evi-sim promote` já faz para falhas)
        ↓  (proposta na caixa de aprovação)
você revisa → numa sessão Claude Code normal, vai para queued/ e entra na fila
```

### Decisões de desenho

| Ponto | Proposta | Por quê |
|---|---|---|
| Honestidade na hora | Ao registrar a lacuna o EVI responde: "Ainda não sei fazer isso; anotei como melhoria (#12). Dá para fazer assim por enquanto: …" | O pior do caso real foi a desculpa inventada. Instrução no prompt + tool barata de chamar |
| Onde nasce o rascunho | `openspec/proposals-inbox/`, **fora** de `changes/` e `queued/` | Respeita "um change ativo por vez" e a fila manual; nada entra na fila sem você |
| Quem escreve no repo | Ninguém do EVI. A oficina gera arquivos em `saida/`; levar ao repo é proposta aprovada | O dev bridge caiu justamente por escrever no repo a partir de um canal de mensagem |
| Implementação automática | **Não.** O rascunho é o fim do caminho do EVI; implementar continua sendo numa sessão sua (`/implement-change`) | Código que se reescreve sem revisão é o risco mais alto do projeto |
| Privacidade | Exemplos passam pela mesma anonimização do `evi-sim promote` antes de ir para o rascunho | Pedidos citam pessoas e conversas |
| Ruído | Lacuna só vira sugestão no relatório com ≥ 2 ocorrências **ou** marcada por você ("isso é importante") | Evita fila de pedidos pontuais |
| Fora de escopo | Lacunas que são decisão de política (ex.: "pague o boleto") viram registro "recusado por regra", não proposta | Não queremos o EVI propondo derrubar as próprias guardas |

**KPI**: lacunas com resposta honesta ≥ 95 % (0 restrição inventada no corpus de simulação);
≥ 1 change por mês nascido de lacuna real.

## 8. Modelo da oficina no OpenRouter

### Por que não o Claude CLI (registro da decisão)

A página oficial *Legal and compliance* do Claude Code reserva o login da assinatura para o
"uso comum do Claude Code e de apps nativos". Um serviço disparando o CLI sozinho fica em
zona cinzenta e arrisca a conta Pro. Além disso, o CLI não tem ZDR (o que quebra a regra do
projeto), divide a cota com seu uso de programação e é difícil de reproduzir no `evi-sim`.
O OpenRouter ZDR resolve os quatro pontos.

### Levantamento (API pública do OpenRouter, `GET /api/v1/endpoints/zdr`, 20/10)

Filtro: endpoint **ZDR** + suporte a **tools** + `response_format`. Preço em US$ por milhão de
tokens (entrada / saída). "Hospedagem" importa: endpoints muito baratos costumam ser
quantizados em fp4, o que tende a piorar tool calling.

| Modelo | Preço ZDR | Hospedagem ZDR | Entrada | Papel possível |
|---|---|---|---|---|
| **anthropic/claude-haiku-5.5** | 0,10 / 0,50 | Google Vertex, Amazon Bedrock (pesos originais) | texto, **imagem, arquivo/PDF**; 1M de contexto | **Padrão da oficina** |
| **anthropic/claude-sonnet-5.5** | 2,00 / 10,00 | Google Vertex, Bedrock | texto, imagem, arquivo | **Escalonamento** para job difícil (código, documento longo) |
| openai/gpt-6-luna | 0,10 / 0,50 | Azure | texto, imagem, arquivo | Alternativa do padrão (mesmo preço, outro fornecedor) |
| deepseek/deepseek-v4.1-flash | 0,06–0,30 / 0,12–1,20 | ~30 provedores, muitos em fp4/fp8 | texto, imagem | Fallback barato (fixar provedor fp8) |
| google/gemma-4-31b-it | 0,10 / 0,34 | CoreWeave fp4 | texto | Já usado nos juízes; fraco para agente longo |
| z-ai/glm-5.3, moonshotai/kimi-k2.6 | 0,75–1,40 / 1,00–4,40 | vários | texto | Mais caros que o Haiku sem vantagem clara aqui |

### Recomendação

- **Padrão: `anthropic/claude-haiku-5.5`.** Tem o preço dos modelos "flash", roda com pesos
  originais em Vertex/Bedrock (sem quantização desconhecida) e tem ZDR. Lê **PDF e imagem
  direto**, o que serve para slides e materiais de aula (§12), e aguenta contexto longo para
  um semestre de material.
- **Escalonamento: `anthropic/claude-sonnet-5.5`** só quando o job pede (código, documento
  de mais de N páginas, ou o Haiku falhou na verificação), e com aviso de custo antes.
- **Fallback:** `openai/gpt-6-luna` (outro fornecedor, mesmo preço), depois DeepSeek V4.1 Flash
  com provedor fp8 fixado. O `llm_structured` já sabe fazer provedor por tarefa + fallback; a
  oficina reaproveita.
- **Rota:** manter `provider: {zdr: true, data_collection: "deny"}` no código, como hoje.
  Ligar também a opção de conta do OpenRouter que restringe a endpoints ZDR, como segunda
  trava (verificar o nome atual da opção nas configurações de privacidade).

**Custo estimado** (job agêntico típico: ~15 passos, ~150 mil tokens de entrada somados, ~10 mil
de saída):

| Modelo | Por job | 100 jobs/mês |
|---|---|---|
| Haiku 5.5 | ~US$ 0,02 | ~US$ 2 |
| Sonnet 5.5 | ~US$ 0,40 | ~US$ 40 |

Sugestão: **orçamento próprio da oficina** (ex.: US$ 5/mês, fail-closed como o atual), teto de
US$ 0,50 por job, e Sonnet só com o seu ok.

**Validar antes de fixar.** Os preços e a lista de modelos mudam; os do Haiku 5.5 batem com o
preço de tabela do modelo. Não tenho benchmark independente da qualidade dele em tarefas
agênticas em português. Proposta: um `llm-eval workshop` com 15–20 jobs reais (resumir PDF de
aula, juntar/converter arquivos, gerar documento de modelo, script simples), comparando Haiku 5.5,
GPT-6 Luna e DeepSeek V4.1 Flash pelo mesmo critério de aprovação sem edição.

### Loop agêntico: próprio, não CLI de terceiros

Agentes de terminal open source (OpenCode, Goose, Aider…) aceitam OpenRouter, mas seria mais
um binário com seu próprio modelo de permissões, difícil de prender às guardas do EVI e de
gravar no `evi-sim`. Recomendo **um loop LangGraph pequeno** dentro do `agent-api` (ou num
worker), com poucas ferramentas que executam **dentro do container da oficina**:
`list_dir`, `read_file`, `write_file`, `run(cmd)` (com timeout), `finish(resumo, arquivos)`.
Imagem com `python`, `pandoc`, `libreoffice --headless`, `poppler`/`qpdf`, `ffmpeg`,
`imagemagick`. Isso dá para conversão, PDF, documentos e scripts, sem rede por padrão.

## 9. Envio direto a terceiros com autorização (WhatsApp + e-mail)

Hoje é proibido por princípio, porque o WhatsApp é o número pessoal via Baileys (não
oficial, com risco de banimento por heurística) e porque envio é o efeito mais difícil de
desfazer. **WhatsApp e e-mail andam juntos**, pelas mesmas fases e guardas. Liberação em
fases, cada uma liberada pelos dados da anterior:

| Fase | Como funciona | Libera a próxima quando |
|---|---|---|
| 0 — você envia | WhatsApp: link `wa.me` com o texto. E-mail: rascunho no Gmail | Rascunhos aprovados **sem edição** ≥ 70 % em 4 semanas |
| 1 — aprovar cada envio | Botão ✅ no Telegram → **"enviando em 30 s · [cancelar]"** → Evolution `sendText` / Gmail `send` | 0 envios errados (destinatário/conteúdo) em 4 semanas, ≥ 30 envios |
| 2 — autonomia por regra | Você autoriza por contato **e** por tipo (ex.: "confirmar horário com a Ana", "agradecer recebimento"). Mantém a janela de cancelamento e o aviso pós-envio | Revisão periódica; você revoga com uma palavra |

**Guardas, em todas as fases:**

- **Política do contato manda (§11).** Contato ou grupo com envio bloqueado nunca recebe nada,
  nem com aprovação. Grupo só depois de liberado por você.
- **O destinatário vem do código, nunca do LLM.** Ele é a conversa de origem da dívida ou do
  pedido. Destino novo ou digitado exige confirmação com nome e número/e-mail na tela.
- **O texto aprovado é o texto enviado.** Hash do conteúdo no botão; editar gera nova
  aprovação; o `callback_data` assinado já existe nos botões do briefing.
- **Contra exfiltração:** o rascunho para X só recebe o contexto da conversa com X (nada de
  outros contatos, notas, e-mails). Uma checagem antes do envio barra telefone, e-mail,
  endereço ou link que não estejam na conversa com X nem no seu pedido.
- **Contra injeção:** turno disparado por conteúdo externo nunca envia; no máximo cria proposta.
- **Contra banimento (WhatsApp):** na fase 1 só conversa direta já existente; teto por hora e
  por dia; horário silencioso; atraso humano entre envios; o watchdog de conexão (Etapa 30)
  suspende os envios se a sessão cair.
- **Rastro:** cada envio no `turn_log`/auditoria com rascunho, aprovação e id da mensagem;
  comando "o que você enviou hoje?" e tela de Atividade (§10).

## 10. Interface própria (desktop + Android) — planejamento para o futuro

Telegram continua sendo o canal do dia a dia. A interface própria serve ao que o chat faz
mal: **ver** muita coisa de uma vez (atividade, filas, histórico), **revisar** coisa grande
(documento, diff, rascunho de change) e **configurar** (contatos, autonomia, disciplinas).

### Forma de entrega

| Opção | Desktop | Android | Prós | Contras |
|---|---|---|---|---|
| **Telegram Mini App** | Sim (Telegram Desktop) | Sim | Sem instalar nada; abre a partir de um botão do próprio chat ("abrir caixa de aprovação"); login pelo `initData` assinado do Telegram | Fica dentro do Telegram; precisa de URL HTTPS que o aparelho alcance |
| **PWA** servida pelo `agent-api` | Navegador / "instalar app" | Instalável na tela inicial; Web Push | Uma base de código; tela cheia | Login próprio; push no Android exige HTTPS válido |
| App nativo (Kotlin/Flutter) | Não (ou outro app) | Sim | Widgets, notificação rica | Duas bases de código; muito esforço para um usuário |

**Recomendação:** **uma só aplicação web** (PWA) que também abre como **Telegram Mini App**,
servida pelo `agent-api` **só na tailnet** com HTTPS do `tailscale serve`. Isso segue a
decisão de segurança atual (nada exposto fora do host/tailnet, `docs/remote-access.md`).
Auth: `initData` do Telegram validado por HMAC no Mini App; sessão curta + chave no PWA. A
`EVI_API_KEY` nunca vai para o navegador.

### Telas

| Tela | Conteúdo | Ações |
|---|---|---|
| **Hoje** | Linha do tempo do dia: agenda, **aulas**, lembretes, dívidas, propostas, jobs rodando | Abrir qualquer item |
| **Caixa de aprovação** | Propostas por tipo, com prévia completa (texto, arquivo, diff) e de onde veio | ✅ / ✏️ editar no lugar / ✖; aprovar em lote |
| **Atividade** | Tudo o que o EVI fez: turnos, tools, envios, jobs, com filtro por canal/tipo/contato | **Desfazer** onde existir; "por que você fez isso?" (origem + evidência) |
| **Oficina** | Jobs (fila, rodando, pronto, falhou), custo de cada um, arquivos de saída | Baixar, aprovar destino, repetir, cancelar |
| **Estudos** | Disciplinas, grade, materiais por aula, resumos, prazos (§12) | Subir material, marcar aula vista, pedir resumo |
| **Contatos e grupos** | Política por contato/grupo (ingestão, envio), última atividade | Liberar/bloquear; **apagar dados de um contato** |
| **Melhorias** | Lacunas de capacidade (§7), contagem, exemplos | "Isso é importante", virar proposta, descartar |
| **Saúde e custo** | Fontes (WhatsApp, Google, Telegram), sonda, gasto OpenRouter por tarefa/oficina vs teto | Links de reconexão |
| **Ajustes** | Autonomia por tipo (L0–L3), horário silencioso, horários de briefing | — |

### O que precisa existir antes (e já pode nascer nos changes da fila)

- **API de leitura** versionada (`/v1/today`, `/v1/proposals`, `/v1/activity`, `/v1/jobs`,
  `/v1/contacts/policy`, `/v1/study/...`) e **ações** que reaproveitam o mesmo código dos
  botões do Telegram. Cada change acima deve expor o que cria por API, mesmo sem tela.
- **Eventos ao vivo** por SSE (`/v1/events`) para a tela atualizar quando um job termina.
- Front sem build pesado (ex.: HTMX ou Preact servidos estáticos) para não criar mais um
  container nem toolchain.

## 11. Controle de contatos e grupos (ingestão e envio)

Hoje: `EVI_WHATSAPP_SKIP_GROUPS=true` e `EVI_WHATSAPP_GROUP_WHITELIST` no `.env` (estático,
exige reiniciar e rodar `setup-evolution.sh`). Contatos individuais não têm controle.

**Proposta: política no banco, editável pelo Telegram (e depois pela tela da §10).**

| Alvo | Ingestão (padrão) | Envio (padrão) |
|---|---|---|
| Contato individual | ligada | segue a fase de envio (§9) |
| **Grupo** | **desligada** | **desligado** |

- **Ingestão desligada** quer dizer que a mensagem é descartada no filtro do webhook, **antes**
  de timeline, perfil, conhecimento de contato, dívidas, promessas, RAG e resumos. Só fica um
  contador anônimo para a sonda de saúde.
- **Liberar um grupo** pode ter escopo: `tudo` ou `só arquivos e avisos` (útil para o grupo da
  turma: materiais e datas de prova, sem a conversa inteira).
- **Comandos:** "para de ler o Fulano", "não envia nada para o Fulano", "libera o grupo X só
  para arquivos", "quem está bloqueado?". Todos determinísticos, sem LLM, com confirmação
  mostrando nome + número/JID.
- **Bloquear também pergunta:** "apagar o que já guardei de Fulano?" (timeline, perfil,
  vetores, dívidas). Executar só com "sim".
- **E-mail:** o mesmo modelo por remetente/domínio para a leitura (ex.: não ingerir newsletter)
  e para o envio.
- Migração: os JIDs da whitelist atual viram política "ingestão ligada" no banco; o `.env`
  passa a ser só o padrão inicial.

## 12. Estudos: faculdade e mestrado

Hoje existe a tarefa "do mestrado" no Google Tasks e nada mais estruturado.

### Modelo

- **Disciplina:** nome, curso (graduação/mestrado), professor, pasta de materiais, onde chegam
  os avisos (grupo da turma, e-mail, AVA), plano de ensino.
- **Grade de aulas:** **um CSV padronizado** (decisão de 20/10, as grades variam demais para
  recorrência), detalhado abaixo. O CSV é a fonte; o EVI publica as aulas numa agenda
  "Estudos" do Google Calendar.
- **Material:** **enviado por você no Telegram, manualmente** (decisão de 20/10: as origens
  variam demais para automatizar). Graduação e mestrado têm aulas, então o mesmo fluxo vale
  para os dois. Detalhes abaixo.
- **Plano de ensino:** PDF lido pela oficina → cronograma (tema por aula, leituras, **datas de
  entrega e prova**) → prazos viram tarefas e lembretes (com a sua aprovação).

### Modelo de CSV da grade

**Uma linha por encontro, com data explícita.** Não há regra de recorrência: feriado, reposição,
aula cancelada e semestre irregular viram simplesmente linhas a mais ou a menos.

```csv
disciplina;data;inicio;fim;descricao;tipo;local;curso
Metodologia Científica;04/11/2026;19:00;22:30;Revisão bibliográfica — cap. 3;aula;Sala 204;mestrado
Metodologia Científica;11/11/2026;19:00;22:30;;aula;Sala 204;mestrado
Metodologia Científica;18/11/2026;;;Entrega do projeto;entrega;;mestrado
Estatística Aplicada;06/11/2026;08:00;11:40;Regressão linear;aula;https://meet.google.com/abc-defg-hij;mestrado
Estatística Aplicada;27/11/2026;08:00;10:00;P1 — conteúdo até regressão;prova;Lab 3;mestrado
Estatística Aplicada;20/11/2026;;;Feriado;sem_aula;;mestrado
```

| Coluna | Obrigatória | Formato | Observação |
|---|---|---|---|
| `disciplina` | sim | texto | Nome como você quer ver no briefing; a mesma grafia agrupa as linhas |
| `data` | sim | `DD/MM/AAAA` ou `AAAA-MM-DD` | Fuso `America/Sao_Paulo` |
| `inicio`, `fim` | sim para `aula`/`prova` | `HH:MM` | Vazios em `entrega`/`sem_aula` = item do dia todo (prazo) |
| `descricao` | não | texto curto | Tema, leitura, observação; vai para o briefing e para a busca de material |
| `tipo` | não (padrão `aula`) | `aula` · `prova` · `entrega` · `seminario` · `sem_aula` | `prova`/`entrega` geram lembretes (ex. 7 e 1 dia antes); `sem_aula` cancela o que houver naquela data |
| `local` | não | sala ou link | Link de reunião vira botão no briefing |
| `curso` | não | `graduacao` · `mestrado` | Para separar visões e o plano semanal |

**Regras de importação (para a spec):**

- **Como chega:** você envia o `.csv` no Telegram (ou deixa em `Estudos/grade.csv`). Aceita `;`
  ou `,` (Excel/Sheets em português exportam com `;`) e UTF-8 com ou sem BOM. Colunas
  extras são ignoradas com aviso.
- **Validação antes de tudo:** relatório por linha (data inválida, `fim` antes de `inicio`, linha
  duplicada, choque com outro evento da agenda) e um resumo do tipo "3 disciplinas, 41 aulas,
  2 provas, 3 entregas, 1 feriado — publicar?". Nada é criado sem o seu ✅.
- **Idempotente:** a chave de cada linha é `disciplina + data + inicio`. Reenviar o CSV
  **atualiza** o que mudou, **cria** o que é novo e **pergunta** antes de remover linhas que
  sumiram. Dá para manter uma planilha viva e reexportar quando a grade mudar.
- **Destino:** agenda separada "Estudos" no Google Calendar (o EVI só mexe nela), com o id
  da linha na descrição do evento para conciliar depois.
- **Atalho:** se a grade vier em PDF ou foto, a oficina pode **gerar o CSV** para você revisar
  (proposta). O CSV continua sendo o formato de verdade.
- **Modelo para baixar:** `/grade modelo` devolve o CSV de exemplo acima.

### Envio de material pelo Telegram

Uma só porta de entrada: **mandar o arquivo para o EVI no Telegram**, ou **encaminhar** a
mensagem do grupo da turma, do e-mail no celular etc. O grupo continua fora da ingestão (§11);
quem decide o que entra é você.

**Associar o arquivo à aula com o mínimo de digitação:**

| Como você envia | O que o EVI faz |
|---|---|
| Arquivo **sem legenda** | Sugere a aula pela grade: a de hoje, senão a mais próxima (anterior ou seguinte, dentro de ±3 dias). Responde "📎 *slides.pdf* → **Metodologia, 04/11** (Revisão bibliográfica)?" com botões **✅** · **outra aula** · **outra disciplina** · **não é de estudo** |
| Legenda com a disciplina (ou apelido) | `metodologia`, `estat` → aula mais próxima daquela disciplina, mesma confirmação |
| Legenda com disciplina **e data** | `estat 27/11` → associa direto e só confirma |
| Vários arquivos de uma vez (álbum) | Uma confirmação para o lote |
| Legenda com tipo | `estat plano de ensino`, `metodologia leitura` → muda o tipo do material (abaixo) |

**Tipos de material:** `aula` (slides, notas — padrão), `leitura` (artigo, capítulo),
`plano` (plano de ensino → extração de cronograma e prazos, §12), `enunciado` (trabalho ou lista
→ propõe tarefa com prazo), `anotacao` (sua foto do quadro, áudio, texto pós-aula).

**O que acontece depois do ✅:**

1. O arquivo é salvo em `Estudos/<curso>/<disciplina>/<AAAA-MM-DD>/<nome>`, com dedupe por hash
   (reenviar o mesmo arquivo não duplica; só oferece reassociar).
2. Um registro `study_material` (disciplina, aula, tipo, hash, caminho, origem = Telegram, data
   de envio) liga o arquivo à linha da grade.
3. Texto extraído (PDF, PPTX/DOCX convertidos, OCR de imagem) é indexado no RAG com disciplina
   e data, para a busca "o que o professor falou sobre regressão?".
4. Conforme o tipo: `aula`/`leitura` → **nenhum resumo automático**; a confirmação ganha o botão
   **[resumo]** e o resumo só é gerado quando você toca (decisão de 20/10); `plano` → cronograma
   e prazos como proposta; `enunciado` → tarefa com prazo como proposta.

**Limites e cuidados:**

- A **Bot API do Telegram** só baixa arquivos até **20 MB** pelo servidor padrão. Acima disso:
  avisar e sugerir mandar em partes ou deixar o arquivo direto na pasta `Estudos/` do host (o EVI
  percebe na varredura e pergunta a associação). Um servidor local da Bot API (até 2 GB) seria
  um container a mais; só se aparecer necessidade real.
- Formatos: PDF, PPTX, DOCX, XLSX, imagens, áudio (anotação falada, transcrita como a voz já é).
  Outros: guardados sem extração, com aviso.
- O material é seu, então pode ir ao OpenRouter ZDR para resumo, sem conflito com a regra de
  privacidade. Arquivo encaminhado de terceiros entra **delimitado** (`wrap_external`), como todo
  conteúdo externo.
- `/estudos` lista as disciplinas com a contagem de materiais por aula e as aulas **sem
  material**, para você saber o que falta mandar.

### No dia de aula

| Momento | O EVI faz |
|---|---|
| Briefing da manhã | Linha "📚 19h Metodologia — tema: X; leitura: cap. 3" com botões **[resumo da leitura]** · **[rever aula passada]** |
| Antes da aula (ex. 2 h) | Lembrete com o material do dia e o botão **[resumo]**. Só ao tocar: **resumo do material** (Haiku 5.5 lê o PDF/slide) e 3–5 perguntas para chegar preparado. Nunca gerado sozinho |
| Depois da aula | "Como foi Metodologia? Manda áudio, foto do quadro ou as anotações." Guarda as anotações; o **resumo da aula** (`Estudos/<disciplina>/<data>/resumo.md`, junto com o material, com **pendências** como propostas) só sai quando você toca **[resumo]** |
| Semanal (domingo à noite) | Plano da semana: aulas, leituras pendentes, entregas próximas, sugestão de blocos de estudo nos horários livres da agenda (como proposta de evento) |
| Perto de prova | Revisão: resumo dos resumos da disciplina + perguntas para treino pelo Telegram |

### Cuidados

- Material da faculdade costuma ser **seu** (slides, PDFs), então pode ir ao OpenRouter ZDR
  sem conflito com a regra de privacidade.
- Sem integração com AVA (Moodle, Classroom): a entrada é manual pelo Telegram. Se algum
  dia a maior parte vier de um mesmo lugar com API, vira lacuna (§7) e change próprio.
- Começar com grade + envio de material + briefing do dia de aula (sem LLM além da extração de
  texto) e medir uso antes de investir nos resumos.

**KPI de exemplo:** em 4 semanas, ≥ 50 % das aulas com material ou resumo registrado; ≥ 1
prazo capturado automaticamente do plano de ensino sem erro de data.

## 13. Perguntas em aberto (para você)

1. **Estudos:** resolvido (§12): grade por CSV, material manual pelo Telegram, resumos só sob
   demanda (botão **[resumo]**).
2. **Pedidos pelo WhatsApp:** que tipo de pedido aparece mais (favores, trabalho, família)?
   Viram tarefa no Google Tasks ou em outro lugar?
3. **Autonomia:** há algo que você aceitaria que o EVI fizesse **sem** perguntar (L2/L3)? Por
   exemplo arquivar newsletter, aceitar convite sem conflito, resumir o material da aula assim
   que ele chega.
4. **Oficina:** quais pastas reais ela poderia ler (ex.: Documentos/Mestrado) e quais nunca?
5. **Orçamento:** US$ 5/mês para a oficina, separado do teto atual, está bom? Usar Sonnet só com
   o seu ok por job?
6. **Interface:** prefere começar pelo Mini App do Telegram ou pela PWA instalável?

## Referências

- LangChain, "Introducing ambient agents" / Agent Inbox — https://www.plushcap.com/content/langchain/blog/langchain-introducing-ambient-agents
- Sequoia Training Data, "Ambient Agents and the New Agent Inbox" (Harrison Chase) — https://inferencebysequoia.substack.com/p/ambient-agents-and-the-new-agent
- AgentMail, padrões de human-in-the-loop (rascunho → aprovação) — https://www.agentmail.to/docs/knowledge-base/human-in-the-loop
- Claude Code headless (`claude -p`), visão geral — https://claudemaster.net/features/claude-code-headless
- Uso de assinatura em integrações (fonte secundária, conferir) — https://smartscope.blog/en/ai-development/claude-code-reasoning-subscription-system-integration/
- Termos do Claude Code comentados (fonte secundária) — https://autonomee.ai/blog/claude-code-terms-of-service-explained/
- Suporte Anthropic, Claude Code com plano Pro/Max (limites compartilhados) — https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan
- Claude Code, *Legal and compliance* (autenticação OAuth × API key, uso individual) — https://code.claude.com/docs/en/legal-and-compliance
- Mudança de créditos do Agent SDK anunciada e suspensa (fontes secundárias) — https://zed.dev/blog/anthropic-subscription-changes · https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026
- Retenção de dados de consumidor: 30 dias ou 5 anos com treino (2025, conferir se ainda vale) — https://www.techcrunch.com/2025/08/28/anthropic-users-face-a-new-choice-opt-out-or-share-your-data-for-ai-training
- OpenRouter, lista de endpoints ZDR (consultada em 2026-10-20) — https://openrouter.ai/api/v1/endpoints/zdr
- OpenRouter, coleção de modelos com tool calling — https://openrouter.ai/collections/tool-calling-models
