# Source quality and import policy

Source: owner-supplied Google Sheet exported read-only on 2026-10-02. Its identifier, snapshot, workbook and row-level data remain outside the public repository.

Read-only live export captured 2026-10-02. SHA-256 and exact rows/cell coordinates are saved in the local source profile/snapshot. Underlying news URLs are source references supplied by the workbook; they have not been independently authenticated or corroborated. Current operational findings concern the workbook only.

| Finding | Evidence | Risk and handling |
|---|---|---|
| No completed field assessments | 75 populated field rows, only ID/township/name cells | No verified human-impact total; blanks remain not assessed |
| Duplicate township/name | 75 rows, 74 distinct composite keys | Separate worklist IDs retained; identity conflict flag |
| Mixed grain | 63 named public rows plus 4 aggregate placeholders | Aggregate placeholders excluded from village inventory and totals |
| Count mismatch | Summary B4=64 versus 63 named public rows | Summary retained as a source claim, not canonical count |
| Housing column has text | 22 named rows contain nonnumeric K values | H:O quarantined on every public row due alignment uncertainty |
| Verification column has numbers | 9 named rows contain numeric O values | No auto-verification or casualty relocation |
| Missing coordinates | No latitude/longitude columns supplied | No guessed village points, map explicitly unavailable |
| Unknown observation time | Event period is a date range; update date is 2026-09-30 | Do not substitute update/upload date for observation time |
| Coverage denominator missing | Worklist is partial and contains grouped names | Regional coverage/silent-zone severity cannot be calculated |
| Source independence unknown | Shared publisher references on many rows | Repeated URL is one independence group, no independent corroboration |

Next correction: a reviewer must compare the original evidence and individually identify the correct casualty, housing, access and needs fields. Do not shift entire columns using a guessed pattern. Verify location names, grouped villages and aliases against an approved registry. Replace incomplete summary formulas after authoritative identities reconcile. All corrections create new report versions with reason and source.
