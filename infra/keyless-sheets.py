#!/usr/bin/env python3
"""Keyless authentication adapter for the immutable pilot's Sheets projection."""
import argparse
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

if Path('/app/flood').is_dir():
    sys.path.insert(0, '/app')
from flood.integrations import http_json, sync_sheets, state
from flood.domain import DomainError, now
from flood.cli import database_path
from flood.repository import Repository, dump
from flood.workers import worker_lock

METADATA = 'http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/'
IAM = 'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/'
SCOPE = 'https://www.googleapis.com/auth/spreadsheets'
EMAIL = r'[a-z][a-z0-9-]{4,62}@[a-z][a-z0-9-]{4,62}\.iam\.gserviceaccount\.com'
TOKEN = r'[A-Za-z0-9._~+/-]+=*'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DomainError('Credential endpoint redirect refused')


def configuration(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Workload configuration must be a private regular file')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) != {'caller_service_account', 'service_account', 'sheet_id'}:
        raise ValueError('Unsupported workload configuration; credentials must not be embedded')
    if any(not re.fullmatch(EMAIL, value.get(key, '')) for key in ('caller_service_account', 'service_account')):
        raise ValueError('Invalid workload identity')
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,100}', value.get('sheet_id', '')):
        raise ValueError('Invalid projection destination')
    if value['caller_service_account'] == value['service_account']:
        raise ValueError('Use the separately scoped projection identity')
    return value


def credential_request(url, data=None, headers=None):
    parsed = urlsplit(url)
    metadata = url in {METADATA + 'email', METADATA + 'token'}
    if metadata:
        if data is not None or headers != {'Metadata-Flavor': 'Google'}:
            raise DomainError('Invalid metadata request')
    elif not (parsed.scheme == 'https' and parsed.hostname == 'iamcredentials.googleapis.com'
              and parsed.port in {None, 443} and not parsed.username and not parsed.password
              and not parsed.query and not parsed.fragment and url.startswith(IAM)
              and url.endswith(':generateAccessToken')):
        raise DomainError('Untrusted credential endpoint')
    encoded = None if data is None else json.dumps(data).encode()
    request = Request(url, data=encoded, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        # Link-local metadata and OAuth credentials must never pass through an
        # ambient proxy or follow a redirect. HTTPS uses the image's trusted CA.
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=20) as response:
            if metadata and response.headers.get('Metadata-Flavor') != 'Google':
                raise DomainError('Untrusted metadata response')
            body = response.read(65537)
            if len(body) > 65536:
                raise DomainError('Oversized credential response')
            return {'email': body.decode().strip()} if url == METADATA + 'email' else json.loads(body)
    except HTTPError as error:
        raise DomainError('Workload credential HTTP ' + str(error.code)) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise DomainError('Workload credential transport failed') from None


class WorkloadToken:
    def __init__(self, path, request=credential_request, clock=time.time):
        self.path = Path(path)
        self.config = configuration(self.path)
        self.request, self.clock = request, clock
        self.token, self.expiry = None, 0

    def __call__(self, path):
        if Path(path) != self.path:
            raise DomainError('Unexpected workload configuration path')
        if self.token and self.expiry - self.clock() > 60:
            return self.token
        identity = self.request(METADATA + 'email', headers={'Metadata-Flavor': 'Google'})
        if identity.get('email') != self.config['caller_service_account']:
            raise DomainError('Unexpected VM workload identity')
        source = self.request(METADATA + 'token', headers={'Metadata-Flavor': 'Google'})
        source_token = source.get('access_token', '')
        if not isinstance(source_token, str) or not re.fullmatch(TOKEN, source_token) or len(source_token) > 8192:
            raise DomainError('Invalid workload token')
        target = IAM + quote(self.config['service_account'], safe='') + ':generateAccessToken'
        result = self.request(target, {'scope': [SCOPE], 'lifetime': '1800s'},
                              {'Authorization': 'Bearer ' + source_token})
        token = result.get('accessToken', '')
        try:
            expires = datetime.fromisoformat(result.get('expireTime', '').replace('Z', '+00:00'))
            if expires.tzinfo is None:
                raise ValueError('Missing expiry timezone')
            expiry = expires.timestamp()
        except (TypeError, ValueError):
            raise DomainError('Invalid short-lived projection expiry') from None
        remaining = expiry - self.clock()
        if (not isinstance(token, str) or not re.fullmatch(TOKEN, token) or len(token) > 8192
                or not 120 <= remaining <= 1900):
            raise DomainError('Invalid short-lived projection token')
        self.token, self.expiry = token, expiry
        return token


