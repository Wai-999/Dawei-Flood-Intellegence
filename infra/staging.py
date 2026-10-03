#!/usr/bin/env python3
"""Bounded Railway trial rehearsal. Synthetic data only; never a persistent production host."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time

spec = importlib.util.spec_from_file_location('bootstrap', Path(__file__).with_name('bootstrap.py'))
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic-only', action='store_true', required=True)
    parser.add_argument('--root', type=Path, default=Path('/srv/dawei-staging'))
    parser.add_argument('--domain', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'preview-[a-f0-9]+\.up\.railway\.app', args.domain) or args.root != Path('/srv/dawei-staging'):
        raise ValueError('Dedicated Railway staging directory and assigned trial hostname required')
    os.umask(0o077)
    bootstrap.validate(args.root, args.domain)
    bootstrap.verify_linux(args.root)
    image = bootstrap.RELEASE['amd64_image']
    bootstrap.prepare(args.root, args.domain, image)
    bootstrap.write_once(args.root / 'STAGING_ONLY', 'SYNTHETIC ONLY; trial host will be deleted; not production\n')
    bootstrap.write_once(args.root / 'Caddyfile-staging', '''{
    auto_https off
}
:8080 {
    request_body {
        max_size 64KB
    }
    reverse_proxy app:8000 {
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto https
        header_up -X-Forwarded-Host
        header_up -X-Forwarded-Ssl
        header_up -X-Forwarded-Protocol
    }
    header Strict-Transport-Security "max-age=31536000"
}
''', 0o644)
    bootstrap.write_once(args.root / 'staging.yml', f'''services:
  proxy:
    ports: !override ['8080:8080']
    volumes: !override
      - {args.root}/Caddyfile-staging:/etc/caddy/Caddyfile:ro
      - {args.root}/caddy-data:/data
      - {args.root}/caddy-config:/config
''')

    def compose(root, *command, **kwargs):
        return bootstrap.run(['docker', 'compose', '--env-file', str(root / 'compose.env'), '-f', str(root / 'compose.yml'), '-f', str(root / 'staging.yml'), *command], **kwargs)

    bootstrap.compose = compose
    bootstrap.run(['docker', 'pull', image], stdout=subprocess.DEVNULL)
    compose(args.root, 'config', '--quiet')
    key = args.root / 'secrets' / 'backup-signing.key'
    if not key.exists():
        key.write_bytes(secrets.token_bytes(64)); key.chmod(0o600); os.chown(key, 10001, 10001)
    code = """import json,sys,secrets; from pathlib import Path; from datetime import datetime,timezone; from flood.repository import Repository,dump; from flood.auth import create_user
p=json.load(sys.stdin);r=Repository('/data/flood.sqlite3'); assert all(u['username']=='synthetic-staging-admin' for u in r.rows('SELECT username FROM users')), 'Refuse operational user data'
users=r.rows('SELECT id FROM users WHERE username=?',('synthetic-staging-admin',));actor=users[0]['id'] if users else create_user(r,'synthetic-staging-admin','administrator',p['password'])
rows=r.rows('SELECT payload FROM assessment_versions'); assert all(json.loads(x['payload']).get('state_region')=='SYNTHETIC STAGING' for x in rows), 'Refuse operational assessment data'
if not rows:
 payload={'state_region':'SYNTHETIC STAGING','township':'SYNTHETIC STAGING','village':'SYNTHETIC STAGING','observed_at':datetime.now(timezone.utc).isoformat(),'source_reference':'Synthetic infrastructure rehearsal only'};r.submit(payload,dump(payload),actor,'administrator','synthetic-staging')
source=Path('/data/source');source.mkdir(exist_ok=True);(source/'source_profile.json').write_text(dump({'synthetic':True}))
print('EXISTS' if users else 'CREATED')
"""
    password = secrets.token_urlsafe(32)
    result = compose(args.root, 'run', '--rm', '--no-deps', '-T', 'maintenance', 'python', '-c', code,
                     input=json.dumps({'password': password}), capture_output=True)
    if result.stdout.strip() == 'CREATED':
        bootstrap.write_once(args.root / 'synthetic-admin-password', password + '\n')
    compose(args.root, 'up', '-d', 'app', 'backup', 'proxy')
    bootstrap.wait_ready(args.root)
    bootstrap.verify_persistence(args.root)
    for attempt in range(30):
        bundles = list((args.root / 'backups').glob('flood-*.tar.gz'))
        if bundles:
            latest = max(bundles, key=lambda path: path.stat().st_mtime)
            compose(args.root, 'run', '--rm', '--no-deps', '-T', 'maintenance', 'python', '-m', 'flood.recovery', 'inspect', '--path', '/backups/' + latest.name, stdout=subprocess.DEVNULL)
            break
        time.sleep(1)
    else:
        raise ValueError('Scheduled backup worker did not produce a signed bundle')
    receipt = {**bootstrap.RELEASE, 'timestamp': datetime.now(timezone.utc).isoformat(), 'domain': args.domain,
               'host': 'Railway anonymous 60-minute trial', 'filesystem': 'ext4 on temporary VM', 'synthetic_only': True,
               'container_restart': 'PASS', 'container_recreation': 'PASS', 'production_persistence': 'NOT VERIFIED', 'host_reboot': 'NOT TESTED',
               'external_https': 'PENDING', 'offsite_restore': 'PENDING', 'integrations': 'DISABLED'}
    (args.root / 'staging-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
