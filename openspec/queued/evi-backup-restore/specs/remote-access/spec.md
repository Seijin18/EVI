## ADDED Requirements

### Requirement: Stateful data is backed up daily, encrypted
A daily job outside the EVI process SHALL write, for `evidb`, `windmill` (`pg_dump -Fc`), the Postgres globals, `data/contact_memory`, `EVI_WORKSPACE` and `.env`, a backup encrypted with a GPG public key and a manifest with SHA-256 and row counts. No plaintext dump SHALL be written to disk. It SHALL keep the 7 latest daily and 4 weekly backups, SHALL refuse to run without a recipient or with less than 2 GB free, and a failed run SHALL NOT delete or promote anything.

#### Scenario: SCN-BKP-01
- **GIVEN** a configured recipient and a healthy Postgres
- **WHEN** `scripts/evi-backup` runs
- **THEN** a dated directory with encrypted files and a `MANIFEST.json` exists, every file has mode 0600, and no unencrypted dump is on disk

#### Scenario: SCN-BKP-02
- **GIVEN** 9 daily backups and the disk below 2 GB free
- **WHEN** the job runs
- **THEN** it exits non-zero without deleting any backup and records `last_error`

### Requirement: Backups are proven restorable
A weekly `--verify` SHALL restore the latest backup into a disposable Postgres container without network and compare row counts with the manifest. Without a decryption key it SHALL check SHA-256 and `pg_restore --list` only and report "integrity only".

#### Scenario: SCN-BKP-03
- **GIVEN** the latest backup and a verification key
- **WHEN** `evi-backup --verify` runs
- **THEN** both databases restore in a throwaway container and the row counts equal the manifest

#### Scenario: SCN-BKP-04
- **GIVEN** a backup file truncated by half
- **WHEN** `evi-backup --verify` runs
- **THEN** it fails on the SHA-256 check and records the error

### Requirement: Missing or failing backups reach the user
The watchdog SHALL send one Telegram alert when the last successful backup is older than 36 hours or the last verification failed, and one message when it recovers.

#### Scenario: SCN-BKP-05
- **GIVEN** a last successful backup 40 hours old
- **WHEN** the watchdog runs twice
- **THEN** exactly one alert is sent, and one recovery message follows the next successful backup
