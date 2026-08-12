## ADDED Requirements

### Requirement: Address-book names are imported from a vCard
The system SHALL import contact names from a local vCard export, because WhatsApp never transmits them: Evolution only receives `pushName`, the name the contact chose for their own profile, and the phone's address book stays on the phone. The importer SHALL read only `FN`/`N` and `TEL`, handling vCard 2.1/3.0/4.0, line folding and quoted-printable.

An imported name SHALL be written to `display_name`, and any existing `pushName` SHALL be preserved as an alias so search keeps matching whichever name the user types. Resolution precedence becomes **address book > pushName > number**.

The import SHALL run as a local job taking a server-side path, never routing the file's contents through an LLM, and SHALL default to a dry run that reports the changes it would make — it touches thousands of rows at once.

#### Scenario: SCN-MEM-12
- **WHEN** the importer runs in dry-run mode against a `.vcf`
- **THEN** it reports matched, unmatched and unchanged counts and writes nothing
- **AND** confirming applies only the matched entries, setting `display_name` and keeping the previous label as an alias

### Requirement: Phone matching survives the Brazilian ninth digit
Matching a vCard number to an existing WhatsApp contact SHALL use `DDD + the last 8 digits`, not string equality on the full number. A mobile number is stored with or without the ninth digit depending on when the record was created — measured on the live registry, 1104 JIDs carry 13 digits and 84 carry 12 — and a vCard may hold either form for the same person.

The key SHALL be verified as unambiguous before use: on the live registry it produced 1187 distinct keys for 1187 Brazilian contacts with zero collisions. An entry matching more than one contact SHALL be reported as ambiguous and skipped rather than guessed.

#### Scenario: SCN-MEM-13
- **GIVEN** a contact stored as `5511987654321@s.whatsapp.net` (with the ninth digit)
- **WHEN** the vCard holds `(11) 8765-4321` (without it, and formatted)
- **THEN** the two are matched
- **AND** an entry whose key matches two different JIDs is skipped and counted as ambiguous
