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
| `evi-study-calendar` | Fila de 20/10, depois de `evi-contact-policy` (ativo); 0 LLM |
| `evi-capability-gaps` | Depois de `evi-study-calendar`; ~0 LLM |
| `evi-approval-inbox` | Depois de `evi-capability-gaps`: migra as confirmações criadas pelos três anteriores |
| `evi-backup-restore` | F13 (segurança, médio); independente dos demais, 0 LLM — pode ser ativado logo após `evi-contact-policy` |
