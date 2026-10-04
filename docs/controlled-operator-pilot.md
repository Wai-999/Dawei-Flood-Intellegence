# Descriptive-only operator exercise

The owner approved TFUCC as the initial technical test operator and descriptive-only reporting on October 4, 2026. This approval does not verify disaster claims, approve geography, appoint an on-call owner, accept Burmese language, or sign field acceptance.

The optional infrastructure adapter reuses the approved application's existing Telegram poller, authorization, worker lock, reply retry and offset checkpoint. It routes only the approved operator's conversations after an explicit `/pilot_start` into a separate private SQLite database. That database must be mounted only into the Telegram worker, with no app, Sheets or source-import access. Other operators retain ordinary authorization. It adds no bot, polling consumer, application image or humanitarian model.

Each test reply states that its data is isolated. A session lasts at most one hour. Expiry keeps the operator in a blocked test context until `/pilot_end`; test messages never silently fall through into operational intake. Control reply retries preserve the original deadline. Malformed or unreadable adapter configuration fails closed. Existing trial and corruption guards remain authoritative.

Use an explicitly synthetic location with no coordinates or geographic aliases in the isolated database. Exercise `/new`, required fields, unknown values, `/skip`, `/back`, `/save`, `/resume`, preview, confirmation, duplicate confirmation, status, correction with a source/reason, and `/pilot_end`. Record actual operator messages and Bot API delivery privately. Reconcile operational rows and the private projection before and after. Do not promote or export the fixture, impersonate a sender, or call local regression inputs a real Telegram field exercise.

Six adapter regressions verify isolated confirmation/correction/replay, expiry across reconstruction, unchanged normal help, scope/operator restrictions, and checkpoint retention after a failed send. The full local suite passes 104 tests. These regressions are source validation. The subsequent actual technical exercise is recorded below; accountable operator and field acceptance remain separate.

Application release remains pinned to `c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc`. Trial hosting remains **TEMPORARY FREE — NOT SUSTAINABLE**.

## Actual technical exercise — October 4, 2026 UTC

The merged adapter at infrastructure commit `ff647ecb51863cce77616bbb724d79457bdeda16` was installed into the existing Telegram worker using configuration `trial-isolated-operator-pilot-1`. Its approved application image, sender allowlist, other services and protected operational/owner rows were unchanged. Failed isolated preparation attempts were preserved before a new successful test database was created.

Actual messages from the authorized operator's existing Telegram session passed isolated activation, guided `/new`, required-field rejection, unknown optional values, `/skip`, `/back`, saved draft/resume, exact preview and confirmation. Confirmation before preview was rejected without creating a report. The report remained unverified. A repeated confirmation retained one report and one version.

A real worker-container removal/recreation preserved the complete draft and original session deadline. The app and Sheets containers were unchanged. Actual mount inspection confirmed that the isolated database/configuration and Telegram credential mount were absent from app and Sheets.

The real correction workflow accepted explicitly synthetic changed fields and source, rejected preview without a reason, then accepted reason/preview/confirmation. Repeated correction confirmation retained one report and two versions. The original version retained its unknown count; the corrected test version used a synthetic count of twelve and returned to `needs_review`. No geographic coordinates, alias, claim verification or operational promotion was made.

Actual status, draft cancellation, `/pilot_end` and ordinary help delivery afterward were acknowledged. Protected operational/owner row hashes and integrity/foreign-key checks passed; the corrected test report remains privately isolated. The private projection visibly retained headers only. Private receipts and message evidence record these checks; provider connection failures and bounded recovery were observed, so no delivery-latency guarantee is made.

This is **TESTED technical guided intake**, performed under the owner's descriptive-only approval. It is not a human field exercise, Burmese-language approval, sustained capacity certification or signed FIELD-ACCEPTED/OPERATIONAL state. A second unauthorized live sender and deliberate provider-failure injection were not exercised; their regressions do not substitute for those real acceptance checks. The previous host reboot proof predates this optional adapter; its live persistence proof covers worker recreation.
