#!/usr/bin/env python3
"""Bounded DuckDNS update using a private token file. Never print token-bearing URLs."""
import argparse
import ipaddress
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--ipv4', required=True)
    parser.add_argument('--ipv6')
    args = parser.parse_args()
    if not args.token_file.is_file() or args.token_file.is_symlink() or args.token_file.stat().st_mode & 0o077:
        raise ValueError('Use a private mode-600 token file')
    ipaddress.IPv4Address(args.ipv4)
    parameters = {'domains': 'floodintelligence', 'token': args.token_file.read_text().strip(), 'ip': args.ipv4}
    if args.ipv6:
        ipaddress.IPv6Address(args.ipv6); parameters['ipv6'] = args.ipv6
    if not parameters['token']:
        raise ValueError('Token file is empty')
    for attempt in range(3):
        try:
            with urlopen('https://www.duckdns.org/update?' + urlencode(parameters), timeout=15) as response:
                if response.read(100).strip() == b'OK':
                    print('DuckDNS update accepted; verify DNS propagation and external HTTPS separately')
                    return
        except Exception:
            # Exceptions may contain the credential-bearing URL; do not print them.
            pass
        if attempt < 2:
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError('DuckDNS update failed after three bounded attempts; token and request URL redacted')


if __name__ == '__main__':
    main()
