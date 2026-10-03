#!/bin/sh
# Disposable Linux/Compose regression drill. Contains synthetic data only.
set -eu
task_variant=${1:-}
case "$task_variant" in ''|--ipv6) ;; *) echo 'Unsupported rehearsal variant'; exit 1;; esac
task_root=$(mktemp -d /var/tmp/dawei-rehearsal.XXXXXX)
task_offsite=$(mktemp -d /var/tmp/dawei-offsite.XXXXXX)
task_source=$(pwd)
compose() { sudo docker compose --env-file "$task_root/compose.env" -f "$task_root/compose.yml" -f "$task_root/rehearsal.yml" "$@"; }
cleanup() {
    compose --profile maintenance --profile telegram --profile sheets down >/dev/null 2>&1 || true
    case "$task_root" in /var/tmp/dawei-rehearsal.*) sudo rm -rf "$task_root";; esac
    case "$task_offsite" in /var/tmp/dawei-offsite.*) sudo rm -rf "$task_offsite";; esac
}
trap cleanup EXIT INT TERM
sudo python3 infra/bootstrap.py --mode prepare --root "$task_root" --domain flood.example $task_variant
sudo python3 infra/bootstrap.py --mode prepare --root "$task_root" --domain flood.example $task_variant
sudo python3 - "$task_root" "$task_offsite" <<'PY'
import os,sys,secrets
from pathlib import Path
r=Path(sys.argv[1]);o=Path(sys.argv[2]);os.umask(0o077)
(o/'objects').mkdir(mode=0o700)
# Each rehearsal owns a distinct project/subnet and cannot replace a running pilot.
p=r/'compose.yml';p.write_text(p.read_text().replace('name: dawei-pilot','name: dawei-rehearsal-'+r.name.rsplit('.',1)[-1].lower()).replace('172.29.0.','172.31.0.'))
p=r/'runtime.env';p.write_text(p.read_text().replace('172.29.0.','172.31.0.'))
k=r/'secrets/backup-signing.key';k.write_bytes(secrets.token_bytes(64));os.chown(k,10001,10001)
(r/'rehearsal.yml').write_text(f'''services:
  proxy:
    ports: !override ['127.0.0.1:18080:8080']
    volumes: !override
      - {r}/Caddyfile-rehearsal:/etc/caddy/Caddyfile:ro
      - {r}/caddy-data:/data
      - {r}/caddy-config:/config
''')
(r/'Caddyfile-rehearsal').write_text('''{
    auto_https off
}
:8080 {
    reverse_proxy app:8000 {
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto https
        header_up -X-Forwarded-Host
    }
}
''');(r/'Caddyfile-rehearsal').chmod(0o644)
(r/'secrets/rclone.conf').write_text('[drill]\ntype = local\n')
PY
compose run --rm --no-deps -T maintenance python -c 'from pathlib import Path; from flood.repository import Repository,dump; from flood.auth import create_user; import secrets; from datetime import datetime,timezone; r=Repository("/data/flood.sqlite3"); actor=create_user(r,"synthetic-compose-rehearsal","administrator",secrets.token_urlsafe(32)); p={"state_region":"SYNTHETIC","township":"SYNTHETIC","village":"SYNTHETIC","observed_at":datetime.now(timezone.utc).isoformat(),"source_reference":"Synthetic Linux Compose regression"};r.submit(p,dump(p),actor,"administrator","compose-fixture"); s=Path("/data/source");s.mkdir();(s/"source_profile.json").write_text(dump({"synthetic":True}))' >/dev/null
compose up -d app backup proxy
if [ "$task_variant" = --ipv6 ]; then
    compose exec -T app python -c 'import socket; assert socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET6), "Container IPv6 address missing"'
