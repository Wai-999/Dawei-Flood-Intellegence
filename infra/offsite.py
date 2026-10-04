#!/usr/bin/env python3
"""Encrypt signed bundles before upload; retrieve and verify into a new isolated restore path."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, capture_output=True, timeout=240, **kwargs)


def private_file(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError('Required private file missing, symlinked or accessible to group/others')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def compose(root, *args):
    return run(['docker', 'compose', '--env-file', str(root / 'compose.env'), '-f', str(root / 'compose.yml'), *args])


def rclone(root, *args, config=None):
    if config is None:
        config = root / 'secrets' / 'rclone.conf'
    else:
        config = Path(config).absolute()
        directory = root / 'backup-secrets'
        if (root.is_symlink() or directory.is_symlink() or
                config != directory / 'drive.conf' or
                not directory.is_dir() or directory.stat().st_mode & 0o077 or
                directory.stat().st_uid != os.geteuid()):
            raise ValueError('Drive credentials require a private backup-only directory')
    private_file(config)
    if config.parent.name == 'backup-secrets' and config.stat().st_uid != os.geteuid():
        raise ValueError('Backup credentials must be operator-owned')
    return run(['rclone', '--config', str(config), '--retries', '3', '--low-level-retries', '3', '--retries-sleep', '5s', '--log-level', 'ERROR', *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('push', 'restore'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--destination', required=True, help='Owner-authorized PRIVATE rclone remote:bucket/prefix')
    parser.add_argument('--recipient-file', type=Path)
    parser.add_argument('--identity-file', type=Path, help='Separately trusted recovery identity, not stored alongside remote backups')
    parser.add_argument('--object', help='Ciphertext basename recorded by push')
    parser.add_argument('--output', type=Path, help='New isolated restore path below root/evidence')
    parser.add_argument('--max-remote-bytes', type=int, default=8 * 1024**3)
    parser.add_argument('--rclone-config', type=Path, help='Optional private root/backup-secrets/drive.conf; never mount into application services')
    args = parser.parse_args()
    os.umask(0o077)
    if args.rclone_config and (args.root.is_symlink() or args.root.absolute() != args.root.resolve()):
        raise ValueError('Explicit backup credentials require a non-symlink deployment root')
    root = args.root.resolve()
    def transfer(*command):
        return rclone(root, *command, config=args.rclone_config)
    if not re.fullmatch(r'[A-Za-z0-9_-]+:[A-Za-z0-9_./-]+', args.destination) or '..' in args.destination:
        raise ValueError('Use a configured private remote and dedicated prefix; no public URL or credential arguments')
    root.joinpath('encrypted').mkdir(mode=0o700, exist_ok=True)
    with (root / 'offsite.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'push':
            if not args.recipient_file:
                raise ValueError('Public age recipient file required; escrow private identity separately first')
            recipient = args.recipient_file.read_text().strip()
            if not re.fullmatch(r'age1[0-9a-z]{50,100}', recipient):
                raise ValueError('Expected age X25519 public recipient')
            bundles = sorted(root.joinpath('backups').glob('flood-*.tar.gz'), key=lambda p: p.stat().st_mtime)
            if not bundles:
                raise ValueError('No signed backup available')
            bundle = bundles[-1]
            private_file(bundle)
            compose(root, 'run', '--rm', '--no-deps', '-T', 'maintenance', 'python', '-m', 'flood.recovery', 'inspect', '--path', '/backups/' + bundle.name)
            with tempfile.TemporaryDirectory(prefix='encrypt-', dir=root / 'encrypted') as temporary:
                cipher = Path(temporary) / 'bundle.age'
                run(['age', '--recipient', recipient, '--output', str(cipher), str(bundle)])
                digest = sha256(cipher)
                name = bundle.name + '.' + digest[:16] + '.age'
                current = json.loads(transfer('size', '--json', args.destination).stdout)['bytes']
                if current + cipher.stat().st_size > args.max_remote_bytes:
                    raise ValueError('Off-site capacity guard reached; preserve data and obtain owner retention decision')
                remote = args.destination.rstrip('/') + '/' + name
                transfer('copyto', str(cipher), remote)
                downloaded = Path(temporary) / 'downloaded.age'
                transfer('copyto', remote, str(downloaded))
                if sha256(downloaded) != digest:
                    raise ValueError('Downloaded ciphertext differs; recovery NOT verified')
                shutil.copy2(cipher, root / 'encrypted' / name)
            receipt = {'timestamp': datetime.now(timezone.utc).isoformat(), 'object': name, 'sha256': digest,
                       'encrypted_before_upload': True, 'download_hash': 'PASS', 'restore': 'NOT VERIFIED', 'retention': 'NO AUTOMATIC OFFSITE DELETION'}
            root.joinpath('offsite-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
            print(json.dumps(receipt))
        else:
            if not args.identity_file or not args.object or not args.output:
                raise ValueError('Trusted identity, recorded object and new isolated output required')
            private_file(args.identity_file)
            if not re.fullmatch(r'flood-[A-Za-z0-9_.-]+\.tar\.gz\.[a-f0-9]{16}\.age', args.object):
                raise ValueError('Expected recorded ciphertext basename')
            output = args.output.absolute()
            if output.exists() or output.is_symlink() or not output.parent.resolve().is_relative_to(root / 'evidence'):
                raise ValueError('Restore must target a new directory below private evidence')
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='restore-download-', dir=root / 'encrypted') as temporary:
                cipher, bundle = Path(temporary) / 'bundle.age', Path(temporary) / 'bundle.tar.gz'
                transfer('copyto', args.destination.rstrip('/') + '/' + args.object, str(cipher))
                digest = sha256(cipher)
                if digest[:16] != args.object.split('.')[-2]:
                    raise ValueError('Ciphertext checksum mismatch')
                run(['age', '--decrypt', '--identity', str(args.identity_file), '--output', str(bundle), str(cipher)])
                # Trusted signing key comes from the host's separately provisioned private secret mount.
                bundle.chmod(0o600); os.chown(bundle, 10001, 10001)
                os.chmod(temporary, 0o700); os.chown(temporary, 10001, 10001)
                os.chown(output.parent, 10001, 10001)
                image = next(line.split('=', 1)[1] for line in (root / 'compose.env').read_text().splitlines() if line.startswith('FLOOD_RELEASE_IMAGE='))
                run(['docker', 'run', '--rm', '--read-only', '--tmpfs', '/tmp:size=32m,mode=1777', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                     '--mount', f'type=bind,source={root}/secrets,target=/run/secrets,readonly',
                     '--mount', f'type=bind,source={temporary},target=/incoming,readonly',
                     '--mount', f'type=bind,source={output.parent},target=/restore',
                     '-e', 'FLOOD_ENV=production', '-e', 'FLOOD_BACKUP_SIGNING_KEY_FILE=/run/secrets/backup-signing.key', image,
                     'python', '-m', 'flood.recovery', 'restore', '--path', '/incoming/bundle.tar.gz', '--output', '/restore/' + output.name])
            receipt = {'timestamp': datetime.now(timezone.utc).isoformat(), 'object': args.object, 'decrypt': 'PASS',
                       'signature_integrity_foreign_keys_source_checks': 'PASS', 'isolated_restore': str(output), 'session_revocation': 'REQUIRED BEFORE TRAFFIC'}
            root.joinpath('restore-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
            print(json.dumps(receipt))


if __name__ == '__main__':
    main()
