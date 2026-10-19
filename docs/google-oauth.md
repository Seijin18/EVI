# Google OAuth do EVI — como está configurado e como reconectar

Estado em **2026-10-19**. Complementa `windmill/README.md` (passo a passo de cada API) e
`docs/security/findings.md` (F11).

## App em Produção (sem expiração de 7 dias)

- Projeto Google Cloud: **EvolvingVirtualInteligence** → Google Auth Platform.
- **Público-alvo**: tipo *Externo*, status **Em produção** (publicado em 2026-10-19). Antes estava em
  *Testando*, em que o Google expira o token de renovação a cada 7 dias — foi o que derrubou agenda,
  tarefas e Gmail em 10/10 e 18/10.
- App **não verificado** de propósito: a verificação só serve para abrir o app a outras pessoas. No
  consentimento aparece "O Google não verificou este app"; para uso próprio: *Avançado → Acessar
  EvolvingVirtualIntelligence (não seguro)* → *Continuar*. Limite: 100 usuários (usa 1).
- **Branding** (exigido para poder publicar): página inicial `https://seijin18.github.io/EVI/`,
  política de privacidade `https://seijin18.github.io/EVI/privacy.html`, domínio autorizado
  `seijin18.github.io`, e-mails de suporte/contato do próprio dono.
- As duas páginas vivem **só na branch `gh-pages`** de `Seijin18/EVI` (repositório público). A
  `main` não foi publicada: ela inclui o registro de achados de segurança. Para editar as páginas,
  trabalhe nessa branch isolada, nunca com `git push` da `main`.
- Revogar o acesso (`myaccount.google.com/permissions`) é o único jeito de pedir nova reconexão.

## Conexões no Windmill

| Recurso (Windmill) | Tipo | Escopos | `.env` |
|---|---|---|---|
| `u/shiba144/calendar` | gcal | `calendar.events` | `WINDMILL_GCAL_RESOURCE` |
| `u/shiba144/gtasks` | gtasks | `tasks` | `WINDMILL_GTASKS_RESOURCE` |
| `u/shiba144/gmail` | gmail | `gmail.readonly` + `gmail.modify` | `WINDMILL_GMAIL_RESOURCE` |

Os nomes antigos (`comprehensive_gcal`, `evi_gtasks`, `evi_gmail`) foram apagados e recriados; o
Windmill nomeou as novas com o padrão (`calendar`, `gtasks`, `gmail`) e o `.env` foi atualizado
(cópia em `data/backups/env-pre-oauth-*`). Após mudar o `.env`:
`docker compose up -d --force-recreate agent-api`. Confirmar com `POST /jobs/probe?wait=true`.

> `gmail.modify` inclui, tecnicamente, a permissão de enviar e-mail. O EVI não tem ferramenta de
> envio e só usa o escopo para ler e mandar para a lixeira — risco aceito, igual ao de antes.

## Como reconectar uma fonte

1. Windmill (`http://localhost:8001`, só loopback; remoto: `docs/remote-access.md`) → **Resources**.
2. Apague a conexão expirada (⋮ → Delete) e use **Add resource** → tipo (`gcal`/`gtasks`/`gmail`).
   *Refresh token* não adianta: o Google responde `invalid_grant` para token expirado/revogado.
3. Escolha a conta → *Avançado → continuar* → permitir. Dê à conexão o nome que o `.env` espera.
4. Faça isso **num navegador comum**: o login abre em popup e devolve o resultado para a página que o
   abriu; o navegador embutido do Claude não suporta isso (a aba fecha e a conexão não é salva).

## Escopos do cliente `gmail` (configuração da instância)

O cliente OAuth `gmail` do Windmill não define escopos por padrão (pede só enviar). O `connect_config`
com `gmail.readonly` e `gmail.modify` fica em **Instance settings → OAuth → gmail** (bloco em
`windmill/README.md`). Se a tela "Add resource → gmail" mostrar só "enviar", a configuração foi perdida.

Alterar pela API (`POST /api/settings/global/oauths`): o corpo **precisa** ser `{"value": {...}}`
com o objeto completo (gcal, gcloud, gmail, gtasks). Sem o `value` a configuração inteira é
zerada (aconteceu em 2026-10-19 por ~1 min; restaurada da cópia de segurança). Sempre salve antes
uma cópia (0600, contém o segredo do cliente) e confira os quatro clientes depois.
