## MODIFIED Requirements

### Requirement: Address-book names are imported from a vCard
The system SHALL import contact names from the user's address book, because WhatsApp never transmits them: Evolution only receives `pushName`, the name the contact chose for their own profile. Sources SHALL be a local vCard export (reading only `FN`/`N` and `TEL`, handling vCard 2.1/3.0/4.0, line folding and quoted-printable) and the Google account address book (People API, read-only, only names and phone numbers), both applied by the same importer.

An imported name SHALL be written to `display_name` with its source (`vcard` or `agenda`), and any existing `pushName` SHALL be preserved as an alias so search keeps matching whichever name the user types. Resolution precedence becomes **name set by the user in chat > address book > pushName > number**; an import SHALL never overwrite a name the user set in chat, and a phone that matches two different address-book names SHALL be reported as ambiguous and left unchanged.

The import SHALL run as a local job, never routing address-book contents through an LLM, and SHALL default to a dry run that reports the changes it would make.

#### Scenario: SCN-MEM-12
- **WHEN** the importer runs in dry-run mode against a `.vcf`
- **THEN** it reports matched, unmatched and unchanged counts and writes nothing
- **AND** confirming applies only the matched entries, setting `display_name` and keeping the previous label as an alias

#### Scenario: SCN-NAME-02
- **GIVEN** the user named a contact "Hollmann" in chat and the address book calls the same number "Pedro H"
- **WHEN** the address-book sync runs
- **THEN** the contact is still "Hollmann"

#### Scenario: SCN-NAME-03
- **GIVEN** a WhatsApp contact shown as "+55 11 94826-0209" and an address-book entry "Hollmann" with "(11) 4826-0209"
- **WHEN** the address-book sync runs
- **THEN** the contact is named "Hollmann" and the previous label is kept as an alias

## ADDED Requirements

### Requirement: The Google address book is synced daily
A scheduled job SHALL read the Google account address book once a day through Windmill (OAuth `contacts.readonly`), keep only names and phone numbers, and apply them through the address-book importer.

#### Scenario: SCN-NAME-01
- **WHEN** the daily sync runs against a fixture of two People API pages
- **THEN** all entries are read and only name and phone numbers reach the importer

### Requirement: A LID contact takes the name of its paired phone
A `…@lid` contact paired with a phone JID SHALL be shown with the name resolved for the phone JID.

#### Scenario: SCN-NAME-04
- **GIVEN** `…@lid` paired with `5511948260209@s.whatsapp.net`, named "Hollmann"
- **WHEN** the WhatsApp summary lists that LID conversation
- **THEN** it is shown as "Hollmann"
