# Removed spec: `dev-bridge`

Kept here rather than under `specs/` because `openspec archive` cannot apply a
delta that removes *every* requirement — the rebuilt spec would have none, and
the validator rejects an empty spec. The directory `openspec/specs/dev-bridge/`
is therefore deleted outright by this change, and this file is the record of
what it contained and why it went.

## REMOVED Requirements

### Requirement: Pluggable dev CLI backend
**Reason**: The dev bridge is removed entirely. It never executed successfully in the containerised deployment — `_REPO_ROOT` resolved to `/` inside the image and the runner scripts were not present — and making it work would require mounting the repo writable into `agent-api` plus installing a code-editing CLI there, gated only by a WhatsApp JID from an unauthenticated webhook.
**Migration**: None. No replacement is provided; use `ssh` to run a coding CLI on the host. The archived changes `2026-06-03-dev-assistant-bridge` and `2026-08-01-evi-dev-bridge-multi-cli` retain the full design, including the backend `Protocol`, should the decision be revisited.

### Requirement: Approval applies real changes
**Reason**: Removed with the dev bridge.
**Migration**: None.

### Requirement: Dev bridge gated to control chat
**Reason**: Removed with the dev bridge. `dev:` / `dev approve` messages now fall through to the LLM as ordinary text.
**Migration**: None.

### Requirement: Propose preview toggle
**Reason**: Removed with the dev bridge, along with the `dev_bridge_state` table that backed it.
**Migration**: None. Existing installs keep an empty `dev_bridge_state` table; no `DROP` is issued.