fi
sudo python3 - "$task_root" "$task_source" <<'PY'
import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('bootstrap',Path(sys.argv[2])/'infra/bootstrap.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.wait_ready(Path(sys.argv[1]));m.verify_persistence(Path(sys.argv[1]))
PY
curl --fail --silent -H 'Host: flood.example' http://127.0.0.1:18080/health/ready | python3 -c 'import sys,json;assert json.load(sys.stdin)=={"status":"HEALTHY"}'
test "$(curl --silent -o /dev/null -w '%{http_code}' -H 'Host: flood.example' http://127.0.0.1:18080/api/v1/health)" = 401
# Stop the one scheduled writer before a one-shot backup; the worker lock must not be bypassed.
compose stop backup >/dev/null
compose run --rm --no-deps -T maintenance python -m flood.recovery once >/dev/null
sudo age-keygen -o "$task_offsite/identity.key" >/dev/null
sudo sh -c 'age-keygen -y "$1/identity.key" > "$2/recipient.txt"' sh "$task_offsite" "$task_root"
sudo python3 infra/offsite.py push --root "$task_root" --destination "drill:$task_offsite/objects" --recipient-file "$task_root/recipient.txt" >/dev/null
task_object=$(sudo python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["object"])' "$task_root/offsite-receipt.json")
sudo python3 infra/offsite.py restore --root "$task_root" --destination "drill:$task_offsite/objects" --identity-file "$task_offsite/identity.key" --object "$task_object" --output "$task_root/evidence/restored" >/dev/null
if sudo python3 infra/offsite.py push --root "$task_root" --destination "drill:$task_offsite/objects" --recipient-file "$task_root/recipient.txt" --max-remote-bytes 1 >/dev/null 2>&1; then
    echo 'Capacity guard failed'; exit 1
fi
sudo python3 - "$task_root" "$task_offsite/objects/$task_object" <<'PY'
import sqlite3,sys
from pathlib import Path
r=Path(sys.argv[1]);p=Path(sys.argv[2])
with sqlite3.connect(r/'evidence/restored/database.sqlite3') as c:
 assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 assert not c.execute('PRAGMA foreign_key_check').fetchall()
 assert c.execute('SELECT COUNT(*) FROM assessments').fetchone()[0]==1
 assert c.execute('SELECT COUNT(*) FROM assessment_versions').fetchone()[0]==1
b=bytearray(p.read_bytes());b[-1]^=1;p.write_bytes(b)
PY
if sudo python3 infra/offsite.py restore --root "$task_root" --destination "drill:$task_offsite/objects" --identity-file "$task_offsite/identity.key" --object "$task_object" --output "$task_root/evidence/tampered" >/dev/null 2>&1; then
    echo 'Tampered ciphertext accepted'; exit 1
fi
# Trial expiry rehearsal uses only the disposable synthetic fixture, never owner account evidence.
sudo python3 - "$task_root" <<'PY'
import json,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
r=Path(sys.argv[1]);now=datetime.now(timezone.utc)
(r/'TRIAL_REQUIRED').write_text('SYNTHETIC TRIAL REHEARSAL')
p=r/'trial-evidence.json';p.write_text(json.dumps({'policy':'TEMPORARY_FREE_TRIAL_NO_UPGRADE_V1','account_type':'FREE_TRIAL','nonbillable':True,'upgraded':False,'captured_at':(now-timedelta(hours=13)).isoformat(),'remaining_credit_usd':300,'shutdown_at':(now+timedelta(days=2)).isoformat(),'expires_at':(now+timedelta(days=10)).isoformat(),'official_terms_checked_on':now.date().isoformat(),'billing_reporting_lag_reviewed':True,'credit_source':'SYNTHETIC REHEARSAL','credit_evidence_sha256':'a'*64}));p.chmod(0o600)
# Trial containers wait for a successful systemd guard after a host or Docker restart.
p=r/'compose.yml';p.write_text(p.read_text().replace('restart: unless-stopped',"restart: 'no'"))
PY
compose up -d app backup proxy >/dev/null
if sudo python3 infra/trial_guard.py --root "$task_root" --apply >/dev/null; then
    echo 'Stale trial evidence accepted'; exit 1
fi
sudo test -f "$task_root/STOP_WRITES"
if [ -n "$(compose ps --status running -q)" ]; then
    echo 'Trial guard did not stop containers'; exit 1
fi
sudo systemctl restart docker
if [ -n "$(compose ps --status running -q)" ]; then
    echo 'Docker restarted a trial writer without authorization'; exit 1
fi
sudo python3 - "$task_root" <<'PY'
import sqlite3,sys
from pathlib import Path
r=Path(sys.argv[1]);saved=r/'evidence/trial-stop/flood.sqlite3'
assert saved.is_file()
with sqlite3.connect(saved.as_uri()+'?mode=ro',uri=True) as c:
 assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
# Only this named disposable CI fixture is reset for the separate corruption drill.
assert r.name.startswith('dawei-rehearsal.')
(r/'STOP_WRITES').unlink();(r/'TRIAL_REQUIRED').unlink();(r/'trial-evidence.json').unlink()
PY
compose up -d app backup proxy >/dev/null
compose stop app >/dev/null
sudo python3 - "$task_root" <<'PY'
import shutil,sys
from pathlib import Path
r=Path(sys.argv[1]);p=r/'data/flood.sqlite3';shutil.copy2(p,r/'evidence/original-fixture.sqlite3');p.write_bytes(b'SYNTHETIC CORRUPTION FIXTURE')
PY
sudo python3 infra/host-monitor.py --root "$task_root" --apply >/dev/null || true
sudo test -f "$task_root/STOP_WRITES"
if sudo python3 infra/bootstrap.py --mode prepare --root "$task_root" --domain flood.example >/dev/null 2>&1; then
    echo 'Incident latch was bypassed'; exit 1
fi
sudo python3 - "$task_root" <<'PY'
from pathlib import Path
import sys
r=Path(sys.argv[1]);assert (r/'data/flood.sqlite3').read_bytes()==b'SYNTHETIC CORRUPTION FIXTURE'
copies=list((r/'evidence').glob('incident-*/flood.sqlite3'));assert len(copies)==1;assert copies[0].read_bytes()==b'SYNTHETIC CORRUPTION FIXTURE'
PY
echo 'Linux preparation/idempotence/Compose/restart/recreation/encrypted roundtrip/tamper/capacity/corruption latch: PASS'
echo 'Trial stale-evidence stop, evidence preservation and Docker restart with writers stopped: PASS'
echo 'Local rclone test destination is a transport fixture, not production off-site commissioning.'
