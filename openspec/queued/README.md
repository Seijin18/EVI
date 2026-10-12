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
| `evi-contact-knowledge` | Depende de `evi-promise-context` (task 2.3 liga o conhecimento do contato ao prompt de promessas) |
