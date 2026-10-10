## ADDED Requirements

### Requirement: Briefing groups WhatsApp items by what the user must do
When `EVI_REPLY_DEBTS_ENABLED=true`, the briefing's WhatsApp section SHALL list, in this order and continuously numbered with the rest of the briefing: conversations waiting for the user's reply (contact, age, wrapped preview), the user's pending promises, and pending dated commitments. Each item SHALL carry a ref (`reply_debt:<jid>` or `commitment:<id>`) in the `morning_briefing` snapshot.

#### Scenario: SCN-DEBT-06
- **GIVEN** one reply debt, one promise and one dated commitment
- **WHEN** the briefing is assembled
- **THEN** the WhatsApp section shows three labelled groups with one item each, and the snapshot maps each number to its ref

### Requirement: No per-capture WhatsApp notifications
When `EVI_REPLY_DEBTS_ENABLED=true`, capturing a commitment or promise SHALL NOT send a notification; the briefing is the only delivery channel for these items.

#### Scenario: SCN-DEBT-07
- **WHEN** a contact proposes "vôlei amanhã às 19h"
- **THEN** a dated commitment is stored and no Telegram or WhatsApp message is sent at capture time

### Requirement: Action rate per item type is reported
The weekly usage report SHALL show, per type (reply debt, promise, dated commitment), how many items were shown and the share the user acted on (replied, done or confirmed).

#### Scenario: SCN-DEBT-08
- **WHEN** the report runs over a week with 10 reply debts of which 4 were answered
- **THEN** it shows 10 shown and 40% acted for reply debts
