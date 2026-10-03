#!/usr/bin/env python3
"""Bounded DuckDNS update using a private token file. Never print token-bearing URLs."""
import argparse
import ipaddress
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen


def update(parameters):
    for attempt in range(3):
        try:
            with urlopen('https://www.duckdns.org/update?' + urlencode(parameters), timeout=15) as response:
                if response.read(100).strip() == b'OK':
                    return
        except Exception:
            # Exceptions may contain the credential-bearing URL; do not print them.
            pass
        if attempt < 2:
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError('DuckDNS update failed after three bounded attempts; token and request URL redacted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--ipv4')
    parser.add_argument('--ipv6')
    parser.add_argument('--ipv6-only', action='store_true', help='Clear stale A/AAAA then publish only the new IPv6 address')
    args = parser.parse_args()
    if not args.token_file.is_file() or args.token_file.is_symlink() or args.token_file.stat().st_mode & 0o077:
        raise ValueError('Use a private mode-600 token file')
    if args.ipv6_only and (not args.ipv6 or args.ipv4):
        raise ValueError('IPv6-only mode requires --ipv6 and forbids --ipv4')
    if not args.ipv4 and not args.ipv6_only:
        raise ValueError('Supply --ipv4 or explicitly select --ipv6-only')
    parameters = {'domains': 'floodintelligence', 'token': args.token_file.read_text().strip()}
    if args.ipv4:
        ipaddress.IPv4Address(args.ipv4); parameters['ip'] = args.ipv4
    if args.ipv6:
        ipaddress.IPv6Address(args.ipv6); parameters['ipv6'] = args.ipv6
    if not parameters['token']:
        raise ValueError('Token file is empty')
    if args.ipv6_only:
        # DuckDNS clear ignores IP parameters. It must be a separate operation.
        # If publishing fails, retry the same explicit command; do not restore a stale A record.
        update({'domains': 'floodintelligence', 'token': parameters['token'], 'clear': 'true'})
    update(parameters)
    print('DuckDNS update accepted; verify DNS propagation and external HTTPS separately')


if __name__ == '__main__':
    main()
