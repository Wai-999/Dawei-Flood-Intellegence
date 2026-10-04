# Dawei Flood Intelligence — actual commissioning checkpoint

Updated October 3, 2026, America/Los_Angeles. **Actual temporary deployment is tested through HTTPS, persistent storage and independent signed recovery.** It is **TEMPORARY FREE — NOT SUSTAINABLE** and is not FIELD-ACCEPTED or OPERATIONAL. The approved application release/image remains unchanged. [Deployment evidence](autonomous-deployment.md) and [hosting decision](free-hosting-decision.md) are the current sources; [older commissioning evidence](archive/commissioning-status-before-live.md) is retained as history.

| Area | Current evidence and practical limit |
|---|---|
| Release | Approved `v0.1.0-pilot`, commit `c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc`, immutable AMD64 image, schema 2. |
| Host | TESTED actual Google trial VM, private IAP, local persistent standard disk, strict secret permissions, non-root read-only app and disabled integrations. No public VM IPv4/NAT/load balancer. |
| Reachability | TESTED DuckDNS trusted HTTPS over IPv6 and separate provider HTTPS ingress over IPv4. DuckDNS itself remains IPv6-only. Pilot networks and the alternate entry point need human acceptance. |
| Security | TESTED actual named owner login and twenty-one security checks on each public route; trusted modern TLS, origin/Host/CSRF/session/cookie/proxy, authenticated `no-store` responses and private-file rejection. Repository scans and 89 regressions passed. This is not an unlimited penetration-testing claim. |
| Persistence | TESTED app restart, container removal/recreation, Compose restart and actual changed-boot-ID reboot; actual integrity/FK/schema/account/source checks passed. |
| Recovery | TESTED real signed source → client encryption → private GCS → download/hash → separate owner-side isolated restore. Owner account/source files recovered; restored sessions revoked; operational rows reconciled. Warm decrypt/restore timing 1.834 seconds excludes host rebuilding/retrieval/switching. |
| Scheduled backup | TESTED actual systemd encrypted-upload service; hourly timer active, capacity guard, bounded retries, no automatic remote deletion. Same-account GCS does not alone protect against account loss. Independent continuously scheduled destination/transport NOT TESTABLE without owner grant. |
| Monitoring | TESTED bounded minute host health/disk/database/worker/backup checks and independent GitHub DNS/IPv4 HTTPS/TLS/readiness probe; [actual external run](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37174434925) passed. The live origin TLS monitor verifies the chain, hostname and certificate expiry with a seven-day warning. Owner on-call receipt/escalation policy remains unaccepted. |
| Capacity | TESTED forty bounded authenticated/dashboard reads, concurrency two, all successful; p95 0.244 seconds. At least 468.9 MiB available RAM and 24.65 GiB free disk during eight samples. Field import/provider workload capacity NOT TESTABLE before those workflows are authorized. |
| Telegram | HUMAN ACTION REQUIRED — private existing bot authorization and approved sender-to-account mapping. Disabled; real intake/correction/duplicate/failure tests pending. |
| Sheets | HUMAN ACTION REQUIRED — least-privilege credential and a dedicated authorized projection destination. Disabled. The original source spreadsheet remains unchanged. |
| Data and geography | Raw source/missingness/quarantine retained; no claim promoted, coordinate/alias invented or field truth approved. Missing geography remains missing. |
| Methodology | HUMAN ACTION REQUIRED — accept descriptive-only scope or approve a versioned model. Unapproved numeric humanitarian ranking is not operationally accepted. |
| Governance and language | Prepared operations/incident/recovery guidance; custody, retention, sharing/roles/on-call approval and Burmese field-language review remain human responsibilities. |
| Pilot/field acceptance | HUMAN ACTION REQUIRED — accountable participants and controlled field acceptance. No field metrics or humanitarian approval fabricated. |

## Remaining owner actions

1. Authorize a private independent scheduled backup destination and acknowledge recovery-key custody, retention and on-call/escalation responsibilities. The existing encrypted owner-side archive is an actual recovery checkpoint, not guaranteed unattended independent transport.
2. Supply Telegram and dedicated Sheets authorization privately, or explicitly exclude either integration from the first pilot. Tokens, private keys, passwords and recovery codes must never enter chat, GitHub or public logs.
3. Accept the prepared technical evidence and trial/alternate-host limits; nominate the controlled pilot and complete governance, descriptive-only or approved-methodology, geography/claim-review and Burmese/field acceptance. Infrastructure automation cannot sign these approvals.

No P0/P1 defect was found in the completed bounded checks. Missing authorizations and unperformed field/capacity/alert-delivery checks remain explicit acceptance gates, not successes. SQLite remains single-host; a migration requires measured evidence, not an assumed need. Corruption means stop writers, preserve evidence and escalate; never auto-overwrite or clear a latch.

The source history contains only safe code/configuration/summary evidence. Private provider IDs, credentials, operational data, ciphertext/decrypted recovery and detailed receipts remain ignored and locally restricted. The next automatic action is to verify any new private authorization, run the real corresponding round trips, then continue the controlled acceptance workflow. No billing upgrade or paid continuation is permitted.
