# Single-host deployment

## Architecture decision

Use one operator-owned Linux VM with Docker Compose, Caddy, encrypted persistent storage, one Gunicorn application container, and separate Telegram/Sheets/backup workers sharing the same local database volume. Only Caddy publishes ports 80/443. SQLite serializes transactions; this is a single-instance architecture, not horizontal scaling. Start with a small host sized after pilot load measurement, and monitor disk, memory, response latency and lock contention.

| Approach | Python / persistence / HTTPS | Cost and operational tradeoff |
|---|---|---|
| Linux VM + supplied Compose (chosen) | Persistent named volumes shared locally; automatic Caddy TLS; operator secret files | VM, encrypted off-site storage and domain costs; operator maintains OS, Docker, firewall and recovery |
| Managed container host, e.g. Render | Python containers, HTTPS and paid persistent disk | Fewer host duties, but disk restrictions prevent using this exact multi-service shared-SQLite topology. Consolidate workers under a supervisor or first migrate to managed PostgreSQL |

Provider pricing, availability and account authorization must be checked when purchasing. Render documents [persistent disk restrictions](https://render.com/docs/disks) and [current pricing](https://render.com/pricing). Caddy documents [proxy behavior](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy); Gunicorn documents [deployment](https://gunicorn.org/deploy/). No host or paid plan has been purchased.

## Prepare privately

Clone the approved release commit. Copy `.env.example` to `.env`, chmod it 600, and supply a real domain, HTTPS origin and TLS contact address. Create an ignored `secrets/` directory with mode 700. Do not enter secrets in source, command arguments, shell history or PR descriptions. Files mounted as `/run/secrets` must be readable by UID 10001; use owner 10001 and mode 600 on the Linux host. Restrict host SSH and firewall ingress to intended operators, HTTP/HTTPS and required monitoring. Prefer an authenticated access gateway/VPN and privileged MFA before exposing operational data broadly.

```sh
cp .env.example .env
chmod 600 .env
mkdir -m 700 secrets
docker compose build
python -m flood.recovery keygen --output secrets/backup-signing.key
```

Generate the signing key on the host in the configured Python environment, then set its ownership/permissions for UID 10001. The container secret mount remains read-only. Keep the key in the approved secret manager and retain old keys during rotation. Production backup refuses to run without it.

Privately transfer source files, if desired, into the persistent `/data/source` directory before initialization. The source importer does not download from the live Sheet automatically. Use a one-off operator container or volume administration tool; do not bake files into the image. Then initialize and provision an administrator:

```sh
docker compose run --rm app python -m flood.cli init
docker compose run --rm -it app python -m flood.cli create-user --username operator --role administrator
docker compose up -d app backup proxy
docker compose exec app python -m flood.probe
docker compose logs --tail 100 app backup proxy
```

Provision each reviewer/coordinator/analyst/contributor separately using the same CLI. Readiness returns 503 until an active administrator exists. Point DNS to the chosen host, confirm Caddy obtained a trusted certificate, verify redirects/HTTPS/cookie flags from an external browser, and confirm anonymous API access fails. Never bypass a certificate warning. No production HTTPS was verified in the local build.

## Runtime controls

The pinned Python image runs as UID/GID 10001 with a read-only root filesystem, writable named data/backup volumes, 32 MiB temporary filesystem, dropped capabilities and no privilege escalation. Gunicorn uses one `gthread` worker, four threads, request timeout 30 seconds, graceful timeout 30 seconds and 2-second keepalive. Compose grants 35 seconds to stop. Request/header limits and Caddy header/body timeouts constrain slow clients. Backend port 8000 is not published.

Caddy is the only trusted proxy at 172.29.0.2. It overwrites the client-address header with one actual peer address and strips alternate forwarding headers. The WSGI layer accepts forwarding information only from configured trusted addresses, validates the exact configured Host/origin, requires HTTPS and Secure cookies in production, caps bodies at 64 KiB and rejects conflicting framing. Update the private subnet and trusted proxy list together if they conflict with another network; do not add an untrusted broad subnet.

Public `/health/live` and `/health/ready` disclose status only; `/api/v1/health` requires administrator authentication. Local loopback probes may use HTTP behind the TLS proxy. Configure external monitoring against the real HTTPS readiness URL and private operator monitoring for worker health/backlogs. HTTP liveness alone does not prove integrations or backups work.

## Commission providers

Keep `--profile integrations` off until private token, account mapping and service-account files are mounted. Follow [operations](operations.md), test real private Telegram intake/reply, review it, verify only the owned Sheets tab changed, and test a correction removes stale verified projection. Then start:

```sh
docker compose --profile integrations up -d telegram sheets
```

Do not commission against operational recipients with synthetic data. Use an operator-approved test destination and clean up through audited status transitions.

## Upgrade and rollback

Back up the existing database **before** migration. Stop integrations and API writes, verify and retain the signed bundle, test the migration on a restored copy, then deploy the approved commit/image and run `init`. Migrations 001→002 preserve raw/version/audit rows; future migrations must be numbered. Reconcile IDs/counts, perform authenticated smoke checks and restart workers. Migration failure blocks release. Maintain old image and backup; roll back by restoring to a separate volume/path and changing configuration during an agreed maintenance window. Avoid copying a live WAL database with a filesystem copy.

CI validates branch and PR changes. Require both validation jobs to pass before merging. Tag an approved version or manually run the release workflow to publish a commit-tagged GHCR image with short-lived GitHub credentials. Host deployment is explicit and requires health verification; CI does not secretly deploy or purchase hosting. If using the supplied local-image Compose config, rebuild from the approved commit; an operator may replace `image` with the pinned GHCR digest and remove `build`.

## Scaling thresholds

Move to PostgreSQL/PostGIS before a second API host, shared/network SQLite storage, high-availability failover, GIS boundary queries or sustained write contention. Treat repeated lock errors, growing outbox/review latency or missed backup windows as a capacity incident. Benchmark the pilot workload; no unsupported transactions-per-second promise is made. Introduce a repository adapter and migrate/test record, history, audit and coordinate parity before cutover.
