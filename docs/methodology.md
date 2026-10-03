# Algorithms and indicator definitions

All thresholds and humanitarian parameters need an explicit domain-owner approval reference. No priority model or half-life is active initially. The software's technical authentication/body limits are security controls, not humanitarian thresholds.

| Algorithm | Purpose / inputs / outputs | Model / assumptions / failure | Override, audit and tests |
|---|---|---|---|
| Validation v1 | Typed report → cleaned values, errors/flags | Nonnegative integer counts, paired coordinates, subset rules. Baseline may be disputed with reason | Reviewer correction creates version; invalid raw retained; test impossible counts/NaN/future date/Unicode digits |
| Identity v1 | Composite state/township/name or stable ID → location | NFC/whitespace/case normalization, exact match only. Similar/grouped names may differ | Human selects IDs or future alias approval; test duplicate names across townships and ambiguous exact identities |
| Replay v1 | Actor + idempotency key + hash → existing report or conflict | Transactional unique key; same key/different content rejected | New corrected submission uses new key; test simultaneous retry and changed payload |
| Duplicate suggestion v1 | Location and observation time → review flag | Same timestamp only a deterministic signal, not probability. Copied sources not independent | Reviewer keeps both or supersedes with reason; test no auto-merge |
| Verification v1 | Version, decision, reason/evidence → retained review event | Quarantined claims require corrected version. Evidence is selected by accountable reviewer | Reopen/reject/supersede audited; test stale version and missing evidence |
| Freshness v1 | Observation time and approved field half-life → age/index | exp(-ln(2)*age/half-life). Unknown time=unknown; upload not substitute | Versioned analyst policy; original values unchanged; test delayed upload/stale road |
| Severity v1 | Approved weights and observed rates/needs/access → interval and contributions | Needs ordinal coding none=0, low=.25, medium=.5, high=.75, critical=1; access 0/.5/1. These are explicit heuristic mappings, not probabilities. Unknown component spans [0,1]. Confidence never discounts need | Approval reference and formula version saved; weights sum 1. No ordinal ranking of incomplete intervals; test missing/zero and separate confidence |
| Investigation v1 | Flags, missing time/coordinates/review → reasons | Categorical information gaps; no numeric humanitarian score | Human investigations remain separate decisions; test unreported not safe |
| Resource gap v1 | Requirement, stock, confirmed receipts/in-transit by unit/period → gaps | Confirmed=max(0,requirement-stock-receipts); projected=max(0,confirmed-in_transit). Pledges separate. Unknown stock=unknown gap; consumed stock must be reassessed, not double counted | New requirement period/follow-up; event quantities audited; test pledge/delivery/receipt/unit isolation |
| Deconfliction v1 | Requirement and planned flows → potential excess | max(0,stock+receipts+transit+pledges-requirement); qualitative warning, not cancellation | Coordinator action; audited pledge events; test multi-organization excess |
| Sensitivity v1 | Approved weights → baseline plus one component +20% and renormalization | Scenario, not fact. This is an example perturbation, not an approved operational threshold | No classification/rank fabricated; test changed contribution and unknown interval |
| Statistics v1 | Latest verified known counts → n/sum/mean/median/min/max/range/population variance/stddev | Descriptive census of known records, not random sample. Unknowns excluded with missing count; all missing=null | Source record IDs and versions exposed; no CI/Bayes without sampling/calibration; test all missing vs observed zero |
| Coverage v1 | Partial worklist vs imported reports → entries with no matched report | Regional denominator unknown; no silent-zone inference without registry/exposure | GIS/data owner supplies approved registry; test aggregate placeholders excluded |
| Sheets outbox v1 | Verified records and job queue → operational projection or retained error | OAuth server-side, bounded retry, schema check, idempotent overwrite of owned projection | Operator fixes cause then uses audited retry-failed CLI; failures visible and data retained; mock integration tests |

## Dashboard indicator contract

Each output includes `calculated_at`, `method_version`, report IDs and current versions. Refresh uses a 30-second visible-tab poll; there is no claim of streaming real-time updates.

| Indicator | Numerator / denominator / unit | Time window / grain / missingness | Freshness, confidence and lineage |
|---|---|---|---|
| Reports | Stored permitted assessments / none / reports | Filtered observation date, township/status/search; unknown dates excluded from date filters | Submission IDs, statuses and original times |
| Reported locations | Latest non-rejected report per canonical location / none / locations | Filtered snapshot, provisional allowed and labeled | Not affected-village census; partial registry warning |
| Verified locations | Latest verified report per location / none / locations | Separate official subset | Reviewer event and version; older verified record may differ from latest provisional |
| Verified share | Latest active records currently verified / active records / % | Snapshot per location; empty denominator=null | Verification status, no estimate of truth probability |
| Affected/displaced/deaths/housing | Sum of known values in latest verified location records / n known and n missing / people or houses | Filtered latest verified subset | Null if all missing; no casualty total from quarantined source |
| Affected/displacement rate | Affected/displaced people / baseline people / fraction | Per assessment observation time | Unknown/zero denominator=null; baseline-disputed warning |
| Review backlog | submitted/needs_review reports / none / reports | Current queue; received→now age | Raw/source access reviewer/admin only |
| Unknown observation time | Active records missing observed_at / active records / records and share | Snapshot | Freshness unknown, not derived from import timestamp |
| Coordinate coverage | Approved coordinate locations / partial location inventory / locations | Current identity set | Coordinate source and reviewer status; no region-wide percent |
| Regional reporting coverage | Recently assessed expected villages / complete expected villages / % | Approved registry/recency absent | Unknown, not 0%; no unreported safety claim |
| Humanitarian severity | Weighted known contributions / approved normalized weights / 0–100 interval | Current report; missing components span full support | Separate confidence/freshness; source IDs and method version |
| Confirmed/projected gap | Requirement minus realized receipts/stock (and transit) / none / requirement unit | Same location/resource/unit/period | Unknown stock=null; pledge does not lower confirmed gap |
| System health | Job status/attempts, database integrity, queue age / none | Current system state | Administrator only; disconnected integrations explicit |

Uncertainty ranges here reflect missing components, not statistical confidence intervals. No causal attribution, normality, representativeness, Bayesian independence or Monte Carlo distribution is assumed.

Ordering sensitivity compares only complete verified indicator sets, perturbing one approved weight by +20% and renormalizing. It saves scenario ranks, best/worst rank and changed ordering; this is deterministic scenario analysis, not probability. Unknown fields remain unranked. Field clocks survive corrections to other fields; last confirmation can refresh a field only when supplied with provenance. Pledge expiry excludes planned coverage, ETA signals delay, and delivered-but-unconfirmed quantities remain outside confirmed receipts.
