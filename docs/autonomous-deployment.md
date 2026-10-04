# Autonomous deployment — live provider checkpoint

Updated October 4, 2026 UTC. **DEPLOYED → HTTPS-VERIFIED → PERSISTENCE-VERIFIED → RECOVERY-VERIFIED** for the actual temporary trial checkpoint. Authorized Sheets projection and Telegram transport are tested and active. Guided Telegram intake passed an owner-approved isolated technical exercise. Unattended independent transport, owner alert delivery and accountable pilot/field acceptance remain open. **TEMPORARY FREE — NOT SUSTAINABLE.** This is not OPERATIONAL or an accepted humanitarian deployment.

The owner authorized the existing non-billable Google trial and prohibited purchases, upgrades and paid continuation. SDK/DuckDNS consent and the named administrator were personally authorized. Earlier missing-host evidence is [historical](archive/autonomous-deployment-before-live.md); Oracle remains excluded and the expired Railway trial was not renewed.

## Actual architecture and pinned source

Approved application: `v0.1.0-pilot`, commit `c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc`, schema 2 and immutable AMD64 image in [release.json](../infra/release.json). Infrastructure commit `ff647ecb51863cce77616bbb724d79457bdeda16` and configuration `trial-isolated-operator-pilot-1` retain that image. Private receipts record actual source/image/configuration hashes and rollout times. No operational data, provider identities or secrets enter public source.

- IPv6: Internet → reserved DuckDNS AAAA → Caddy trusted TLS → Compose/Gunicorn → SQLite on local persistent standard disk.
- IPv4: separate provider HTTPS hostname → pinned Caddy Cloud Run ingress → Direct VPC private HTTPS → the same VM/database. No public VM IPv4, NAT, paid connector or load balancer. DuckDNS itself remains IPv6-only.
- Local signed hourly backup → age encryption → private GCS using workload identity. Literal downloaded ciphertext also passed a separate owner-side isolated restore outside the trial account. The decryption identity remains owner-side.
- Authorized Telegram and dedicated restricted Sheets workers use read-only infrastructure IPv6 adapters. Sheets uses narrow keyless impersonation after actual metadata isolation; Telegram secrets are inaccessible to the app.

[Ingress/timer implementation](ipv4-ingress-and-backup-timer.md) and [provider commissioning](provider-commissioning.md) record tested architecture deviations, real provider evidence and practical limits.

## Actual verification

Stable DNS, trusted TLS, redirect, HSTS, readiness/liveness, anonymous rejection and unknown Host rejection passed externally. Twenty-one real authentication/security checks passed per public route after worker rollout: named owner login, secure host-only cookies, authenticated no-store responses, forwarded spoof/CSRF/origin rejection, logout/session revocation, private-path rejection and modern TLS. IPv4 checks used IPv4 sockets. Direct DuckDNS and independent GitHub probes passed after reboot.

Persistent canaries survived app restart, container removal/recreation, Compose restart and actual host reboot. A second actual reboot after provider activation passed automatic guarded recovery, protected operational/owner rows, source hashes, SQLite integrity/FK/schema and actual IPv4/IPv6 metadata isolation. The host monitor currently reports database/disk/containers healthy, backups fresh, Telegram FRESH and Sheets IDLE; origin certificate chain/hostname/expiry are verified with a seven-day warning.

Signed operational copy → age encryption → private GCS upload → literal download/hash → separate owner-side decrypt → approved-image network-isolated signed restore passed. The initial checkpoint reconciled twenty-four operational tables to the original source. The fresh provider checkpoint preserved owner/provider state and seven protected operational/owner row sets; isolated sessions were revoked after signed verification. Warm decrypt/restore took 0.547 seconds, excluding retrieval/rebuilding/switching. This is not an RTO promise. Hourly encrypted uploads are active; same-account GCS alone cannot protect against account loss. No remote history is automatically deleted.

The refreshed bounded source-import/provider/backup/read workload retained at least 345.7 MiB available RAM and 24.25 GiB free disk during ten samples. Forty authenticated IPv4 reads, concurrency two, passed with p95 0.300 seconds. The current-source import was isolated from operational data; protected rows and SQLite checks passed. Field scale and sustained input remain unaccepted.

The current implementation has one hundred four passing regressions, and all six exact-head checks passed before the keyless/IPv6 and isolated operator-adapter merges, including dependency/static/privacy checks, container smokes, trusted-TLS/Host/origin and both Linux deployment rehearsals. Independent external monitoring is enabled; manual probes and the [actual scheduled external probe](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37190263375) passed. The scheduled event genuinely ran on main, verifying the expected DuckDNS AAAA and trusted IPv4 ingress/application. Owner alert receipt remains unverified; one successful run does not guarantee future timing or delivery.

## Remaining proven boundaries

Telegram and Sheets authorizations are complete. The owner approved descriptive-only technical testing with TFUCC, and the [actual guided Telegram exercise](controlled-operator-pilot.md) passed. The existing Google Drive destination was authorized and its backup client prepared; private credential replacement and the actual `drive.file` grant remain pending. No Drive backup, quota check or restore is claimed. Custody/retention/on-call and accountable humanitarian/pilot/field acceptance remain human gates; SDK consent does not grant Drive access. [Commissioning status](commissioning-status.md) records them.

Actual credit/account and independently restored recovery must remain fresh within twelve hours. Stale/invalid evidence, reserve/cutoff failure or corruption stops containers and preserves a write latch. No automatic latch clearing, data overwrite, billing upgrade or trial renewal is permitted.

The optional isolated Telegram adapter passed actual worker recreation, draft/session-deadline persistence, correction/duplicate handling and operational-row isolation after the earlier host-reboot checkpoint. Actual public readiness/security probing passed at 10:40 UTC and host health at 11:00 UTC. These fresh probes do not certify sustained service or field acceptance.

A new actual encrypted GCS upload/literal download and separate owner-side signed isolated restore completed at 10:52 UTC. Signature, source hashes, schema, integrity/FK, protected operational/owner row parity and isolated-session invalidation passed. The signed archive and earlier checkpoints were preserved. No new recovery duration was measured. A genuinely fresh owner billing observation at 10:59 UTC and this actual restore were installed without changing account scope, cutoff, reserve or latches. These observations remain time-limited; they do not prove continuing independent transport or unused aggregate allowance.
