# Hosting decision — authorized temporary allowance

Updated October 4, 2026 UTC. The owner's latest allowance-only instruction supersedes the earlier sustainable-only answer. The existing owner-created, unupgraded, non-billable Google trial is actually deployed and tested. **TEMPORARY FREE — NOT SUSTAINABLE.** No paid continuation, purchase, payment entry, renewal or Oracle deployment is authorized.

The provider comparison and rejected ephemeral-database alternatives are preserved in [the prior researched decision](archive/free-hosting-decision-before-live.md) and [infrastructure research](free-infrastructure-research.md). They are historical research, not current missing-access claims. The expired anonymous Railway trial was not restarted.

## Selected and tested topology

One eligible-region `e2-micro` VM, a 30 GB standard local persistent disk, private encrypted-backup bucket and reserved external IPv6 preserve the approved single-host SQLite architecture. Private IAP supplies administration. No public VM IPv4, NAT, load balancer or managed DNS zone was created. The real DuckDNS HTTPS endpoint, persistence through actual reboot and real off-site signed restore passed; see [deployment evidence](autonomous-deployment.md).

IPv4-only clients use a separately assigned Cloud Run HTTPS ingress, tested externally with the real application. Direct VPC reaches the same persistent VM over trusted private TLS; the ingress stores no SQLite or source data. Observed request-based billing, minimum zero / maximum one instance, concurrency one, 128 MiB memory, ten-second request timeout and disabled startup CPU boost bound this component. They are not unlimited-free-use guarantees or hard monetary caps. Custom-domain Cloud Run mapping was not used because the documented inability to disable TLS 1.0/1.1 would weaken the tested baseline.

## Cost and account evidence

The account remains an actual Free Trial; the current UI displayed the original remaining credit, while billing reporting can lag more than a day. A displayed zero bill is not proof of unused aggregate allowances. All linked projects were enumerated and the intended account/project scope verified; pre-provisioning resource inventory was retained privately. No usage evidence was fabricated.

[Google trial and allowance terms](https://docs.cloud.google.com/free/docs/free-cloud-features) distinguish the temporary non-billable trial from sustainable billing-linked Free Tier use. [Cloud Run pricing](https://cloud.google.com/run/pricing) aggregates free requests/CPU/memory across a billing account; global egress is not universally free. [Budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps) are not a guaranteed zero-cost cap. Trial credit may absorb metered usage; no permanent $0 promise is made.

The separately tested trial policy retains a recovery reserve, conservative cutoff recorded privately before the advertised expiry, and a twelve-hour freshness requirement for real account/credit observations and independently restored recovery. Stale/missing evidence stops writes and containers. The sustainable non-trial guard was not weakened. The owner computer holds an actual encrypted archive and separately escrowed identity, but continuous independent transport is not commissioned. The trial bucket alone cannot survive loss of the trial account.

## Proven owner boundaries

- **D — Independent cloud backup authorization:** a continuing independently accessible private destination still requires a scoped owner grant. [Rclone Drive documentation](https://rclone.org/drive/) recommends an owner OAuth client because its shared client is being retired during 2026; `drive.file` can restrict access to app-created backup files. Existing SDK consent does not grant Drive access. No broad Drive token or recovery identity was transferred to the VM.
- **TESTED — Integration authorization:** owner-authorized Telegram token/sender and the dedicated restricted Sheets projection are installed. Both workers are active; Sheets passed a real isolated projection drill and Telegram transport/checkpoint checks passed. Complete guided Telegram intake remains a controlled operator exercise. [Provider evidence](provider-commissioning.md) records the keyless/IPv6 adaptation and tested limits.
- **D — Accountable acceptance:** recovery custody/retention/on-call responsibilities, descriptive-only methodology, geography and quarantined-claim review, Burmese field review, named pilot participants and field acceptance cannot be self-approved by infrastructure automation.

These are the remaining boundaries. Host access, DuckDNS, real HTTPS, persistent storage and a real independent restore have been solved. Current evidence and the minimum handoff are in [commissioning status](commissioning-status.md).
