# Acceptance evidence — 2026-10-02 (historical)

This document preserves the October 2 source checkpoint. [Current commissioning](commissioning-status.md) and [provider evidence](provider-commissioning.md) supersede its missing-host/provider statements; historical measurements below are not current deployment claims.

## Repository and local acceptance

- **53 automated tests** cover parser/validation/normalization, unknown vs zero, raw retention before report parsing and geography failure, immutable audit/history, concurrent replay, v1→v2 migration, review/correction, ownership and privilege checks, session expiry/revocation, HTTP429 persistence, origin/CSRF, secure cookies, body/host/proxy framing, separate freshness/severity/confidence, sensitivity snapshots, resource units/expiry/receipts, safe exports, source quarantine, provider retry and Sheets correction removal.
- Pipeline tests demonstrate private Telegram intake → retained raw → parse/validation/geography/conflicts → human review → canonical version → approved synthetic analytics → reviewed coordinates → pledge/dispatch/delivery/receipt → private feedback → mocked Sheets → safe export → correction reopening/removal. Fixtures are synthetic and do not alter the operational source.
- Python compilation and **all dashboard scripts checked explicitly as ES modules**. Browser inspection found and repaired a statistics-view syntax error missed by the old automatic module detection check.
- Browser: real-source overview preserves zero verified records and unknown impact totals; English/Burmese navigation and statistics render. Separate synthetic map shows three approved points, a two-point cluster, detail/freshness explanation and one unplotted unknown coordinate. Responsive map inspected at 390px; viewport restored. This is not field-user acceptance or a full Windows/macOS/mobile device matrix.
- Dependency audit: no known vulnerabilities in pinned production dependencies at audit time. Requests was upgraded to 2.33.0 after an earlier audit finding. Bandit reports zero issues at all severities. These scans do not replace an independent penetration test.
- Docker build, non-root UID10001/read-only runtime, readiness, private-file exclusion and persistent-volume restart smoke passed. Compose configuration and Caddy configuration validation passed. No hosted HTTPS was tested.
- Signed real local database/source bundle restored into a separate directory: SQLite integrity `ok`, foreign keys valid, 79 locations, 63 assessments, 63 submissions, 63 assessment versions, 66 audit events and zero assistance events. All three retained source files and HMAC signature verified; local extraction/validation took 0.006 seconds. Later audit events can increase the live count. The measurement is not a hosted RTO benchmark.
- Secret/privacy scan is required on all Git-tracked artifacts before publication and in CI. Source-only Git publication excludes snapshots, private Sheet identifier, DBs, credentials, backups and exports. GitHub workflow results are visible on the current pull request; merge requires green checks.

## Earlier source/workbook acceptance retained

The original Sheet was exported read-only and remains unchanged. The earlier processed workbook has 15 tabs, 79 location entries, 63 provisional reports and 88 quarantined cells. It remains a private local artifact; observation time/counts were not invented. Source news references were not independently corroborated.

## External acceptance at this historical checkpoint

No live host/domain, hosted TLS, production identity provisioning, real Telegram intake/replies or Google writes have been commissioned. Encrypted off-site storage, alerts and a hosted outage recovery exercise require owner accounts/configuration. Validated geographic inputs, domain-approved methods and field terminology/pilot usability require data-owner approval. Missing source information cannot support verified impact totals, regional coverage or defensible village rankings today.

## GitHub acceptance

[Production validation run 2](https://github.com/Wai-999/Dawei-Flood-Intellegence/actions/runs/37083989391) completed successfully on implementation commit `cf07f8938d8346945c51eacc94a9463276cd3aa1`. Both test-security and container jobs passed on fresh Ubuntu runners, including dependency installation, all 53 tests, explicit module checks, scans, image build/restart smoke and Caddy validation. [Pull request #1](https://github.com/Wai-999/Dawei-Flood-Intellegence/pull/1) contains the source-only release and deployment instructions. Documentation-only follow-up commits remain subject to current PR checks.
