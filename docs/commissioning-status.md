# Dawei Flood Intelligence — actual commissioning checkpoint

Updated October 4, 2026 UTC. Actual temporary deployment is tested through HTTPS, persistence, independent signed recovery, dedicated Sheets projection and Telegram transport. **TEMPORARY FREE — NOT SUSTAINABLE.** FIELD-ACCEPTED and OPERATIONAL are not recorded. [Deployment](autonomous-deployment.md), [provider evidence](provider-commissioning.md) and [hosting decision](free-hosting-decision.md) supersede [historical evidence](archive/commissioning-status-before-live.md).

| Area | Actual evidence and practical limit |
|---|---|
| Release | Approved `v0.1.0-pilot`, commit `c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc`, immutable image, schema 2. Infrastructure commit `ff96112de64b38e1178aec0d034c6f8e90835937`; configuration `trial-keyless-provider-workers-1`. |
| Host | TESTED trial VM, strict IAP, persistent local disk, non-root read-only services and guard-controlled provider recovery. No public VM IPv4/NAT/load balancer. |
| Reachability | TESTED DuckDNS IPv6 HTTPS and separate provider IPv4 HTTPS. DuckDNS itself remains IPv6-only; intended pilot networks/alternate entry point need acceptance. |
| Security | TESTED 21 actual checks per public route, trusted modern TLS, origin/Host/CSRF/session/cookie/proxy/cache/private-path controls. Actual metadata isolation survived reboot. Ninety-eight regressions and six exact-head CI checks passed. No unlimited penetration-testing claim. |
| Persistence | TESTED app restart, removal/recreation, Compose restart and actual reboot; another provider-enabled reboot passed automatic recovery, canary, protected rows, integrity/FK/schema and source hashes. |
| Recovery | TESTED fresh signed operational copy, age-encrypted private GCS upload/literal download, separate owner-side isolated signed restore; protected rows/source/account/provider checkpoints passed; isolated sessions revoked. Warm decrypt/restore 0.547 seconds excludes rebuilding/retrieval/switching. |
| Scheduled backup | TESTED real encrypted upload/download service; bounded hourly timer active, capacity guard, no automatic remote-history deletion. Continuing independent transport NOT TESTABLE without owner destination grant. |
| Monitoring | TESTED minute host health/database/disk/worker/backup/trusted origin TLS expiry and [independent external probe](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37187819320). External workflow active/enable flag set; successful manual runs and [actual scheduled external probe](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37190263375) recorded. Actual scheduled DNS/IPv4 HTTPS execution is TESTED. Owner alert receipt remains unverified; no schedule timing guarantee. |
| Capacity | TESTED bounded existing-source isolated import, active Telegram polling, idle Sheets, encrypted upload/download and 40 concurrent authenticated reads. p95 0.300 seconds; ten samples retained 345.7 MiB available RAM / 24.25 GiB disk. Sustained intake and field-scale capacity are not certified. |
| Telegram | TESTED actual authorized private `/start`, real reply and persistent recipient/poll checkpoint through restart/recreation/reboot. Active. Full guided report/preview/confirmation/correction and real denial/duplicate/failure exercises remain for controlled operator acceptance; regressions are not a field drill. |
| Sheets | TESTED narrow keyless access to dedicated restricted projection; real isolated write/readback/retry/duplicate/correction/removal/recreation; final headers only. Active. Original source unchanged; organization key policy preserved. |
| Data/geography | Raw source, missingness and quarantine retained; no operational claim promoted, coordinate/alias invented or field truth approved. |
| Methodology | HUMAN ACTION REQUIRED — accept descriptive-only scope or approve a versioned model; no unapproved humanitarian ranking accepted. |
| Governance/language | HUMAN ACTION REQUIRED — custody, retention, sharing/roles, on-call/escalation and Burmese field review. Prepared guidance is not approval. |
| Pilot/field | HUMAN ACTION REQUIRED — accountable participants, realistic networks/workload and controlled field acceptance. No field metrics or approval fabricated. |

## Minimum owner actions

1. Narrowly authorize an independent unattended private backup destination outside trial closure; record recovery custody, retention and on-call/escalation responsibilities. Existing owner-side ciphertext is a real independent checkpoint, not guaranteed continuing transport. No GitHub backup or inferred Drive grant is permitted.
2. Nominate the controlled pilot and complete descriptive-only or methodology, governance, geography/claim-review where needed, Burmese language, network and field acceptance. Include the complete guided Telegram workflow and realistic sustained workload in that exercise.

SDK, DuckDNS, administrator, Telegram token/sender and private Sheets authorization are completed. Do not request them again. No P0/P1 defect was found in completed bounded checks; unperformed intake, owner alert delivery and field checks remain acceptance gates. SQLite stays single-host; a migration needs measured evidence. Corruption means stop writers, preserve evidence and escalate; never auto-overwrite or clear a latch.

Private provider IDs, credentials, operational data, recovery payloads and detailed receipts remain ignored and restricted. Continue actual health/evidence maintenance and inspect new owner authorities; execute authorized real independent transport and controlled pilot checks when available. No paid continuation is permitted.
