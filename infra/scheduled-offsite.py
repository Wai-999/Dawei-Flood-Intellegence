#!/usr/bin/env python3
"""Bounded private encrypted upload timer; recovery identities remain off the host."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess


def settings(root):
    if root.is_symlink() or (root / 'secrets').is_symlink():
        raise ValueError('Deployment and secret directories must not be symlinked')
    config = root / 'secrets' / 'offsite.json'
    if config.is_symlink() or not config.is_file() or config.stat().st_mode & 0o077:
        raise ValueError('Private off-site configuration required')
    value = json.loads(config.read_text())
    if set(value) != {'destination', 'recipient', 'max_remote_bytes'}:
        raise ValueError('Only destination, public recipient and capacity are permitted')
    if not isinstance(value['destination'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+:[A-Za-z0-9_./-]+', value['destination']) or '..' in value['destination']:
        raise ValueError('Dedicated private remote prefix required')
    if not isinstance(value['recipient'], str) or not re.fullmatch(r'age1[0-9a-z]{50,100}', value['recipient']):
        raise ValueError('Public age recipient required; never install the identity')
    limit = value['max_remote_bytes']
    if type(limit) is not int or not 1 <= limit <= 4_000_000_000:
        raise ValueError('Conservative private storage limit required')
    return value


def unit_text(root):
    service = f'''[Unit]
Description=Dawei signed client-encrypted off-site upload
After=network-online.target docker.service
ConditionPathExists=!{root}/STOP_WRITES
[Service]
Type=oneshot
UMask=0077
Nice=10
ExecStart=/usr/bin/python3 {root}/scheduled-offsite.py --root {root}
TimeoutStartSec=900
'''
    timer = '''[Unit]
Description=Dawei bounded hourly encrypted upload
[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
RandomizedDelaySec=120
Persistent=true
[Install]
WantedBy=timers.target
'''
    return service, timer


def upload(root):
    value = settings(root)
    if (root / 'STOP_WRITES').exists():
        raise ValueError('STOP_WRITES remains latched; no automatic recovery')
    trial = runpy.run_path(str(root / 'trial_guard.py'))['guard'](root, apply=False)
    if trial['status'] == 'STOP WRITES':
        raise ValueError('Trial safety evidence is stale or invalid')
    if shutil.disk_usage(root).free < 2 * 1024**3:
        raise ValueError('Insufficient disk headroom; preserve backups')
    bundles = sorted((root / 'backups').glob('flood-*.tar.gz'), key=lambda p: p.stat().st_mtime)
    if not bundles or datetime.now(timezone.utc).timestamp() - bundles[-1].stat().st_mtime > 7200:
        raise ValueError('Fresh signed local backup required')
    recipient = root / 'secrets' / 'offsite-recipient.txt'
    if recipient.is_symlink():
        raise ValueError('Recipient path must not be symlinked')
    if recipient.exists() and recipient.read_text().strip() != value['recipient']:
        raise ValueError('Recovery recipient changed; owner custody review required')
    if not recipient.exists():
        with recipient.open('x') as stream:
            stream.write(value['recipient'] + '\n')
        recipient.chmod(0o600)
    result = subprocess.run(['/usr/bin/python3', str(root / 'offsite.py'), 'push', '--root', str(root),
                             '--destination', value['destination'], '--recipient-file', str(recipient),
                             '--max-remote-bytes', str(value['max_remote_bytes'])],
                            capture_output=True, text=True, timeout=850)
    evidence = root / 'evidence' / 'scheduled-offsite-operation.json'
    evidence.write_text(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(),
                                   'exit_code': result.returncode, 'stdout': result.stdout,
                                   'stderr': result.stderr}, indent=2) + '\n')
    evidence.chmod(0o600)
    if result.returncode:
        raise ValueError('Encrypted upload failed; private evidence retained and next hourly retry bounded')
    receipt = json.loads((root / 'offsite-receipt.json').read_text())
    if receipt.get('download_hash') != 'PASS' or receipt.get('encrypted_before_upload') is not True:
        raise ValueError('Actual encrypted round trip receipt required')
    return {'status': 'UPLOAD_DOWNLOAD_VERIFIED', 'isolated_restore': 'SEPARATE OWNER-SIDE GATE',
            'independent_of_trial_account': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.absolute()
    if root.is_symlink() or root.resolve() != root or not re.fullmatch(r'/srv/[A-Za-z0-9_-]+', str(root)):
        raise ValueError('Existing dedicated /srv deployment root required')
    settings(root)
    if args.install:
        if os.geteuid() != 0 or not Path('/run/systemd/system').exists():
            raise ValueError('Root on a supported systemd host required')
        for name, content in zip(('dawei-offsite.service', 'dawei-offsite.timer'), unit_text(root)):
            path = Path('/etc/systemd/system') / name
            if path.is_symlink() or (path.exists() and path.read_text() != content):
                raise ValueError('Existing different unit preserved; review before replacement')
            if not path.exists():
                path.write_text(content); path.chmod(0o644)
        subprocess.run(['systemctl', 'daemon-reload'], check=True, capture_output=True)
        subprocess.run(['systemctl', 'enable', '--now', 'dawei-offsite.timer'], check=True, capture_output=True)
        print(json.dumps({'timer': 'CONFIGURED', 'actual_upload': 'NOT YET TESTED'}))
    else:
        with (root / 'scheduled-offsite.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(json.dumps(upload(root)))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError):
        print(json.dumps({'status': 'FAILED', 'detail': 'Private host evidence retained; no data deleted or restored'}))
        raise SystemExit(1)
