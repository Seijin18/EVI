## ADDED Requirements

### Requirement: Security review is recorded and repeatable
The project SHALL keep a threat model and a findings register under `docs/security/`, every finding with evidence, severity and status, and an offline scan (`./scripts/evi-security-scan`) covering dependency vulnerabilities, secrets in git history, security lint rules, published ports, file permissions and routes without authentication. A change SHALL NOT be archived with a critical or high finding open.

#### Scenario: SCN-SEC-02
- **WHEN** a change is archived
- **THEN** `docs/security/findings.md` has no open critical or high finding

#### Scenario: SCN-SEC-03
- **WHEN** CI runs
- **THEN** dependency audit, secret scan and security lint run and fail the build on new findings

### Requirement: Container images are pinned
Every image in `docker-compose.yml` SHALL name an explicit version (no `latest` or branch tags).

#### Scenario: SCN-SEC-06
- **WHEN** the compose file is checked
- **THEN** no image uses `latest`, `main` or no tag
