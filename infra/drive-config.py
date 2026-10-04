#!/usr/bin/env python3
"""Prepare a backup-only Drive credential after exact-scope owner consent.

This performs no network requests, authorizes no account, and enables no timer.
Real privacy/quota/upload/download/isolated-restore gates remain separate.
"""
import argparse
import configparser
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import tempfile

SCOPE = 'https://www.googleapis.com/auth/drive.file'
TOKEN_URI = 'https://oauth2.googleapis.com/token'


def private_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Private non-symlink credential or consent receipt required')
    return json.loads(path.read_text())


def scalar(value):
    if not isinstance(value, str) or not value or any(c in value for c in '\r\n\x00'):
        raise ValueError('Invalid credential field; no values are logged')
    return value


def render_config(client, credential, consent, folder_id, now=None):
    now = now or datetime.now(timezone.utc)
    if set(client) != {'installed'} or not isinstance(client['installed'], dict):
        raise ValueError('Owner-authorized desktop client required')
    installed = client['installed']
    if (installed.get('auth_uri') != 'https://accounts.google.com/o/oauth2/auth' or
            installed.get('token_uri') != TOKEN_URI or credential.get('token_uri') != TOKEN_URI):
        raise ValueError('Unexpected OAuth endpoint')
    if (credential.get('scopes') != [SCOPE] or consent.get('requested_scopes') != [SCOPE] or
            consent.get('actual_granted_scopes') != [SCOPE] or
            consent.get('refresh_token_present') is not True):
        raise ValueError('Exact drive.file owner grant and refresh token evidence required')
    client_id, secret = scalar(installed.get('client_id')), scalar(installed.get('client_secret'))
    if credential.get('client_id') != client_id or credential.get('client_secret') != secret:
        raise ValueError('Credential does not match the privately replaced desktop client')
    if not isinstance(folder_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', folder_id):
        raise ValueError('Verified app-owned private folder ID required')
    try:
        expiry = datetime.fromisoformat(scalar(credential.get('expiry')).replace('Z', '+00:00'))
        observed = datetime.fromisoformat(scalar(consent.get('captured_at')).replace('Z', '+00:00'))
        if expiry.tzinfo is None or observed.tzinfo is None or expiry <= now or not 0 <= (now - observed).total_seconds() <= 86400:
            raise ValueError('Stale credential or consent evidence')
    except (TypeError, ValueError) as error:
        raise ValueError('Fresh timestamped consent and unexpired token required') from error
    token = {'access_token': scalar(credential.get('token')), 'token_type': 'Bearer',
             'refresh_token': scalar(credential.get('refresh_token')),
             'expiry': expiry.astimezone(timezone.utc).isoformat()}
    config = configparser.ConfigParser(interpolation=None)
    config['dawei_drive'] = {'type': 'drive', 'client_id': client_id, 'client_secret': secret,
                             'scope': 'drive.file', 'root_folder_id': folder_id,
                             'skip_shortcuts': 'true', 'token': json.dumps(token)}
    output = io.StringIO()
    config.write(output)
    return output.getvalue()


def write_config(root, content):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise ValueError('Non-symlink deployment root required')
    directory = root / 'backup-secrets'
    if directory.is_symlink():
        raise ValueError('Backup credential directory must not be symlinked')
    directory.mkdir(mode=0o700, exist_ok=True)
    if not directory.is_dir() or directory.stat().st_mode & 0o077 or directory.stat().st_uid != os.geteuid():
        raise ValueError('Backup credential directory must be private and operator-owned')
    target = directory / 'drive.conf'
    # Hard-link promotion refuses existing credentials, including broken symlinks.
    # No partially written file is ever exposed as the active configuration.
    with tempfile.NamedTemporaryFile(mode='w', dir=directory, prefix='.drive-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            temporary.chmod(0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--client', type=Path, required=True)
    parser.add_argument('--credential', type=Path, required=True)
    parser.add_argument('--consent-receipt', type=Path, required=True)
    parser.add_argument('--folder-file', type=Path, required=True, help='Private JSON with verified app-owned private folder_id')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError('Install production backup credentials as root')
        folder = private_json(args.folder_file)
        if set(folder) != {'folder_id', 'app_owned', 'private_permissions_verified'} or folder.get('app_owned') is not True or folder.get('private_permissions_verified') is not True:
            raise ValueError('Actual private app-owned folder evidence required')
        content = render_config(private_json(args.client), private_json(args.credential),
                                private_json(args.consent_receipt), folder['folder_id'])
        write_config(args.root, content)
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'prepared': False, 'error_class': type(error).__name__, 'credential_values_logged': False}))
        raise SystemExit(1) from None
    print(json.dumps({'prepared': True, 'scope': 'drive.file', 'credential_values_logged': False,
                      'timer_enabled': False, 'drive_roundtrip_verified': False}))


if __name__ == '__main__':
    main()
