#!/usr/bin/env python3
"""External DNS/TLS/HTTP verification. No credentials, cookies or report content collected."""
import argparse
from datetime import datetime, timezone
import http.client
import json
import socket
import ssl
import sys


def probe(host):
    result = {'hostname': host, 'time': datetime.now(timezone.utc).isoformat(), 'checks': {}}
    checks = result['checks']
    result['addresses'] = sorted({row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    checks['dns'] = bool(result['addresses'])
    with socket.create_connection((host, 443), timeout=10) as sock:
        with ssl.create_default_context().wrap_socket(sock, server_hostname=host) as tls:
            certificate = tls.getpeercert()
            result['certificate_expires'] = certificate['notAfter']
            checks['trusted_hostname_certificate'] = True
            checks['tls_expiry_over_7_days'] = ssl.cert_time_to_seconds(certificate['notAfter']) - datetime.now(timezone.utc).timestamp() > 7 * 86400
    connection = http.client.HTTPConnection(host, timeout=10)
    connection.request('GET', '/health/ready')
    response = connection.getresponse()
    checks['http_redirect'] = response.status in {301, 302, 307, 308} and response.getheader('Location', '').startswith('https://' + host + '/')
    connection.close()
    for path, name, expected in [('/health/live', 'liveness', 200), ('/health/ready', 'readiness', 200), ('/api/v1/health', 'anonymous_api_rejected', 401)]:
        connection = http.client.HTTPSConnection(host, timeout=10, context=ssl.create_default_context())
        connection.request('GET', path)
        response = connection.getresponse()
        body = response.read(2048)
        if name in {'liveness', 'readiness'}:
            try:
                app_health = json.loads(body) == {'status': 'HEALTHY'}
            except (ValueError, UnicodeError):
                app_health = False
            checks[name] = response.status == expected and app_health
        else:
            checks[name] = response.status == expected
        checks['hsts'] = response.getheader('Strict-Transport-Security', '').startswith('max-age=31536000')
        connection.close()
    connection = http.client.HTTPSConnection(host, timeout=10, context=ssl.create_default_context())
    connection.request('GET', '/health/ready', headers={'Host': 'untrusted.example', 'X-Forwarded-Host': host})
    response = connection.getresponse()
    checks['untrusted_host_rejected'] = response.status in {400, 403, 404, 421}
    connection.close()
    result['pass'] = all(checks.values())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hostname', default='floodintelligence.duckdns.org')
    args = parser.parse_args()
    try:
        result = probe(args.hostname)
    except (OSError, ssl.SSLError, http.client.HTTPException) as error:
        result = {'hostname': args.hostname, 'pass': False, 'error_type': type(error).__name__}
    print(json.dumps(result, indent=2))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
