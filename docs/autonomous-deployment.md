# Autonomous deployment evidence — 2026-10-03

## Current state

**Production: INFRASTRUCTURE-SELECTED, conditional on account and cost verification.** The approved pilot remains RELEASED. The latest instruction explicitly excludes Oracle; the current selected candidate is Google Free Tier with persistent block storage and external IPv6 only. Authenticated Google Cloud browser access was tested at the end-to-end mandate recheck, but no accessible billing account was listed and all three visible projects had billing disabled. No production host is provisioned; private gcloud/ADC access remains absent. See [current non-Oracle free-hosting decision](free-hosting-decision.md) for provider evidence, strict cost gates, prepared automation and the precise owner billing-authority boundary. Neither unrestricted $0 traffic nor production HTTPS is verified.

**Separate synthetic staging: DEPLOYED → HTTPS-VERIFIED → PERSISTENCE-VERIFIED → RECOVERY-VERIFIED within staging scope.** This does not advance production commissioning, provider commissioning, pilot readiness, field acceptance or operational status. The temporary Railway VM has an explicit **2026-10-03 07:48:50 UTC** expiry. Staging checks are historical once that window closes.

The implementation keeps the original single-host architecture: Internet → DuckDNS → Caddy → Compose → Gunicorn → host-mounted SQLite, with separate backup and disabled integration workers. Only the temporary staging ingress deviates: Railway TLS edge → Caddy :8080 → app. External tests confirmed that this preserves authentication, trusted origin/proxy handling, secure cookies and Host rejection.

## Reproducible release

