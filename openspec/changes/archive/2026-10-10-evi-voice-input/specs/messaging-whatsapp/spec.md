## ADDED Requirements

### Requirement: Only the user's own WhatsApp audio is transcribed
`audioMessage` SHALL be parsed and fetched (`getBase64FromMediaMessage`) only when the sender is a configured control JID; it SHALL then be transcribed and handled like a control-chat text message, with the same echo line. Audio from any other sender SHALL NOT be downloaded or transcribed.

#### Scenario: SCN-VOICE-02
- **WHEN** the user sends a voice note to the control chat asking "quais meus compromissos de amanhã?"
- **THEN** the reply lists tomorrow's events and starts with "🎙️ Entendi:"

#### Scenario: SCN-VOICE-05
- **WHEN** a contact sends a voice note in a direct conversation
- **THEN** no media download or transcription happens and nothing is sent to anyone
