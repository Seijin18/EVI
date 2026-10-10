## ADDED Requirements

### Requirement: The user's voice messages on Telegram are transcribed and handled as text
When `EVI_VOICE_ENABLED=true`, a `voice` or `audio` message from the configured Telegram chat SHALL be downloaded through the Bot API (`getFile`), transcribed by the Gemini provider in a single call without tools, and processed by the normal chat flow as the user's text. The reply SHALL start with a line echoing the transcription ("🎙️ Entendi: …").

#### Scenario: SCN-VOICE-01
- **GIVEN** a voice note saying "marca dentista amanhã às três da tarde"
- **WHEN** it arrives on Telegram
- **THEN** an event "dentista" is created for tomorrow 15:00 and the reply starts with "🎙️ Entendi:"

### Requirement: Voice input never fails silently
A voice message SHALL always get a reply. With the flag off, with `EVI_LLM_PROVIDER=ollama`, when the audio exceeds `EVI_VOICE_MAX_SECONDS`, or when download or transcription fails, the reply SHALL say briefly why. An empty transcription SHALL ask the user to repeat.

#### Scenario: SCN-VOICE-03
- **WHEN** a 10-minute voice note arrives with `EVI_VOICE_MAX_SECONDS=300`
- **THEN** the user is told the audio is too long and no transcription call is made

#### Scenario: SCN-VOICE-04
- **WHEN** a voice note arrives with `EVI_LLM_PROVIDER=ollama`
- **THEN** the reply says audio is not supported in this mode

### Requirement: Voice turns are measurable
`turn_log` SHALL record `input_kind` (`text` or `voice`) and the weekly report SHALL show voice turns and their success rate.

#### Scenario: SCN-VOICE-06
- **WHEN** the report runs over a week with 4 voice turns, 1 of them corrected
- **THEN** it shows 4 voice turns and 75% success
