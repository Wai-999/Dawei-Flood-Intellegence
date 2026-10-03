# Security, threat model and pre-mortem

## Boundaries and controls

Protected operational data is served by authenticated APIs and is absent from the public static bundle/image. Contributor report/history/update/feedback access is owner-scoped; reviewer/admin raw evidence and audit access is separate from analytic exports. API and repository methods enforce roles even when called without the UI. User deactivation is administrator-only, requires a reason, revokes sessions and cannot remove the last active administrator. Account provisioning/recovery uses the private operator CLI; broad self-registration is disabled.

Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Random sessions are hashed in SQLite, expire after eight hours and check active identity. Cookies use HttpOnly/SameSite=Strict and Secure in production. Mutation origin must equal the configured origin and session CSRF must match. Persistent hashed login buckets limit account and peer address attempts across worker restarts; failed login audits omit password/plain username/IP. Stolen valid sessions remain a risk until expiry/revocation; use an approved identity/access gateway and privileged MFA for exposed production.

Gunicorn/Caddy production configuration has request/header/time limits, exact trusted Host, explicit proxy addresses, overwritten forwarding headers, HTTPS enforcement, HSTS, 64 KiB request bodies, strict JSON/framing, self-only CSP, no frame embedding/MIME sniffing and parameterized SQL. DOM content uses textContent. Provider URLs are restricted to owned HTTPS API hosts; redirects are refused. Caddy is the only published ingress. TLS configuration validation is not a verified deployed certificate. Loopback read-only preview is never a production identity mode.

## Threats and mitigations

| Threat | Control | Residual / operator action |
|---|---|---|
| Stolen credentials or compromised contributor | Individual roles, session expiry, audited deactivation/revocation, private allowlist | MFA/gateway, rotate provider keys, investigate prior submissions |
| Brute force / denial of service | Persistent account/address throttle, bounded body/headers, proxy and worker timeouts | Pilot load test, host/WAF quotas; account throttling can temporarily deny a legitimate user |
| CSRF / privilege escalation | Strict origin/CSRF/SameSite, server-side role and ownership tests | Protect operator sessions; independent security review |
| SQL/DOM/spreadsheet injection | Parameterized SQL, text DOM, restrictive CSP, CSV formula escaping, XLSX inline text, Sheets RAW | Never enable arbitrary HTML/formulas in operational data |
| Fabricated or copied reports | Raw/version provenance, validation, conflict flags, evidence independence, accountable human review | Matching sources are not automatically independent or true; investigate high-impact claims |
| Replay / accidental duplicate | Actor-scoped key/hash, transactional uniqueness and durable Telegram response/checkpoint | Similar observations may be real; reviewer decides audited supersession |
| Secret or private export leakage | Source-only Git/Docker exclusions, token/privacy scanner, export allowlist/RBAC/audit | Scanner is heuristic; operator reviews contents/history before publishing and rotates any leaked key |
| Tampered/lost backups | Signed HMAC manifests, checksums, integrity/FK/count checks, strict member allowlist, new-path restore | HMAC is not encryption and cannot resist stolen signing key/root; encrypted off-site copies and separate key custody |
| Wrong/stale coordinates or pledges | Reviewed supplied coordinates, field clocks, ETA/expiry/cancellation, unconfirmed delivery warning | Correct with source/reason; do not allocate solely from map/pledges |
| Hosting/connectivity/provider outage | Persistent volumes, retries/idempotency, explicit degraded health, local device draft, tested restore | Off-host alerts, actual recovery drill, one active consumer, fallback operator process |

Raw, audit, assessment versions, observations, claims, methods, review/resource events, evidence, outcomes, resolutions and priority snapshots reject destructive mutation through application triggers. Mutable current projections retain prior events. SQLite root/file administrators can bypass triggers; signed separately retained backups improve detection and do not make the database cryptographically immutable.

## Data minimization and secrets

No household identities, phone lists or medical case detail are required. Precise contacts/logistics are excluded from general analytics/exports and assistance feedback. Raw notes/evidence, audit actors and provider checkpoint/state are private operational data. No unauthenticated/public impact endpoint exists. Approve retention and any publication/de-identification policy before sharing data externally.

Secrets remain in ignored private files or an approved secret manager. Use Linux ownership 10001/mode600 for mounted readable files and mode700 secret directories. Encrypt host volumes/off-site backups, separate backup access and signing keys, and rotate compromised credentials immediately. Never put tokens in workflows, PRs, static assets, logs, URLs pasted to users or Docker build arguments. Recognizable-token scanning is mandatory but not exhaustive.

## Flood failure pre-mortem

Connectivity loss: communicate delayed observations, save drafts explicitly and resume with stable IDs. Verification overload: monitor oldest queue, prioritize contradictions/high-impact claims and preserve unverified labels. Selection bias: disclose partial inventory/unreported entries; obtain registry/exposure/access evidence before spatial inference. Stale intelligence: distinguish observation/submission/verification/field confirmation clocks. Telegram or Sheets outage: retain canonical data/checkpoints/outbox, inspect provider errors and repair access before audited requeue. Lost host: verify trusted signature, restore isolated data and source, revoke restored sessions, reconcile and restart one consumer. Confusing UI: conduct English/Burmese field acceptance and accessible device tests. Security incident: suspend affected integrations, deactivate users, preserve audit/raw evidence and follow the approved incident channel.

Before launch: provision access/TLS/volume encryption/keys, verify real providers, enable encrypted off-site backups and external alerts, measure capacity and complete field acceptance. These are launch commissioning gates; the repository implements their runtime controls without claiming an external service is active.
