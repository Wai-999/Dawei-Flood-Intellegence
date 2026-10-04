#!/usr/bin/env python3
"""Exercise the ingress template against a trusted private TLS fixture, never disaster data."""
import http.client
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid


def main():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('host_fixture', here / 'rehearse-caddy-host.py')
    fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    run = fixture.run
    release = json.loads((here / 'release.json').read_text())
    prefix = 'dawei-bridge-' + uuid.uuid4().hex[:12]
    network, backend, tls, bridge = [prefix + '-' + name for name in ('network', 'echo', 'tls', 'ingress')]
    created = []
    with tempfile.TemporaryDirectory(prefix='dawei-bridge-') as temporary:
        folder = Path(temporary)
        echo = "from http.server import BaseHTTPRequestHandler,HTTPServer;import json\nclass H(BaseHTTPRequestHandler):\n def do_GET(self):\n  self.send_response(200);self.end_headers();self.wfile.write(json.dumps(dict(self.headers)).encode())\nHTTPServer(('0.0.0.0',8000),H).serve_forever()"
        (folder / 'backend').write_text('{\n    admin off\n}\nflood.example {\n    tls internal\n    reverse_proxy echo:8000\n}\n')
        (folder / 'bridge').write_text((here / 'cloud-run-bridge.Caddyfile').read_text())
        try:
            run('docker', 'network', 'create', network); created.append(('network', network))
            run('docker', 'run', '-d', '--platform', 'linux/amd64', '--name', backend, '--network', network, '--network-alias', 'echo',
                '--read-only', '--cap-drop', 'ALL', release['amd64_image'], 'python', '-c', echo)
            created.append(('container', backend))
            run('docker', 'run', '-d', '--name', tls, '--network', network, '--network-alias', 'upstream',
                '--mount', 'type=bind,source=' + str(folder / 'backend') + ',target=/etc/caddy/Caddyfile,readonly', release['caddy_image'])
            created.append(('container', tls))
            ca = folder / 'root.crt'
            for _ in range(30):
                result = subprocess.run(['docker', 'cp', tls + ':/data/caddy/pki/authorities/local/root.crt', str(ca)], capture_output=True, timeout=10)
                if result.returncode == 0: break
                time.sleep(1)
            assert ca.is_file(), 'Fixture CA missing'
            run('docker', 'run', '-d', '--name', bridge, '--network', network, '-p', '127.0.0.1::8080',
                '--mount', 'type=bind,source=' + str(folder / 'bridge') + ',target=/etc/caddy/Caddyfile,readonly',
                '--mount', 'type=bind,source=' + str(ca) + ',target=/fixture-root.crt,readonly',
                '-e', 'SSL_CERT_FILE=/fixture-root.crt', '-e', 'FLOOD_BRIDGE_HOST=bridge.example',
                '-e', 'FLOOD_DOMAIN=flood.example', '-e', 'FLOOD_PRIVATE_UPSTREAM=upstream', release['caddy_image'])
            created.append(('container', bridge))
            port = int(run('docker', 'port', bridge, '8080/tcp').rsplit(':', 1)[1])

            def request(host='bridge.example', origin=None, spoof=False):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                headers = {'Host': host}
                if origin: headers['Origin'] = origin
                if spoof: headers.update({'Forwarded': 'host=evil.example;proto=http', 'X-Forwarded-Host': 'evil.example', 'X-Forwarded-Proto': 'http'})
                connection.request('GET', '/', headers=headers); response = connection.getresponse()
                result = response.status, dict(response.getheaders()), response.read(); connection.close(); return result

            for _ in range(30):
                try:
                    if request()[0] == 200: break
                except OSError: pass
                time.sleep(1)
            else: raise AssertionError('Trusted upstream TLS did not become ready')
            status, headers, body = request(origin='https://bridge.example', spoof=True)
            echoed = json.loads(body)
            assert status == 200 and 'max-age=31536000' in headers['Strict-Transport-Security']
            assert echoed['Host'] == 'flood.example' and echoed['Origin'] == 'https://flood.example'
            assert echoed['X-Forwarded-Proto'] == 'https' and echoed['X-Forwarded-Host'] == 'flood.example'
            assert 'Forwarded' not in echoed
            assert request(origin='https://evil.example')[0] == 403
            assert request(host='evil.example', spoof=True)[0] == 421
            assert request(origin='http://bridge.example')[0] == 403
            print('PASS: trusted private TLS, exact origin mapping, foreign origin/Host rejection, spoofed forwarding removal, HSTS')
        finally:
            for kind, name in reversed(created):
                subprocess.run(['docker', kind, 'rm', *(['-f'] if kind == 'container' else []), name], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
