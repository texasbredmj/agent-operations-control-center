# Threat model

The trust boundary is the API and its PostgreSQL transactions. A browser can be modified, its buttons
can be bypassed and request bodies can be forged. These actions do not grant a role or choose a project.
Credentials, application code, configured principal identities and database administrators are trusted.
This lab binds services to localhost and uses distinct random role credentials; it has no public
deployment, external model connection or arbitrary tool execution.

| Threat | Implemented control and verification |
| --- | --- |
| UI bypass / forged role | Every read/write authenticates; server maps role/project; strict schemas reject extra fields |
| Cross-project inspection | Scoped queries return 404 and omit other projects from totals; integration tests inspect both paths |
| Unapproved effects | Pending tasks cannot be claimed; separate approver checks action hash under lock |
| Stale or racing decisions | Version comparison plus task lock; concurrent approve/reject test permits one winner |
| Duplicate delivery | Project/key/actor/body-bound durable command response; replay tests check one event/effect |
| Worker duplication or interruption | SKIP LOCKED claim, lease and claim fencing; unique ledger key and transactional effect |
| Cancellation race | Lock and claim invalidation before effect; terminal cancellation returns conflict |
| Unsafe retry | Only transient failure before effect, bounded attempts; permanent/mismatched outcomes cannot retry |
| False completion claim | Independent quantity/receipt read; mismatch fixture remains failed with evidence |
| Scripted task title / credential leakage | React escapes text; no arbitrary HTML; CSP; memory-only credential; no keys in artifacts |
| Resource exhaustion | Project capacity lock, bounded input/page sizes, SQL deadlines and container memory limits |

Opaque tokens are static and have no expiry or remote revocation API. Removing a credential and
restarting the API revokes it for subsequent requests. Local operators who can read `.env` can assume
its configured roles. A production system needs managed identities, TLS, rate limiting, separate
database roles, encrypted storage/backup policy and audited secret rotation. Database superusers can
modify history; no cryptographic audit immutability is claimed.

PostgreSQL gives correctness for the one database ledger effect. The worker's claimed tool records
are not a general external execution attestation. The mismatch case deliberately commits incorrect
fixture data to demonstrate detection; it cannot be retried automatically. No arbitrary external
effect should be substituted without an adapter-specific authorization and reconciliation design.

The worker does not renew long-running leases because its only operation is a short transaction.
Adding slow/external work requires lease renewal and effect-specific fencing. Agent resource counters
are shared infrastructure values, not private tenant accounting. Live advisory scans are separate from
required correctness CI and do not imply freedom from undisclosed vulnerabilities.
