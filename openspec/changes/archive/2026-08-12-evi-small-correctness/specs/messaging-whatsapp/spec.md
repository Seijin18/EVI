## ADDED Requirements

### Requirement: Seen-id eviction keeps the newest ids
The WhatsApp dedupe store SHALL evict in insertion order, so trimming to `_MAX_SEEN_IDS` drops the oldest ids and always retains the most recently seen. Trimming an unordered `set` is not permitted — which ids survive is arbitrary, so a just-seen message can be evicted while an older one is kept, letting a duplicate through. The on-disk JSON array format is unchanged, so existing `evolution_seen_ids.json` files keep loading.

#### Scenario: SCN-WA-17
- **GIVEN** `_MAX_SEEN_IDS` seen ids already stored
- **WHEN** a new id is claimed and the store is trimmed
- **THEN** the newest id is still present and the oldest was the one dropped
- **AND** re-claiming the newest id returns False (still deduped)
