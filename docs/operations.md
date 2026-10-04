# Operations, recovery and incidents

## Commissioning

Runtime dependencies are pinned in `requirements-production.txt`; the optional source profiler additionally needs `requirements-integrations.txt`. Application preview never starts outbound workers. Production state is shown on the administrator health page with HEALTHY / DEGRADED / BLOCKED / FAILED and explicit NOT COMMISSIONED providers.

Telegram requires a bot token file, an allowlist JSON mapping numeric Telegram sender IDs to active individual account IDs, and one long-poll consumer. Use `TELEGRAM_BOT_TOKEN_FILE` and `TELEGRAM_USERS_FILE`. Private chat is mandatory. Test denied/group senders, guided drafts, preview/confirmation, corrections, evidence, feedback and outage recovery. Restart after changing the allowlist. Revoking a user immediately blocks intake and feedback and revokes sessions. Attachments are retained evidence references; binary attachment storage is outside this release.

The current IPv6 trial uses the [tested keyless Sheets adapter](keyless-sheets.md), narrowly scoped workload identity and a dedicated restricted projection. No long-lived key was created. The original standalone path supports a privately mounted service-account JSON, Sheets API, destination sharing, `GOOGLE_SERVICE_ACCOUNT_FILE` and `GOOGLE_SHEET_ID`. Run `python -m flood.integrations sheets --once`. Confirm the owned `12_Dashboard_Export` tab and exact headers. Sync uses RAW values and replaces the latest verified per-location projection, blanks stale trailing rows, and never shifts or repairs the original source tabs. A failed provider write leaves the canonical database intact. Header conflict refuses overwrite. Protect this owned tab from concurrent manual editing.

Provider network calls use HTTPS to owned API hosts, do not follow redirects, and use bounded timeouts. Google authorization uses the official [service-account client](https://developers.google.com/identity/protocols/oauth2/service-account). See [Sheets batch values](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdate) and [Telegram polling](https://core.telegram.org/bots/api#getupdates). Telegram may redeliver a reply after a lost acknowledgement; stable IDs let operators recognize it and intake does not create a second assessment.

Workers hold an OS lock per database/kind. Sheets polls every 30 seconds; errors back off 2–60 seconds. Projection/feedback jobs stop automatic retries after eight failures. Diagnose access/schema/provider error, then use the privileged host CLI `python -m flood.cli retry-failed --kind sheets --reason "Access corrected and destination reviewed"` (or `--kind feedback`). Requeue is audited. Do not edit canonical data to hide a failure. The current adapter records an idle heartbeat when no projection jobs are pending; the deployed host monitor checks container liveness separately. Inspect pending/failed jobs and heartbeat age rather than treating expected idle as failed projection.

## Backup contract

Default targets: **RPO ≤ 1 hour**, **RTO ≤ 60 minutes**, hourly backups and 30-day local retention. These are operating targets pending owner approval and a hosted disaster drill. The small local restore measured 0.006 seconds; it does not demonstrate a hosted RTO. Frequency/retention are configured with `FLOOD_BACKUP_INTERVAL_SECONDS` and `FLOOD_BACKUP_RETENTION_DAYS`.

The backup worker uses SQLite's consistent online backup, integrity_check, foreign_key_check and reconciliation of location/assessment/submission/version/audit/assistance counts. Each bundle includes the database and available source snapshot/profile/original workbook, per-file SHA-256 and a HMAC-SHA256 signed manifest. Private files are mode 600; restore destinations are new directories. Production requires `FLOOD_BACKUP_SIGNING_KEY_FILE`; missing or wrong key fails verification. HMAC detects tampering by someone without the key and does **not encrypt** the contents. Root or a stolen signing key remains a trust boundary.

```sh
python -m flood.recovery keygen --output /private/secrets/backup-signing.key
# Configure key/source/database/backup paths privately in the environment.
python -m flood.recovery once
python -m flood.recovery inspect --path /private/backups/flood-TIMESTAMP.tar.gz
python -m flood.recovery restore --path /private/backups/flood-TIMESTAMP.tar.gz --output /private/new-restore-directory
```

Local retention deletes only owned, successfully verified expired bundles after a successful new backup. A malformed old bundle stops retention and makes worker failure visible. Keep the signing key separately, securely escrow it, record key ID and retain historical keys while old backups exist. Restore using the matching trusted key; copying a key alongside an untrusted backup does not establish trust.

Configure encrypted off-site copies in an owner-approved storage account with separate least-privilege credentials, lifecycle retention and alerting. Named Docker volumes alone do not protect against host loss. Verify at least daily that an off-site copy exists; perform a monthly isolated restore and reconcile source and audit counts. The current temporary trial has an active tested hourly signed age-encrypted private GCS upload/download timer and actual separate owner-side signed restore. Independent unattended transport, custody/retention acceptance and owner alert receipt remain open; the trial bucket alone cannot protect against account loss. See [current commissioning](commissioning-status.md).

## Restore drill and outage

Stop writes/integration consumers; preserve the failed volume and logs. Verify the bundle signature using the separately trusted key. Restore into a new directory/volume, validate integrity/counts, configure `/data/flood.sqlite3` from restored `database.sqlite3`, put snapshots into the configured source directory, and start API only. Sessions are included in backups: revoke restored sessions before allowing external traffic. Provision/verify active operator identity, confirm raw/history/evidence/resource parity, then restart one worker of each kind and reconcile provider checkpoint/outbox. Never overwrite live evidence or restart both old/new Telegram consumers simultaneously.

Before upgrades, `python -m flood.cli backup` reads the existing database without applying migration. The simple `check-backup` and `restore` commands support legacy DB copies. Signed bundles are the production recovery format. Audit rows and raw history remain in the restored database; backup creation itself generates a later audit event outside that snapshot.

## Daily operator checks

Monitor external readiness, private API/DB health, disk space/inodes, memory/CPU, host logs, login failures, provider last success, Telegram offset, failed/exhausted outbox/feedback, oldest review age and backup/signature/off-site age. Analytics recompute on authenticated requests; priority snapshots retain method and source versions. Log request status/time, never cookies/passwords/token URLs/report bodies. Route actionable alerts to the approved operator channel; actual owner alert delivery remains uncommissioned. Provider replies and projection writes have separate authorization and commissioning evidence.

Compromised account: administrator deactivation revokes sessions, stops feedback and preserves evidence. Compromised bot/service key: suspend relevant worker, rotate in the secret manager, review access/audit and restart after an approved test. Lost host: execute isolated restore and reconciliation. Wrong coordinates: correct with evidence and review, retain original versions. Stale pledges: cancel or update through coordinator events, inspect ETA/expiry/unconfirmed receipts. Connectivity loss: save drafts privately, show delayed data and explicitly retry when connected. Verification overload: triage conflicts/high-impact claims and investigation reasons; never automatically verify copied sources. Selection bias: disclose unreported worklist entries and missing regional denominator; do not infer safety.
