# Dawei Flood Intelligence — commissioning report

Updated 2026-10-03 UTC. **CURRENT PRODUCTION STATE: INFRASTRUCTURE-SELECTED (conditional).** The approved application release is unchanged. Oracle is excluded by the latest owner instruction. Google Free Tier IPv6/local-block-storage automation is prepared, but owner authorization, actual aggregate cost/traffic gates and every production commissioning check remain open. See [current free-hosting decision](free-hosting-decision.md). Synthetic cloud staging checks are historical; the anonymous Railway VM expired and has not been renewed. The tables below retain prior evidence and do not establish current production readiness.

## Pilot release completed — 2026-10-03 06:27:24 UTC

**Historical boundary, superseded by autonomous investigation: PRODUCTION HOST ACCESS REQUIRED.** The owner release gate is complete. Deployment requires an operator-controlled Linux host/account, approved SSH/access method, intended domain and DNS control. No production `.env`, private secret directory or project SSH host is configured in the available environment. No cloud deployment CLI/account is configured; no VM, domain or paid service was purchased. Do not request provider secrets before the host exists.

- Repository owner `Wai-999` merged [PR #1](https://github.com/Wai-999/Dawei-Flood-Intellegence/pull/1) at `2026-10-03T01:52:16Z`. Validated merge commit: `c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc`; source tree: `51959b0c47523fa41c2f271615edfb647f45b81f`, identical to the reviewed candidate.
- [Post-merge validation run 37087732219](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37087732219) completed successfully on that merge commit. No unresolved reviews/threads or application changes were found during the release recheck.
- Published [Dawei Flood Intelligence v0.1.0-pilot](https://github.com/Wai-999/Dawei-Flood-Intellegence/releases/tag/v0.1.0-pilot), marked **Pre-release**, at `2026-10-03T06:21:52Z`. Verified `refs/tags/v0.1.0-pilot` points exactly to the validated merge commit. SQLite schema: **2**. Only source/application artifacts are included; no operational files were attached.
- [Tag validation run 37102805964](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37102805964) and [release-image run 37102805989](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37102805989) both passed on the tagged commit. Release validation ran all 53 tests, explicit ES-module/compilation checks, dependency audit, Bandit, privacy scan, Docker readiness/private-file tests, signed restore/container recreation and Caddy checks before image publication.
- Immutable published image: `ghcr.io/wai-999/dawei-flood-intellegence@sha256:c6d38231fc37097dfef73643114de4f028369f886401b49ff130d4f31cdfff98` (Linux AMD64). Digest verified in successful build/push output and by pulling the artifact. **Both smoke scripts passed locally against this exact downloaded digest**, including signed backup/source/audit/schema restore and database persistence after container recreation. Disposable resources were removed; no public endpoint was opened.
- Release limitations and commissioning requirements are included in the public prerelease notes. This source release/image does not establish production deployment, host recovery, commissioned integrations or field acceptance. Deploy the pinned tag/commit/image, not an uncommitted tree or a later documentation-only commit.

## Historical release-gate recheck — 2026-10-03 01:44:15 UTC

At this earlier inspection the owner release gate was still open. The later completed-release evidence above supersedes that blocker; the following facts preserve the dated validation record.

- Independently fetched current PR head: `8d697b7e6241f64e07e8878b1308e83b80315035`; base/main: `15ff7782e3920eac2333d716d26bf9554def28b0`. PR is open, unmerged, mergeable and clean. No newer commits than the commissioning baseline were present before this documentation update.
- Four current Actions checks passed: test-security and container on both [PR run 37086125592](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37086125592) and [push run 37086123134](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37086123134). No submitted reviews, requested reviewers, issue/review comments or unresolved review threads were present.
- Main reports `protected: false`; repository/inherited ruleset listing is empty. The integration cannot read the administrative classic-protection endpoint (403); it was not granted broader permissions. Owner approval remains an explicit release gate independently of repository enforcement.
- Current remote tree `35d80803b8f51e0ef7a3aa9ffcededd1d7e89b27` matches the clean local checkout. All 64 tracked files were inspected for private artifact paths; no operational DB, snapshots, `.env`, secrets, backup/signing files, exports or private drill artifacts were tracked. Secret/privacy scan passed again.
- The historical `dawei-flood:commissioning-check` image was absent from the current Docker daemon. Rebuilt current candidate as `dawei-flood:release-gate`; build succeeded. New local ARM64 manifest-list digest: `sha256:64df27d0691e21efbd2eb4cf1380a32722605cadad95fc3d30fb3b5cde0c1d12`; runtime image configuration: `sha256:e9b52f53bcd5fda468832ceefd30ed45534c69b5b484b6dedb2a44ac56583945`. This is a local candidate artifact, not a published release image.
- Re-run **53/53 tests passed in 4.823 seconds** with authorized loopback access. An initial restricted-sandbox attempt could not bind sockets for four API test setups; the permitted run passed all cases without source changes. Both container smokes passed again, including non-root/readiness/private-file checks, signed backup/isolated restore/source/audit/schema checks, restart and container recreation. Compose and pinned Caddy validation passed.
- No P0/P1 regression was found in these checks. This documentation-only evidence update must also receive green CI before any approved merge. No production services or provider credentials were configured, and no deployment, pilot or owner operational acceptance is claimed.

## Historical pre-release validation evidence

- Repository: [Wai-999/Dawei-Flood-Intellegence](https://github.com/Wai-999/Dawei-Flood-Intellegence).
- Release: production-readiness candidate in [PR #1](https://github.com/Wai-999/Dawei-Flood-Intellegence/pull/1); merge approval and `v0.1.0-pilot` tag remain pending. There were no submitted PR reviews at inspection. Passing CI does not constitute owner approval.
- Revalidated application commit: `e2ecef05bd91de985bed8130a25740c6ba07998b`, tree `e29a7d9d6ffa6cad152c6746a3a1b56a2b9df0bb`. This commissioning change adds documentation and a container rehearsal to both workflows; it does not change application behavior. Its current checks must pass before release.
- Production URL: none supplied or commissioned.
- Latest inspected application CI: [run 37084498230](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37084498230), completed successfully on the application commit above; both test-security and container jobs passed. Consult [current PR checks](https://github.com/Wai-999/Dawei-Flood-Intellegence/pull/1/checks) for subsequent commits.
- Re-run locally: **53/53 tests passed** in 4.718 seconds, including integration simulations, security, migration, recovery, retries, correction removal and ownership checks. Python compilation and explicit ES-module syntax checks passed.
- Security checks: pinned-production dependency audit reported no known vulnerabilities at audit time; Bandit reported zero findings at all severities; tracked-source privacy scan passed. These are bounded checks, not a penetration test or an assertion of future vulnerability absence.
- Production Docker build passed. Local ARM64 image manifest digest: `sha256:cab111fc82ffade0c4e7788fd1a0ffee92c1f880e3561c22ceab9b3d4995d753`. Compose validation, pinned Caddy configuration validation, non-root/readiness/private-file smoke and persistent-volume restart passed. Caddy validation reported formatting and explicit-forwarding warnings, with no configuration error.
- New `scripts/commissioning-smoke.sh` passed against that image: read-only application root, private signing key, one-shot backup worker, signed isolated restore, source/audit/schema reconciliation, no published application port, and assessment/version persistence after container deletion and recreation. Temporary test volumes and containers were removed.
- No P0/P1 regression was found in these checks. Production environment, real-provider and field acceptance gates remain open; no operational acceptance is implied.

## Commissioning matrix

| Area | Evidence-backed state | Evidence and remaining gate |
|---|---|---|
| Core Application | IMPLEMENTED / TESTED | 53 tests, fresh-runner CI, non-root container readiness. Real-host deployment and endpoint acceptance pending. |
| Authentication | IMPLEMENTED / TESTED | Password hashing, hashed sessions, expiry/revocation, persistent login throttling and cookie tests. No named production users provisioned. |
| Authorization | IMPLEMENTED / TESTED | Server-side role, ownership, export, CSRF/origin and escalation tests. Operator account/role assignments and privileged-access policy pending. |
| Database | IMPLEMENTED / TESTED | SQLite schema 2, immutable raw/history/audit and migration tests; isolated real-source recovery verified. Production volume not provisioned. |
| HTTPS | CONFIGURED | Caddy validation and production proxy/origin tests pass. DNS, trusted certificate, external redirect/security checks and real named-user login NOT COMMISSIONED. |
| Persistent Storage | CONFIGURED / TESTED locally | Compose volumes and synthetic container recreation passed. Linux host reboot, host storage encryption and recovery NOT COMMISSIONED. |
| Telegram | IMPLEMENTED / TESTED with simulations | Private sender allowlist, malformed/duplicate/correction/checkpoint/retry/feedback tests. Real token, sender mapping and private end-to-end round trip NOT COMMISSIONED. |
| Google Sheets | IMPLEMENTED / TESTED with simulations | Owned-tab/header-safe RAW projection, retries/idempotency and stale-correction removal. Service account, approved destination and real writes NOT COMMISSIONED. |
| GIS / Geography | IMPLEMENTED / TESTED with synthetic coordinates | Prior browser map placement/clustering/filter/detail/layer checks. Operational source has no approved coordinates; canonical registry/aliases/coordinate provenance approval pending. |
| Priority Methodology | IMPLEMENTED; operational ranking NOT COMMISSIONED | Tests separate severity/confidence/completeness/freshness and versioned approved parameters. No approved source method supplied; numeric operational ranking remains unavailable. Owner must approve parameters or explicitly accept descriptive-only pilot scope. |
| Silent-Zone Methodology | IMPLEMENTED descriptive worklist; spatial inference DEFERRED | Unreported locations mean investigation needed, not low need or high severity. Complete registry and geographic/hazard/access/reporting evidence absent. |
| Imported Claims | Owner review pending | Ambiguous source claims require accountable review before use as facts. Preserve original values, source and history. Detailed source counts/results remain in private evidence. |
| Backup | IMPLEMENTED / CONFIGURED / TESTED locally | Signed database/source bundle, integrity/count/tamper tests and container worker rehearsal. Host key custody, schedule/retention acceptance and alarms pending. Signing does not encrypt a bundle. |
| Off-site Backup | NOT CONFIGURED / NOT COMMISSIONED | No approved storage account, encryption/key custody, separate credentials, retention or successful off-site copy evidenced. |
| Restore Drill | TESTED locally | Signed private source restored separately and synthetic container restore passed; details below. Hosted drill and measured operational RPO/RTO pending. |
| Monitoring | IMPLEMENTED / CONFIGURED in application | Safe public live/ready, administrator-only operational health, queues and failure state. External probes, host/disk/lock alerts and approved on-call destination NOT COMMISSIONED. |
| Governance | Draft procedures IMPLEMENTED; approval pending | Recovery/incident/key rotation documented in operations. Raw/evidence/audit/account/backup retention, sharing/export/de-identification and MFA/access-gateway policy require owner approval. Public release remains disabled. |
| Burmese Field Review | Localization IMPLEMENTED; review NOT COMPLETED | Centralized English/Burmese core labels and actions; prior browser inspection only. Technical prose remains partly English; field-language corrections require Burmese-speaking users. |
| Pilot | NOT STARTED | No named field group or recorded field acceptance. Repository simulations do not measure submission friction, abandoned drafts or actual review delays. |
| Performance | Pilot capacity NOT MEASURED | Single-host SQLite architecture is bounded; no production latency, throughput, lock contention, resource or provider-latency claim. Measure on the authorized host during the pilot. |
| Security Review | Repository checks TESTED; go-live review pending | Scans and application controls pass. Trusted HTTPS, external ports, named privileged users, monitored backups/workers and hosted recovery need real-host evidence. |
| Owner Acceptance | NOT RECORDED | Infrastructure, data, operations, provider and human acceptance gates below must be signed off before OPERATIONAL. |

## Private source recovery result

A local signed backup was restored into a new directory on 2026-10-03. Schema version 2, SQLite integrity `ok`, foreign-key checks, HMAC verification and source-file checks passed. Comparison verified restored counts and identical assessment, raw/version, claim, source, observation and relationship rows. Detailed operational counts and source measurements are retained only in private local evidence.

The measured local extraction/validation time is retained in private evidence. It excludes host provisioning, off-site retrieval, traffic switching, operator authentication and provider reconciliation and does not demonstrate hosted RTO. The backup action adds a subsequent live audit event outside the restored snapshot; this is expected.

Detailed result, bundle, restored DB and private key remain in ignored private storage; none are published. Default hourly frequency, 30-day local retention, RPO ≤ 1 hour and RTO ≤ 60 minutes remain proposed operating targets pending approval and a hosted drill. Off-site encryption, host loss and reboot remain untested.

## Outstanding external actions, in order

1. **Infrastructure operator:** supply an authorized Linux VM/account, domain/subdomain, DNS control, TLS contact and approved access method. No provider purchase was made. Use the exact approved pilot release, private `.env`/secrets, persistent encrypted storage, restricted SSH/firewall and named accounts; start only app + backup + proxy. See [deployment](deployment.md).
2. **Operations owner:** authorize encrypted off-site storage, separately held recovery key, backup retention and meaningful alert destination. Prove external HTTPS/security, readiness, host reboot persistence and isolated hosted restore; record measured RPO/RTO and source/audit parity. See [operations](operations.md).
3. **Provider owners:** place Telegram and Google secrets in private host files/secret manager, approve individual sender mappings and a test destination, then perform real round trips, correction/removal, unauthorized-input and restart/retry checks. Preserve unrelated Sheets tabs/cells. No secrets should be supplied in chat or committed.
4. **Data/domain owner:** approve the settlement registry and coordinate provenance/aliases, review quarantined claims, approve analytical/freshness parameters or explicitly defer ranking, and approve retention/export/sharing/privileged access/incident policies.
5. **Field/operational owner:** provide a small named pilot group (suggested 2–5 contributors, 1–2 reviewers, coordinator and administrator), conduct Burmese terminology review, execute the acceptance cases below, resolve critical defects and record operational acceptance.

Only these external authority/access/data/human boundaries prevent further operational commissioning. The original Google Sheet remains unchanged.

## Field and hosted acceptance record to complete

No row below is recorded as passed. Attach UTC time, exact release/image, named accountable tester, private evidence reference, expected/actual result and defect/retest outcome for each executed case. Keep report content and credentials out of public issues and CI logs.

| Acceptance group | Required real-environment cases | Current result |
|---|---|---|
| Infrastructure/security | DNS, HTTP redirect, trusted hostname/TLS, no certificate warnings, Secure/HttpOnly cookies, security headers, anonymous denial, named login, RBAC/export, public ports limited to 80/443 for application | NOT EXECUTED |
| Recovery/monitoring | Container recreation, host reboot, signed scheduled backup, encrypted off-site copy, retention/failure alert, isolated restore, source/audit parity, revoke restored sessions, readiness/worker/disk/lock alerts | Local recreation/restore passed; hosted cases NOT EXECUTED |
| Providers | Private Telegram full intake/review/verify/dashboard/feedback, malformed/missing/duplicate/unauthorized/correction/restart/send failure; real Sheets verified projection/correction/removal/header safety/retry and unchanged unrelated cells | Simulations passed; provider cases NOT EXECUTED |
| Data/GIS/methods | Reviewed names/aliases/coordinates, unknown coordinates excluded, placement/clusters/filters/detail/layers, claim interpretations with reviewer/reason/time, approved or explicitly deferred ranking/freshness | Synthetic UI/code passed; owner cases NOT EXECUTED |
| Controlled field pilot | Normal/incomplete/update/duplicate/conflict/unknown-coordinate/stale report; pledge/dispatch/delivery/receipt/expiry; unauthorized access/export; backup during use; restart/recovery | Automated cases passed; field cases NOT EXECUTED |
| Human/performance | Burmese prompts/labels/validation/assistance review; time-to-submit, confusion, abandoned drafts, correction/duplicate/conflict rates, reports/day, median review delay/backlog; CPU/memory/disk growth/latencies/lock contention | NOT MEASURED |
| Final acceptance | Current approved release, all required commissioning evidence, pilot-critical defects closed, approved sharing/security/incident policy, accountable operational-owner sign-off | NOT RECORDED |

## Limits and deferred features

The partial source inventory is not a regional denominator; no report means unknown need. Provisional source references were not independently corroborated. No operational coordinates, observed times or defensible humanitarian ranking were invented. Single-host SQLite has no tested HA or multi-host operation, and no throughput promise. Some technical interface text remains English. A signed local backup does not provide encrypted off-site recovery.

Bayesian calibration, Monte Carlo, SMS, advanced spatial silent-zone inference, choropleths, PostgreSQL/PostGIS, multi-host HA and public analytics remain deferred. Migration is required before multi-host/shared-network DB operation or when measured sustained contention/HA/spatial requirements justify it. These features do not block the bounded pilot unless owners explicitly require them.

**FINAL STATE: EXTERNAL-BLOCKED — published and tested pilot source/image; production hosting and commissioning remain pending.**
