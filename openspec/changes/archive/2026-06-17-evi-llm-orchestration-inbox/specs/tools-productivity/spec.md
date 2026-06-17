## ADDED Requirements

### Requirement: Delete emails by Gmail query
The tool `delete_emails_by_query` SHALL trash messages matching a Gmail search query via Windmill.

#### Scenario: SCN-UX-INBOX-02
- **WHEN** user asks to delete AliExpress/OLX emails
- **THEN** agent calls delete tool without requesting message IDs
