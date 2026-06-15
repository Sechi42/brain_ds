# Delta for datasource-readonly-secrets

> Slice 3 of `brainds-harness-orchestrator-flow-hardening`. Defines the
> read-only datasource access contract and the secret contract, and
> surfaces both in the harness.

## ADDED Requirements

### Requirement: read-only datasource access is the only path the harness exercises

When a connected data source is read by the harness, the connector MUST
open the source in read-only mode. For SQLite, this is the composition of
the read-only URI mode (`mode=ro`) and `PRAGMA query_only`, plus the
existing path sandbox. The read-only guarantee MUST hold for both
unauthenticated and authenticated sources.

#### Scenario: SQLite read-only enforcement with secret_ref

- GIVEN a SQLite data source descriptor with `kind: "sqlite"`, a sandboxed
  `path`, and an optional `secret_ref` naming a valid env var
- WHEN the connector opens the source
- THEN the URI includes `mode=ro` AND the connection issues
  `PRAGMA query_only` immediately after open
- AND any write attempt (INSERT, UPDATE, DELETE, CREATE, DROP) is rejected
  by the database engine, not just by the harness

#### Scenario: read-only holds for an unauthenticated SQLite source

- GIVEN a SQLite data source descriptor without `secret_ref`
- WHEN the connector opens the source and the harness runs a SELECT
- THEN the SELECT returns rows
- AND any write statement against the same connection fails with a
  read-only error

### Requirement: secret contract — referenced, never stored

A Data Source `details.connection` MAY include an OPTIONAL `secret_ref`
field whose value is the NAME of an environment variable (a string, not a
literal credential). The connector MUST resolve the credential value from
`os.environ` inside the open path. The raw credential value MUST NOT be
persisted to the store, to any card_sections, or to any `.elicit/`
artifact.

#### Scenario: secret_ref is stored as a name, not a value

- GIVEN a Data Source node whose `details.connection.secret_ref` is the
  string `BRAINDS_SRC_PWD`
- WHEN the node is serialized (e.g. to the store JSON or to disk)
- THEN the serialized payload contains the literal string `BRAINDS_SRC_PWD`
- AND the serialized payload does NOT contain the resolved value of
  `BRAINDS_SRC_PWD` from the environment

#### Scenario: anti-leak guard — resolved secret never reaches .elicit/

- GIVEN a Data Source node with `secret_ref = "BRAINDS_SRC_PWD"` and the
  env var `BRAINDS_SRC_PWD` is set to a sentinel value
  (e.g. `SENTINEL-LEAK-CANARY-12345`)
- WHEN a full explore + document + map + brd cycle runs against this
  source and writes all artifacts to `.elicit/`
- THEN no file under `.elicit/` (active cycle, archive, or any
  intermediate output) contains the literal string
  `SENTINEL-LEAK-CANARY-12345`

#### Scenario: missing env var fails closed, not open

- GIVEN a Data Source node with `secret_ref = "DOES_NOT_EXIST"` and the
  env var is unset
- WHEN the connector attempts to open the source
- THEN the open fails with a clear error that names the missing env var
- AND no default or placeholder credential is silently substituted

### Requirement: secret contract surfaced in the harness

`SOURCE_EXPLORATION_CONTRACT` in `brain_ds/mcp/grounding.py` MUST reference
the `secret_ref` mechanism (field name, source of resolution, and
no-persistence guarantee) so sub-agents can request / reference
credentials correctly. A guard test MUST assert that the contract text
mentions the string `secret_ref` and the no-persistence rule.

#### Scenario: SOURCE_EXPLORATION_CONTRACT mentions secret_ref

- GIVEN the harness is loaded
- WHEN `SOURCE_EXPLORATION_CONTRACT` is introspected
- THEN its serialized form contains the string `secret_ref` AND a clause
  stating the resolved value is not persisted
