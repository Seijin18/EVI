## ADDED Requirements

### Requirement: Recent WhatsApp messages come from the local timeline first
Listing or summarizing recent WhatsApp messages SHALL read the per-contact timelines recorded by the webhook (canonical identity, both sides) for direct conversations, and SHALL call Evolution only for whitelisted groups and for direct conversations with no local entries in the period, concurrently and within a total time budget, noting when some conversations could not be read. Third-party text SHALL stay wrapped as external content. `EVI_WHATSAPP_LOCAL_FIRST=false` SHALL restore the Evolution-only behaviour.

#### Scenario: SCN-WA-RECENT-01
- **GIVEN** three direct conversations with messages today in the local timelines and Evolution answering each request after 5 seconds
- **WHEN** the user asks to summarize today's WhatsApp
- **THEN** the summary covers the three conversations and no direct-conversation request is sent to Evolution

#### Scenario: SCN-WA-RECENT-02
- **GIVEN** a whitelisted group and Evolution not answering one of the requests within the budget
- **WHEN** recent messages are listed
- **THEN** the direct conversations and the answered group are listed and the reply says some conversations could not be read

### Requirement: Repeated WhatsApp summaries are served from a short cache
A WhatsApp summary for the same period SHALL be reused for up to 10 minutes unless a newer message has arrived.

#### Scenario: SCN-WA-RECENT-03
- **WHEN** the user asks for today's WhatsApp summary twice within 10 minutes with no new message in between
- **THEN** the LLM is called once
