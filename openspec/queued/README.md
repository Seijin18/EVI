# Changes na fila

Changes **já propostos por completo** (proposal, design, tasks, specs delta) que
aguardam a vez. O projeto mantém um único change ativo em `openspec/changes/`;
o que está aqui não aparece em `openspec list` e não é implementado.

Para ativar o próximo, depois de arquivar o atual:

```bash
openspec list                      # deve estar vazio
git mv openspec/queued/<slug> openspec/changes/<slug>
openspec validate <slug> --strict
```

Antes de ativar, releia o `design.md`: o código pode ter mudado desde a proposta
(em especial, paths citados em `Files:`).

Ordem: [`BACKLOG.md`](../BACKLOG.md) → "Fila atual".

| Change | Por que está aqui |
|---|---|
| `evi-security-review` | Próximo depois de `evi-promise-context`; a contenção do F1 (task 1.1) pode ir antes como hotfix |
| `evi-contact-knowledge` | Depende de `evi-promise-context` (`llm_structured`, avaliador; task 2.3 liga o conhecimento ao prompt de promessas) |
| `evi-contact-names` | Depende de `evi-contact-knowledge` (identidade canônica `@lid`↔telefone) |
| `evi-ux-review` | Último da fila: a apresentação depende do conteúdo dos anteriores (títulos de promessa, nomes de contato) |
