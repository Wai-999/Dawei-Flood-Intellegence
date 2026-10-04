# Autonomous deployment — live trial checkpoint

Updated October 3, 2026, America/Los_Angeles. **DEPLOYED → HTTPS-VERIFIED → PERSISTENCE-VERIFIED → RECOVERY-VERIFIED for the actual temporary trial checkpoint.** Monitoring has a real independent external test; provider commissioning and accountable pilot/field acceptance remain open. **TEMPORARY FREE — NOT SUSTAINABLE.** This is not OPERATIONAL or an accepted humanitarian field deployment.

The owner authorized the existing non-billable Google Free Trial allowance and prohibited purchasing, upgrades and paid continuation. SDK and DuckDNS consent were completed personally. The earlier sustainable-only answer, missing-host diagnosis and expired Railway staging are historical; [the previous checkpoint](archive/autonomous-deployment-before-live.md) is retained for chronology. Oracle remains excluded.

## Actual architecture and reproducibility

The exact approved application remains `v0.1.0-pilot`, commit `c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc`, schema 2 and the immutable AMD64 image in [release.json](../infra/release.json). Infrastructure source is separate: [PR #8](https://github.com/Wai-999/Dawei-Flood-Intellegence/pull/8) fixes unknown-Host rejection; [PR #9](https://github.com/Wai-999/Dawei-Flood-Intellegence/pull/9), head `d1fb2b2b40219dc9c60732330c90e5e33e310f30`, adds tested ingress and scheduled encrypted uploads. All six PR/push checks passed before merge. No approved application code or image was replaced.

- IPv6: Internet → reserved DuckDNS AAAA → Caddy trusted TLS → Compose/Gunicorn → SQLite on the persistent local standard disk.
- IPv4: provider HTTPS hostname → pinned Caddy Cloud Run ingress → Direct VPC private HTTPS → the same VM/app/database. The VM has no public IPv4, NAT, paid connector or load balancer. The provider hostname is a separate entry point; DuckDNS itself remains IPv6-only.
- Local signed hourly worker → age encryption → private GCS using workload identity. A real encrypted copy is also held outside the trial account on the owner computer; its recovery identity remains owner-side.

Private receipts record actual host/source/configuration/image hashes and timestamps. Provider identities, credentials, source files, databases and recovery payloads are excluded from the public repository. [Ingress and timer implementation](ipv4-ingress-and-backup-timer.md) records the architecture deviation and controls.

## Actual verification

- Stable DNS verified independently; obsolete A cleared and AAAA matched the reserved address. Target trusted certificate, HTTP redirect, HSTS, liveness/readiness, anonymous API denial and unknown Host rejection passed externally.
- Twenty real authentication/security checks passed on each public route: named owner login, Secure/HttpOnly/SameSite=Strict/host-only cookies, forwarded-header spoof rejection, CSRF, foreign origins, logout/session invalidation and private-path rejection. Both routes rejected TLS 1.0/1.1 and accepted trusted TLS 1.2. The IPv4 authentication requests explicitly used IPv4 sockets.
- Persistent canary writes survived app restart, app container removal/recreation, Compose restart and an actual host reboot with changed boot ID. Real database integrity/FK/schema, source hashes and the named owner account survived reboot.
- Actual signed operational copy → age encryption → private GCS upload → download/hash verification → separate owner-side decryption → approved-image network-isolated restore passed. The refreshed restore included the owner account, revoked sessions and all retained source hashes. Twenty-four operational tables matched original rows exactly; the reviewed differences were account/authentication/audit/worker bookkeeping. Warm owner-side decrypt plus isolated restore took 1.834 seconds; this excludes retrieval, provisioning and traffic switching and is not an operational RTO promise.
- The actual systemd encrypted-upload service passed its round trip in 7.964 seconds; the hourly timer is active. No remote history is automatically deleted. GCS within the trial account is not independent account-loss protection. Continuous independent transport is not commissioned.
- Forty authenticated/dashboard reads at concurrency two succeeded: median 0.152 seconds, p95 0.244 seconds, maximum 0.264 seconds. Eight host samples retained at least 468.9 MiB available RAM and 24.65 GiB free disk; SQLite integrity passed. This bounded read test does not certify field imports or Telegram/Sheets load.
- Eighty-eight local regressions passed. GitHub also passed dependency/static/privacy checks, container smokes, trusted-TLS/Host/origin rehearsals and both Linux deployment rehearsals.

## Remaining proven boundaries

Telegram token/sender mapping and Google Sheets credential/dedicated projection authorization were absent from the available authorized configuration; both workers remain disabled. Broader Drive authorization was not inferred from SDK consent. An independent scheduled cloud backup destination needs owner authorization and quota verification. [Current commissioning report](commissioning-status.md) distinguishes these Category-D account/acceptance gates from completed infrastructure work.

Trial guard evidence must remain fresh: actual credit/account observations and independently restored recovery within twelve hours, a conservative reserve and early cutoff. Invalid/stale evidence stops containers and latches writes; it never clears itself. No billing upgrade, trial renewal, public operational backup or corrupted-data overwrite is permitted.