class ProjectionClient:
    """One authorized Sheet; at most ten reads and ten writes per minute."""
    def __init__(self, sheet, client=http_json, clock=time.monotonic, sleep=time.sleep):
        self.base = 'https://sheets.googleapis.com/v4/spreadsheets/' + sheet
        self.client, self.clock, self.sleep = client, clock, sleep
        self.windows = {'read': deque(), 'write': deque()}

    def __call__(self, url, data=None, headers=None):
        if not (url == self.base or any(url.startswith(self.base + suffix) for suffix in ('?', '/', ':'))):
            raise DomainError('Unexpected projection destination')
        window = self.windows['read' if data is None else 'write']
        current = self.clock()
        while window and current - window[0] >= 60:
            window.popleft()
        if len(window) >= 10:
            self.sleep(max(0, 60 - (current - window[0])) + 0.01)
            current = self.clock()
            while window and current - window[0] >= 60:
                window.popleft()
        window.append(current)
        return self.client(url, data, headers)


def run(repo, token, client, once=False, sleep=time.sleep):
    failures = 0
    while True:
        try:
            result = sync_sheets(repo, client=client, token_provider=token)
            if result['status'] == 'no_pending_jobs':
                state(repo, 'sheets', {'status': 'idle', 'time': now()})
            failures = 0
            print(dump({'integration': 'sheets', 'status': result['status']}), flush=True)
            if once:
                return 0
            sleep(30)
        except Exception:
            # Exception messages may contain URLs, identity details or tokens.
            state(repo, 'sheets', {'status': 'failed', 'error': 'KEYLESS_PROJECTION_FAILED'})
            failures += 1
            print(dump({'integration': 'sheets', 'error': 'KEYLESS_PROJECTION_FAILED', 'attempt': failures}), flush=True)
            if once or failures >= 8:
                return 1
            sleep(min(60, 2 ** failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--probe', action='store_true', help='Read authorized projection metadata without writing')
    parser.add_argument('--ipv6', action='store_true', help='Require IPv6 for fixed provider endpoints on an IPv6-only host')
    args = parser.parse_args()
    if args.ipv6:
        from provider_ipv6 import install
        install()
    token = WorkloadToken(args.config)
    sheet = token.config['sheet_id']
    client = ProjectionClient(sheet)
    if args.probe:
        metadata = client(client.base + '?fields=spreadsheetId,sheets.properties',
                          headers={'Authorization': 'Bearer ' + token(args.config)})
        if metadata.get('spreadsheetId') != sheet:
            raise DomainError('Projection read verification failed')
        print('{"projection_access":"TESTED","credential_mode":"SHORT_LIVED_WORKLOAD"}')
        return 0
    os.environ['GOOGLE_SERVICE_ACCOUNT_FILE'] = str(args.config)
    os.environ['GOOGLE_SHEET_ID'] = sheet
    repo = Repository(database_path())
    with worker_lock(repo, 'sheets'):
        return run(repo, token, client, once=args.once)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (DomainError, ValueError, OSError):
        print('{"integration":"sheets","error":"KEYLESS_CONFIGURATION_OR_AUTHENTICATION_FAILED"}', flush=True)
        raise SystemExit(1) from None
