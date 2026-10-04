#!/usr/bin/env python3
"""Test production Host routing over trusted fixture TLS and private Docker ports."""
import http.client
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time
import uuid


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90).stdout.strip()


def request(port, host, *, context=None, forwarded=False):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    if context:
        connection.sock = context.wrap_socket(socket.create_connection(('127.0.0.1', port), timeout=5), server_hostname='flood.example')
    headers = {'Host': host}
    if forwarded:
        headers['X-Forwarded-Host'] = 'flood.example'
    try:
        connection.request('GET', '/health/ready', headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def main():
    here = Path(__file__).resolve().parent
    release = json.loads((here / 'release.json').read_text())
    suffix = uuid.uuid4().hex[:12]
    network, backend, proxy = ['dawei-host-' + suffix + '-' + name for name in ('network', 'app', 'proxy')]
    created = []
    with tempfile.TemporaryDirectory(prefix='dawei-caddy-host-') as temporary:
        folder = Path(temporary)
        config = (here / 'Caddyfile').read_text().replace('{$FLOOD_DOMAIN} {', '{$FLOOD_DOMAIN} {\n    tls internal', 1)
        (folder / 'Caddyfile').write_text(config)
        server = "from http.server import BaseHTTPRequestHandler,HTTPServer;import json\nclass Handler(BaseHTTPRequestHandler):\n def do_GET(self):\n  self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'status':'HEALTHY'}).encode())\nHTTPServer(('0.0.0.0',8000),Handler).serve_forever()"
        try:
            # Docker omits published ports on an internal-only bridge. These
            # fixture ports bind solely to loopback; neither fixture has data.
            run('docker', 'network', 'create', network)
            created.append(('network', network))
            run('docker', 'run', '-d', '--platform', 'linux/amd64', '--name', backend, '--network', network, '--network-alias', 'app',
                '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                release['amd64_image'], 'python', '-c', server)
            created.append(('container', backend))
            run('docker', 'run', '-d', '--name', proxy, '--network', network,
                '-p', '127.0.0.1::443', '-p', '127.0.0.1::80',
                '--mount', 'type=bind,source=' + str(folder / 'Caddyfile') + ',target=/etc/caddy/Caddyfile,readonly',
                '-e', 'FLOOD_DOMAIN=flood.example', release['caddy_image'])
            created.append(('container', proxy))
            https_port = int(run('docker', 'port', proxy, '443/tcp').rsplit(':', 1)[1])
            http_port = int(run('docker', 'port', proxy, '80/tcp').rsplit(':', 1)[1])
            ca = folder / 'root.crt'
            for attempt in range(30):
                result = subprocess.run(['docker', 'cp', proxy + ':/data/caddy/pki/authorities/local/root.crt', str(ca)], capture_output=True, timeout=10)
                if result.returncode == 0:
                    break
                time.sleep(1)
            assert ca.is_file(), 'Fixture CA was not created'
            context = ssl.create_default_context(cafile=str(ca))
            for attempt in range(30):
                try:
                    status, _, body = request(https_port, 'flood.example', context=context)
                    if status == 200 and json.loads(body) == {'status': 'HEALTHY'}:
                        break
                except (OSError, ValueError, ssl.SSLError):
                    pass
                time.sleep(1)
            else:
                raise AssertionError('Valid Host did not reach the private backend')
            assert request(https_port, 'untrusted.example', context=context, forwarded=True)[0] == 421
            status, headers, _ = request(http_port, 'flood.example')
            assert status in {301, 302, 307, 308} and headers.get('Location') == 'https://flood.example/health/ready'
            assert request(http_port, 'untrusted.example', forwarded=True)[0] == 421
            print('PASS: trusted fixture TLS, valid Host proxy, HTTP redirect, HTTP/HTTPS unknown-Host rejection, forwarded-Host spoof rejection')
        finally:
            for kind, name in reversed(created):
                subprocess.run(['docker', kind, 'rm', *(['-f'] if kind == 'container' else []), name], capture_output=True, timeout=30, check=False)


if __name__ == '__main__':
    main()
