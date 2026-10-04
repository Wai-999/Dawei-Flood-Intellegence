# Descriptive-only operator exercise

The owner approved TFUCC as the initial technical test operator and descriptive-only reporting on October 4, 2026. This approval does not verify disaster claims, approve geography, appoint an on-call owner, accept Burmese language, or sign field acceptance.

The optional infrastructure adapter reuses the approved application's existing Telegram poller, authorization, worker lock, reply retry and offset checkpoint. It routes only the approved operator's conversations after an explicit `/pilot_start` into a separate private SQLite database. That database must be mounted only into the Telegram worker, with no app, Sheets or source-import access. Other operators retain ordinary authorization. It adds no bot, polling consumer, application image or humanitarian model.

Each test reply states that its data is isolated. A session lasts at most one hour. Expiry keeps the operator in a blocked test context until `/pilot_end`; test messages never silently fall through into operational intake. Control reply retries preserve the original deadline. Malformed or unreadable adapter configuration fails closed. Existing trial and corruption guards remain authoritative.

Use an explicitly synthetic location with no coordinates or geographic aliases in the isolated database. Exercise `/new`, required fields, unknown values, `/skip`, `/back`, `/save`, `/resume`, preview, confirmation, duplicate confirmation, status, correction with a source/reason, and `/pilot_end`. Record actual operator messages and Bot API delivery privately. Reconcile operational rows and the private projection before and after. Do not promote or export the fixture, impersonate a sender, or call local regression inputs a real Telegram field exercise.

Six adapter regressions verify isolated confirmation/correction/replay, expiry across reconstruction, unchanged normal help, scope/operator restrictions, and checkpoint retention after a failed send. The full local suite passes 104 tests. These checks are source validation; live installation, actual guided input and accountable operator acceptance must be recorded separately.

Application release remains pinned to `c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc`. Trial hosting remains **TEMPORARY FREE — NOT SUSTAINABLE**.
