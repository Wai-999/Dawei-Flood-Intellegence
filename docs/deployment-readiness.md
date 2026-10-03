# Deployment readiness — 2026-10-02

Scope: the existing local MVP hardened into a single-host release candidate. Classification means implementation evidence, not a claim of a running production service. Production is **EXTERNAL-BLOCKED** on host/domain, private credentials, backup destination, operator access and commissioning acceptance. No live URL, hosted HTTPS or live provider success is claimed.

| Component / priority | Status | Evidence | Risk / required action | Blocks production? |
|---|---|---|---|---|
| API / P0 | WORKING | HTTP/WSGI tests; production container health smoke; strict framing/body/host checks | Pilot capacity test and deployed endpoint smoke | External launch acceptance |
| Auth / P0 | WORKING | Individual PBKDF2 users, hashed 8-hour sessions, expiry/revocation, persistent HTTP429 throttle, CSRF/origin/Secure-cookie tests | Provision named accounts; privileged MFA/access gateway and recovery policy | External configuration |
| Authorization / P0 | WORKING | Owner reads/updates/feedback; server-enforced review/admin/export permissions; escalation rejected | Review actual operator role assignments | External configuration |
| Database / P0 | WORKING | SQLite schema 2; v1 migration sentinel test; immutable raw/versions/audit; transaction/replay/concurrency tests | One host/local persistent volume; migrate before multi-instance or sustained contention | External volume configuration |
| Intake/review/history / P1 | WORKING | End-to-end raw→parse→validate→geography→conflict→review→version tests | Imported ambiguous claims still require accountable human correction | Blocks using imported impact claims as verified facts |
| Telegram / P1 | EXTERNAL-BLOCKED | Guided/structured commands, private allowlist, checkpoint/send-failure retry and feedback mocked | Private token and active sender mapping; real round-trip commissioning | Yes for Telegram operation |
| Sheets / P1 | EXTERNAL-BLOCKED | Transactional outbox, header-safe RAW projection, correction removal and retry mocked | Service account/API/destination access; protect owned tab and verify real write | Yes for Sheets operation |
| Coordination / P2 | WORKING | Pledge→dispatch→delivery→receipt tests, unit/period checks, ETA/expiry/excess warnings and private feedback | Owner-approved requirements/units/standards; no automatic allocation | External operational acceptance |
| Freshness/priority / P2 | PARTIAL | Field clocks, approved decay only, separate severity/confidence/completeness, sensitivity ordering and immutable snapshots | No source-approved model supplied; supply policy/reference and validated data | Blocks numeric operational rankings until approved |
| GIS / P2 | PARTIAL | Browser synthetic fixture: clustering, detail, layers/zoom; unknown coordinates excluded; keyboard controls | Operational source has no approved coordinates. Boundaries/hazard layers absent | Blocks geographic operational analysis, not intake |
| Silent zones/coverage / P2 | PARTIAL | Unreported worklist entries and investigation reasons; denominator disclosed unknown | Complete registry, exposure/access/neighbor evidence required for spatial inference | Blocks regional coverage/inferred silent-zone severity |
| Dashboard / P2/P5 | WORKING | Browser overview, statistics, map/detail, English/Burmese controls and 390px mobile map | Technical prose partly English; field terminology and user acceptance required | External pilot acceptance |
| Exports/privacy / P0 | WORKING | Role-safe filtered CSV/JSON/XLSX; formula protection; metadata/version/coverage tests | Public release remains disabled; owner must approve any further de-identification | External sharing policy |
| Backup / P3 | WORKING | Signed real-data/source restore, counts/integrity; wrong-key/tampering tests; hourly worker/retention/lock | Mount private key, encrypted off-site storage and alerts; hosted RPO/RTO drill | External configuration |
| Monitoring / P3 | PARTIAL | Public safe live/ready and private operator health, queues/provider state/backup failures; structured logs | Configure off-host probes, disk/worker alerts and on-call destination | External configuration |
| CI/CD / P3 | WORKING | Tests, ES-module checks, Bandit, dependency audit, privacy scan, Docker smoke/Caddy validation; [GitHub run passed](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37083989391) | Require current PR checks green before merge; release builds image; host deploy explicit | Remote CI and external deployment gate |
| Secrets / P0 | WORKING | Source-only allowlist, Git/Docker exclusions, recognizable-token scan; private file exclusion container test | Operator key custody/rotation and volume encryption | External configuration |
| Runtime/proxy / P3 | WORKING | Pinned non-root image, Gunicorn threads/timeouts, private port, trusted proxy/header checks, Caddy config validation | Real DNS/certificate/HTTPS test has not occurred | External host/domain |
| Advanced statistics / P4 | MISSING (deferred) | Descriptive sample size/missingness only; no fabricated Bayesian/Monte Carlo output | Need sampling/calibration/scenario distributions and domain validation | No; unsupported outputs remain unavailable |

## Release acceptance

53 automated tests are in the repository; local results and limitations are in [acceptance-results.md](acceptance-results.md). GitHub PR validation completed successfully for implementation commit `cf07f8938d8346945c51eacc94a9463276cd3aa1`; inspect current PR checks after later changes. No production deployment is approved by a locally green test alone. Build contains source/static assets only, never operational data. The original Sheet remained unchanged.

All P0–P3 repository-controlled paths have implementation and local checks. Launch tasks requiring external account/data-owner authority are enumerated below. Advanced features remain explicitly deferred, rather than implemented with unsupported assumptions.

1. Select and authorize a persistent server account, domain and TLS; use [deployment](deployment.md).
2. Provision individual production identities, trusted proxy/origin and approved operator roles; decide privileged MFA/access gateway.
3. Mount private bot/service-account/signing files and commission approved test destinations with real round trips.
4. Configure encrypted persistent storage, separate encrypted off-site backup and actionable monitoring; run a hosted restore drill.
5. Review imported claims and geography, supply approved models/registry when available, approve retention/export policy and complete field terminology/pilot acceptance.

The chosen architecture supports a bounded single-host pilot. It has no tested high-availability failover, public unauthenticated analytics, load capacity promise, automatic humanitarian allocation or region-wide risk inference.
