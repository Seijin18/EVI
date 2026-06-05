# Proposal: evi-deprecate-n8n-spec

## Why

`integrations-n8n` spec duplicates Windmill requirements and wastes agent context.

## What Changes

Remove `openspec/specs/integrations-n8n/spec.md`; n8n deprecation remains in `integrations-windmill` SCN-DEP-02.

## Out of scope

Deleting n8n fixture folders in tests (harmless).