- Approved tag: [v0.1.0-pilot](https://github.com/Wai-999/Dawei-Flood-Intellegence/releases/tag/v0.1.0-pilot).
- Exact application commit: `c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc`; SQLite schema 2.
- AMD64 image: `ghcr.io/wai-999/dawei-flood-intellegence@sha256:c6d38231fc37097dfef73643114de4f028369f886401b49ff130d4f31cdfff98`.
- Caddy digest: `sha256:881bbc60f9986d5ab8e7cfd6cf7e4ef3c9c0439fef2429d035d065577882f028`.
- Infrastructure configuration: `pilot-infrastructure-1`; new source/configuration commit is separate from the unchanged approved application tag. Host receipts record source/image/configuration hashes and deployment time.
- Staging deployment receipt timestamp: `2026-10-03T07:17:21.762027+00:00`.

## Historical autonomous options attempted

The table records the earlier investigation. Its Oracle recommendation and owner handoff are superseded by the latest non-Oracle decision; do not retry that provider.

| Detected blocker | Exactly one classification | Investigation / action / result |
|---|---|---|
| Missing host information | C — Automatically discoverable | Checked repository/deployment artifacts, environment variable names, SSH/cloud/rclone/tunnel configuration paths and GitHub Actions secrets/variables. No production credentials, hosts, repository secrets or variables were found. OCI browser reached a sign-in form with no authorized tenancy. Available hosting plugins were not connected. |
| No persistent cloud account access after discovery | D — User-action-required | Current provider documentation compared Oracle, Google, Fly, Railway, Render, Koyeb, Northflank, Codespaces, Actions, Tunnel, AWS, Azure, DigitalOcean and Hetzner. Eligible persistent Oracle resources offer the safest continuing free design; signup/identity/card/terms/access cannot be performed on the owner's behalf. |
| Original VM path unavailable for immediate testing | B — Architecture-solvable | Provisioned one accountless Railway Linux VM through the documented SSH route. Used trusted provider TLS and a private host-mounted synthetic SQLite database. Actual deployment, security, persistence and cloud-to-owner-host recovery tests passed. Temporary lifetime prevents production use. |
| Compose temporary mount syntax | A — Agent-solvable | Corrected a YAML list that parsed the mount comma as another list item. Actual Compose startup and rehearsal passed. |
| Worker/app IP collision | A — Agent-solvable | Assigned separate fixed addresses to proxy, app and each worker; isolated maintenance one-offs have no network. Actual app recreation passed. |
| Backup one-shot versus scheduled worker lock | A — Agent-solvable | Preserved the existing exclusivity lock. Staging consumes the scheduled backup; isolated rehearsal stops its own worker before a one-shot operation. Signed backup verified. |
| Temporary VM had no system python3 in sudo path | A — Agent-solvable | Installed trusted Ubuntu python3 package for the Linux rehearsal. Production bootstrap correctly refuses sandbox systemd absence; staging is an explicitly separate runner. |
| Need encrypted off-site evidence | B — Architecture-solvable | Generated the age identity on the owner computer, transferred only its public recipient to the cloud VM, encrypted a signed synthetic bundle before transfer, then restored on the separate owner computer using the escrowed signing key. Actual integrity/source/schema/audit checks passed. |
| Persistent private backup destination authorization | D — User-action-required | Oracle private Object Storage can use the same owner cloud authorization; B2/R2 free allowances also researched. No operational upload occurred. Production bucket access, key custody, retention, on-call destination and real recovery remain uncommissioned. |
| DuckDNS update authorization | D — User-action-required | Existing hostname resolves to IPv4; HTTP/HTTPS readiness timed out. No token was found in available configuration. A private-token update helper is prepared. Host and storage work proceeds first; no token was exposed or DNS changed. |
| Telegram and Sheets credentials | D — User-action-required | Both workers remain disabled. They do not prevent Phase A host/app/SQLite/TLS/backup deployment. Owner authorization will enable and commission each separately. |
| Geography, governance, claims and field acceptance | D — User-action-required | No coordinate, alias, severity/freshness, quarantined-claim or field-truth approval was invented. Existing human ownership gates remain unchanged. |

The provider rationale, ongoing costs, account requirements, storage safety and reliability limitations are documented in [free infrastructure research](free-infrastructure-research.md). No free-tier restrictions were evaded and no paid service was ordered.

## Test evidence

- **59 local regression tests passed**: 53 approved application tests plus six infrastructure tests for immutable release pins, private idempotent configuration, unsafe-root/input/symlink rejection, read-only corruption classification, and secret-file permissions.
- **Actual Linux Docker/Compose rehearsal passed** on Ubuntu 26.04.1 AMD64: prepare twice, readiness, separate SQLite write → app restart → read and write → app container removal/recreation → read; encrypted upload/download/decryption and isolated signed restore; ciphertext tamper rejection; quota refusal; corruption STOP_WRITES latch, writer shutdown and evidence preservation. The rehearsal transport uses a private local rclone fixture, explicitly distinguished from off-site commissioning.
- **Actual off-site synthetic drill passed**: cloud signed bundle → age encryption on cloud host → private ciphertext copy to separate owner computer → decryption → signature/source-hash verification → isolated SQLite restore → integrity/FK/schema/assessment-version-source-audit parity checks. No operational disaster data left the existing trusted local workspace.
- **External HTTPS checks passed** against the temporary assigned Railway hostname at 07:15 UTC; authentication/cookie and spoofed-forward-header checks passed at `2026-10-03T07:33:54.022875+00:00`. DNS, TCP 443, certificate hostname/trust/expiry, HTTP→HTTPS redirect, HSTS, healthy readiness/liveness JSON, anonymous administrator API rejection, invalid Host rejection, Secure/HttpOnly/SameSite=Strict cookies and authenticated session read were checked. Provider certificate expiry observed: 2026-12-26; that date does not extend the VM lifetime.
- **Native ARM64 Linux container build and both approved smoke scripts passed** on the local ARM Docker runtime, using an archive of exact approved commit `c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc`. Resulting local image ID: `sha256:11cd0fe1ea819eec1cbb884579c8d79a220ce06ca1c874d87274ba41437b67ce`. This validates application/image compatibility, not an Oracle host or ARM registry publication.
- **GitHub validation passed** on infrastructure commit `fc1bd58d1a218d414f1ad415340ccc9279314a26`: [PR run 37107316462](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37107316462) and [push run 37107311791](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37107311791), including security/tests, both container smoke scripts and the Linux deployment rehearsal.
- **Not tested/commissioned:** persistent Oracle host installation/firewall, Oracle ARM host deployment, host reboot, target DuckDNS ACME/HTTPS, production encrypted object restore, actual Telegram/Google end-to-end operation, operational RPO/RTO and human field acceptance.

Detailed logs, private credentials, identity/signing escrow, SQLite fixtures and decrypted recovery content remain only under ignored private `outputs/autonomous-infrastructure/`. None is committed or attached to the public release. Public source carries summary outcomes, not payloads or secrets.

## Current owner handoff and next execution

**Category D: authorize the selected Google Free Tier project privately at [Google Cloud Console](https://console.cloud.google.com/).** Account creation, legal acceptance, MFA and payment verification belong to the owner. The agent will not upgrade billing or purchase resources. Sustainable Free Tier use requires an active non-trial billing account and verified aggregate allowances; a new trial alone is temporary and can delete resources. Provide private authorized access and project ID, never passwords, payment details, MFA codes or public keys/tokens in issues or logs.

After authorization, inventory the actual whole account, verify current free eligibility/usage and excluded-destination/egress controls, then provision only eligible resources and bootstrap the unchanged pinned application. Request DuckDNS update authorization only after host work is ready, if still absent. Verify real external HTTPS, restart/recreation/reboot persistence and encrypted private GCS transport plus independent isolated restore before advancing production. IPv4-only field users require a separately verified access solution. Telegram, Sheets and accountable operational acceptance remain later gates.

The scheduled follow-up excludes Oracle and waits quietly while the owner account/billing boundary is unchanged. Detailed implementation, test scope, limitations and fallback choices are in [free-hosting decision](free-hosting-decision.md). No local or historical trial test is a production PASS.
