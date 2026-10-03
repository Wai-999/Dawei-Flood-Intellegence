# Pinned pilot host deployment

These tools automate infrastructure for the exact approved `v0.1.0-pilot` application. `release.json` pins source commit, AMD64 image digest, Caddy digest, schema and configuration version. Changes here do not retag the approved application release. Record the immutable infrastructure commit used to retrieve these files alongside the generated configuration hash and deployment receipt.

The persistent target is an owner-authorized Always Free Linux VM with local block storage. See [provider investigation](../docs/free-infrastructure-research.md) and [autonomous evidence](../docs/autonomous-deployment.md). Account signup, terms, MFA and card verification belong to the account owner. No purchase or upgrade is authorized.

## Safe modes

`python3 infra/bootstrap.py` prints a plan only. On a supported root-owned Linux host, `--mode prepare` validates Ubuntu 22.04/24.04/26.04 or Debian 12/13, AMD64/ARM64, local ext4/xfs/btrfs and free disk space; creates private persistent directories; and generates non-secret configuration. It preserves existing files and refuses configuration drift, symlinks, shared roots and a `STOP_WRITES` incident latch.

`--mode deploy --allow-install --configure-firewall --admin-user <named-operator>` installs Docker/Compose from Docker's signed official apt repository where needed, preserves SSH access before enabling a restrictive firewall, retrieves the pinned release, starts app/backup/Caddy, verifies readiness and database persistence, and configures systemd startup/monitoring. It must run on the newly authorized production host, not the user's workstation or a temporary sandbox. If the SSH client cannot be inferred, supply `--ssh-cidr` explicitly; provider security lists must also allow 80/443 and restrict SSH. Docker-published ports can bypass UFW: only Caddy publishes ports, never the app or SQLite.

Application directories are private host bind mounts; the app runs as UID 10001 with a read-only root filesystem, temporary filesystem, dropped capabilities and no privilege escalation. Telegram and Sheets are disabled by default and contain no credentials. An explicit named administrator receives a generated initial password stored only in a private host file; retrieve privately and follow the existing owner access policy. No humanitarian data, geography, weights or governance approvals are generated.

AMD64 pulls the immutable published digest. ARM64 fetches exactly the approved commit, checks a clean checkout, builds natively, runs both approved smoke scripts and freezes the resulting local image ID. That ARM path is prepared, but no Oracle ARM host has yet been provisioned or tested. An existing different image pin causes a refusal, not a silent update.

Deployment persistence checks write a separate synthetic infrastructure fixture, restart the app and read it, then recreate the app container and read it. They do not invent operational claims. App restart/recreation introduces a brief maintenance interruption. Host reboot and external HTTPS are separate explicit checks; the deployment receipt does not fabricate either.

## Recovery and monitoring

`host-monitor.py --root /srv/dawei-flood --apply` checks read-only database health, disk capacity, containers, backup age, off-site receipt age and enabled worker freshness. Container recovery is bounded to three attempts per 30-minute window with backoff. Database corruption or critical disk exhaustion creates `STOP_WRITES`, stops writers and preserves database/WAL/SHM evidence. It never replaces a corrupt database or restores automatically. Existing recovery procedures, accountable operator review and session revocation apply before restored records are served. The latch also prevents future bootstrap/startup.

`offsite.py push` requires a private `secrets/rclone.conf`, an age public-recipient file and a private approved destination such as `remote:bucket/prefix`. It verifies the signed bundle, encrypts before upload, checks quota, uploads with bounded retries, downloads and compares hashes. `offsite.py restore` downloads, decrypts using an off-host identity, verifies signature/source/database integrity and restores into a new isolated directory using the pinned image. It refuses overwrite. `age` and `rclone` must be installed from trusted distro packages. No production private bucket, remote credentials or off-site upload schedule is active yet. Retention and operational RPO/RTO must be approved by the data owner; there is no automatic deletion of remote backup history.

The default 8 GiB prefix quota is a guard, not proof of whole-account cost safety. Check all buckets, requests, egress and account allowances before enabling a destination. A successful upload receipt is not a restore receipt. Keep both the age identity and trusted signing key independently escrowed and out of source, logs and the cloud application container.

`external-probe.py --domain floodintelligence.duckdns.org` verifies DNS, TCP/TLS, hostname/certificate expiry, HTTP redirect, HSTS, healthy JSON, anonymous API rejection and invalid Host rejection. Secure-cookie/authenticated checks require a private named test account and are separate. The GitHub external-readiness schedule is disabled unless the repository variable `FLOOD_MONITOR_ENABLED` is explicitly set to `true` after real production HTTPS works. It sends no credentials or operational data to GitHub.

`duckdns-update.py` reads a mode-600 owner token file and updates the fixed hostname via HTTPS with bounded retries. It never prints the token or request URL. DNS acceptance and external propagation are distinct checks. Do not commit tokens or request them in a public issue or chat.

`staging.py` is strictly for synthetic Railway anonymous-VM tests. Provider HTTPS replaces public ACME at the staging edge, while Caddy still overwrites forwarding headers and the app enforces its trusted origin. The VM's deletion deadline and creator-IP restriction are explicit; production data is prohibited there.

## Validation

`sh infra/rehearse-linux.sh` creates a separate disposable Linux Compose stack and private synthetic fixtures. It verifies preparation twice, fixed network assignments, readiness, restart/recreation, encrypted transport/isolated restore, tamper rejection, quota refusal and corruption stop/preserve behavior. The rclone local transport fixture is not an off-site production destination. Its unique Compose project/subnet and cleanup scope avoid changing another running pilot.

Production installation/firewall, Oracle native ARM, host reboot, DuckDNS ACME issuance, actual bucket restoration, provider integrations and field acceptance remain unverified until the corresponding live owner-authorized resources exist.
