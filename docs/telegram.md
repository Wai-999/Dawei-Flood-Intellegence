# Telegram conversation and low-bandwidth intake

Workers are not started automatically. Configure token and an allowlist mapping Telegram sender IDs to active local contributor accounts, then run the worker. Never paste secrets into chat or commit them.

Main commands: `/start`, `/new`, `/back`, `/skip`, `/save`, `/resume`, `/cancel`, `/preview`, `/confirm`, `/find <query>`, `/status <report_id>`, `/update <report_id>`, `/correction <report_id>`, `/reason <reason>`, `/template`, `/evidence <report_id> <reference>`, `/feedback`, `/help`. Inline buttons invoke those same commands. Draft state is saved in SQLite after every response. It is not an offline Telegram transport: Telegram requires connectivity. The web form can retain a device-local structured-text draft for explicit retry.

Guided sequence: approved location ID; observed_at with timezone; affected households; affected people; displaced people; water/food/shelter/medical needs; road status; source. Back revisits a field; skip is available for optional observations; cancel clears draft; save/resume preserve it. Preview shows exact parsed fields and validation. Confirm is required before ingestion, and replay returns the original ID. Fields not assessed stay blank with explicit state.

Structured template:

```text
#FLOOD_REPORT
report_type: new
location_id: TFUCC-00-01
observed_at: 2026-10-02T13:00:00+06:30
affected_households:
affected_population:
displaced_population:
water_need: unknown
food_need: unknown
road_access: unknown
source_reference: field team observation reference
```

Compact format uses a reviewed location ID and explicit time/source; it does not guess regional aliases:

```text
FR|TFUCC-00-01|2026-10-02T13:00:00+06:30|team-reference|AH=84|W=critical|ROAD=blocked
```

Structured input is parsed deterministically into a durable preview. Ambiguous estimates, repeated keys, unknown fields, unzoned dates and invalid enums return correction messages. No AI fills missing numbers or coordinates. `/update ID` starts a structured full preview with current fields, expected version and required correction reason/source. The user confirms; correction creates a new version and returns to review. Contributors update only their own reports. `/status` returns permitted review status and ID; it does not reveal other contributors' raw evidence or sensitive logistics. Evidence can be added with `/evidence` and a source reference. Direct binary file-upload/scanning storage remains deferred.

Durable Telegram update checkpoints advance only after a successful response. Confirmation saves its response in the draft so a network retry cannot create a second report. External errors remain in integration state and retry with bounded backoff. Owner-addressed feedback covers receipt, clarification/follow-up requests, verification/correction and assistance pledge/dispatch/delivery/receipt events without quantities or private logistics. `/feedback` returns only the signed-in owner’s feedback. Delivery uses an active private recipient mapping; stable feedback IDs help recognize at-least-once replies. Real Telegram commissioning remains external.
