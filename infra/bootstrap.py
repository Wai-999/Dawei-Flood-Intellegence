#!/usr/bin/env python3
"""Idempotent, pinned single-host deployment. No provider account creation or secrets in arguments."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RELEASE = json.loads((HERE / 'release.json').read_text())


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def write_once(path, content, mode=0o600):
    """Preserve existing private configuration; refuse silent configuration drift."""
    if path.is_symlink():
        raise ValueError('Symlink configuration refused')
    if path.exists():
        if path.read_text() != content:
            raise ValueError(f'Existing configuration differs: {path.name}; review before replacement')
    else:
        with path.open('x') as handle:
            handle.write(content)
    path.chmod(mode)


def validate(root, domain):
    if not root.is_absolute() or not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(root)):
        raise ValueError('Use an absolute directory without spaces or interpolation characters')
    if root == Path('/') or root in {Path('/etc'), Path('/var'), Path('/srv'), Path('/tmp')}:
        raise ValueError('Use a dedicated application directory')
    if '..' in root.parts or any(p.is_symlink() for p in [root, *root.parents]):
        raise ValueError('Symlink or parent traversal refused')
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain):
        raise ValueError('Expected a plain lowercase DNS hostname')


def verify_linux(root):
    if platform.system() != 'Linux' or os.geteuid() != 0:
        raise ValueError('Preparation/deployment requires root on a supported Linux host')
    info = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    distro, version = info.get('ID', '').strip('"'), info.get('VERSION_ID', '').strip('"')
    if (distro, version) not in {('ubuntu', '22.04'), ('ubuntu', '24.04'), ('ubuntu', '26.04'), ('debian', '12'), ('debian', '13')}:
        raise ValueError('Supported: Ubuntu 22.04/24.04/26.04 or Debian 12/13')
    if platform.machine() not in {'x86_64', 'aarch64', 'arm64'}:
        raise ValueError('Supported: AMD64 or ARM64')
    parent = root
    while not parent.exists():
        parent = parent.parent
    filesystem = run(['findmnt', '-n', '-o', 'FSTYPE', '-T', str(parent)], capture_output=True).stdout.strip()
    if filesystem not in {'ext4', 'xfs', 'btrfs'}:
        raise ValueError(f'Require persistent local block filesystem, found {filesystem}')
    if shutil.disk_usage(parent).free < 2 * 1024**3:
        raise ValueError('At least 2 GiB free disk required')
    return distro, info.get('VERSION_CODENAME', '').strip('"')


def install_docker(distro, codename):
    if shutil.which('docker'):
        run(['docker', 'version'], stdout=subprocess.DEVNULL)
        run(['docker', 'compose', 'version'], stdout=subprocess.DEVNULL)
        return
    for package in ('docker.io', 'podman-docker', 'containerd', 'runc'):
        installed = subprocess.run(['dpkg-query', '-W', '-f=${db:Status-Status}', package], capture_output=True, text=True)
        if installed.returncode == 0 and installed.stdout == 'installed':
            raise ValueError('Conflicting container package; preserve host and review installation')
    run(['apt-get', 'update'])
    run(['apt-get', 'install', '-y', 'ca-certificates', 'curl'])
    Path('/etc/apt/keyrings').mkdir(mode=0o755, exist_ok=True)
    run(['curl', '--fail', '--silent', '--show-error', '--proto', '=https', '--max-time', '30',
         f'https://download.docker.com/linux/{distro}/gpg', '-o', '/etc/apt/keyrings/docker.asc'])
    Path('/etc/apt/keyrings/docker.asc').chmod(0o644)
    arch = run(['dpkg', '--print-architecture'], capture_output=True).stdout.strip()
    write_once(Path('/etc/apt/sources.list.d/docker.sources'),
               f'Types: deb\nURIs: https://download.docker.com/linux/{distro}\nSuites: {codename}\nComponents: stable\nArchitectures: {arch}\nSigned-By: /etc/apt/keyrings/docker.asc\n', 0o644)
    run(['apt-get', 'update'])
    run(['apt-get', 'install', '-y', 'docker-ce', 'docker-ce-cli', 'containerd.io', 'docker-buildx-plugin', 'docker-compose-plugin'])
    run(['systemctl', 'enable', '--now', 'docker'])


def prepare(root, domain, image):
    if (root / 'STOP_WRITES').exists():
        raise ValueError('STOP_WRITES incident latch exists; use isolated recovery before restarting')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    for name in ('data', 'backups', 'secrets', 'caddy-data', 'caddy-config', 'evidence', 'encrypted'):
        path = root / name
        if path.is_symlink():
            raise ValueError('Symlink data directory refused')
        path.mkdir(mode=0o700, exist_ok=True)
        path.chmod(0o700)
        if name in {'data', 'backups', 'secrets'}:
            os.chown(path, 10001, 10001)
    runtime = (f'FLOOD_ENV=production\nFLOOD_DOMAIN={domain}\nFLOOD_PUBLIC_ORIGIN=https://{domain}\n'
               'FLOOD_SECURE_COOKIES=1\nFLOOD_TRUSTED_PROXIES=172.29.0.2\nFLOOD_DATABASE=/data/flood.sqlite3\n'
               'FLOOD_SOURCE_DIRECTORY=/data/source\nFLOOD_BACKUP_DIRECTORY=/backups\n'
               'FLOOD_BACKUP_SIGNING_KEY_FILE=/run/secrets/backup-signing.key\n'
               'FLOOD_BACKUP_INTERVAL_SECONDS=3600\nFLOOD_BACKUP_RETENTION_DAYS=30\n')
    write_once(root / 'runtime.env', runtime)
    compose_env = root / 'compose.env'
    if image == 'ARM64-PIN-PENDING' and compose_env.exists():
        current = compose_env.read_text()
        match = re.fullmatch(r'FLOOD_ROOT=' + re.escape(str(root)) + r'\nFLOOD_RELEASE_IMAGE=(sha256:[a-f0-9]{64}|ARM64-PIN-PENDING)\n', current)
        if not match:
            raise ValueError('Existing ARM configuration is not a pinned image ID')
        image = match.group(1)
    write_once(compose_env, f'FLOOD_ROOT={root}\nFLOOD_RELEASE_IMAGE={image}\n')
    write_once(root / 'compose.yml', (HERE / 'compose.yml').read_text())
    write_once(root / 'Caddyfile', (HERE / 'Caddyfile').read_text(), 0o644)
    for name in ('host-monitor.py', 'offsite.py', 'external-probe.py'):
        target = root / name
        write_once(target, (HERE / name).read_text(), 0o700)


def compose(root, *args, **kwargs):
    return run(['docker', 'compose', '--env-file', str(root / 'compose.env'), '-f', str(root / 'compose.yml'), *args], **kwargs)


def release_image(root):
    if platform.machine() == 'x86_64':
        run(['docker', 'pull', RELEASE['amd64_image']])
        return RELEASE['amd64_image']
    # ARM builds must come from the approved commit, never the current moving branch.
    source = root / 'releases' / RELEASE['commit']
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'init', str(source)])
        run(['git', '-C', str(source), 'fetch', '--depth=1', RELEASE['repository'], RELEASE['commit']])
        run(['git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD'])
    if run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture_output=True).stdout.strip() != RELEASE['commit']:
        raise ValueError('Source pin mismatch')
    if run(['git', '-C', str(source), 'status', '--porcelain'], capture_output=True).stdout.strip():
        raise ValueError('Pinned source checkout is dirty')
    tag = f'dawei-pilot:{RELEASE["commit"]}-arm64'
    run(['docker', 'build', '--platform', 'linux/arm64', '--label', f'org.opencontainers.image.revision={RELEASE["commit"]}', '-t', tag, str(source)])
    run(['sh', 'scripts/container-smoke.sh', tag], cwd=source)
    run(['sh', 'scripts/commissioning-smoke.sh', tag], cwd=source)
    return run(['docker', 'image', 'inspect', '--format', '{{.Id}}', tag], capture_output=True).stdout.strip()


def firewall(ssh_cidr):
    if not ssh_cidr:
        peer = os.environ.get('SSH_CONNECTION', '').split()
        if not peer:
            raise ValueError('Firewall needs the connected operator SSH address or --ssh-cidr')
        ssh_cidr = str(ipaddress.ip_network(peer[0] + ('/128' if ':' in peer[0] else '/32')))
    ipaddress.ip_network(ssh_cidr, strict=False)
    run(['apt-get', 'install', '-y', 'ufw'])
    ports = [line.split()[1] for line in run(['sshd', '-T'], capture_output=True).stdout.splitlines() if line.startswith('port ')]
    if not ports:
        raise ValueError('Cannot determine SSH ports; firewall unchanged')
    for port in ports:
        run(['ufw', 'allow', 'from', ssh_cidr, 'to', 'any', 'port', port, 'proto', 'tcp'])
    for port in ('80', '443'):
        run(['ufw', 'allow', port + '/tcp'])
    # Preserve pre-existing rules. Only Caddy publishes Docker ports; UFW does not filter those ports.
    run(['ufw', 'default', 'deny', 'incoming'])
    run(['ufw', 'default', 'allow', 'outgoing'])
    run(['ufw', '--force', 'enable'])


def wait_ready(root):
    for attempt in range(30):
        probe = subprocess.run(['docker', 'compose', '--env-file', str(root / 'compose.env'), '-f', str(root / 'compose.yml'), 'exec', '-T', 'app', 'python', '-m', 'flood.probe'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            return
        time.sleep(1)
    raise ValueError('Readiness failed; preserve data and inspect private host logs')


def verify_persistence(root):
    # A separate infrastructure fixture never fabricates operational assessments.
    fixture = "import sqlite3; c=sqlite3.connect('/data/.persistence-test.sqlite3'); c.execute('CREATE TABLE IF NOT EXISTS proof(value TEXT)'); c.execute('DELETE FROM proof'); c.execute(\"INSERT INTO proof VALUES('persistent-pilot-volume')\"); c.commit()"
    check = "import sqlite3; c=sqlite3.connect('/data/.persistence-test.sqlite3'); assert c.execute('SELECT value FROM proof').fetchone()[0]=='persistent-pilot-volume'"
    compose(root, 'exec', '-T', 'app', 'python', '-c', fixture)
    compose(root, 'restart', 'app', stdout=subprocess.DEVNULL)
    wait_ready(root)
    compose(root, 'exec', '-T', 'app', 'python', '-c', check)
    compose(root, 'up', '-d', '--no-deps', '--force-recreate', 'app', stdout=subprocess.DEVNULL)
    wait_ready(root)
    compose(root, 'exec', '-T', 'app', 'python', '-c', check)


def systemd(root):
    if not Path('/run/systemd/system').exists():
        raise ValueError('Production host must run systemd; sandbox deployment is explicitly separate')
    docker = shutil.which('docker')
    command = f'{docker} compose --env-file {root}/compose.env -f {root}/compose.yml'
    write_once(Path('/etc/systemd/system/dawei-pilot.service'),
               f'[Unit]\nDescription=Dawei pinned pilot\nRequires=docker.service\nAfter=docker.service network-online.target\nConditionPathExists=!{root}/STOP_WRITES\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart={command} up -d app backup proxy\nExecStop={command} stop\n[Install]\nWantedBy=multi-user.target\n', 0o644)
    write_once(Path('/etc/systemd/system/dawei-monitor.service'),
               f'[Unit]\nDescription=Dawei private host health and corruption guard\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 {root}/host-monitor.py --root {root} --apply\nTimeoutStartSec=180\n', 0o644)
    write_once(Path('/etc/systemd/system/dawei-monitor.timer'),
               '[Unit]\nDescription=Dawei bounded health timer\n[Timer]\nOnBootSec=90\nOnUnitActiveSec=60\nPersistent=true\n[Install]\nWantedBy=timers.target\n', 0o644)
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', 'dawei-pilot.service', 'dawei-monitor.timer'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('plan', 'prepare', 'deploy'), default='plan')
    parser.add_argument('--root', type=Path, default=Path('/srv/dawei-flood'))
    parser.add_argument('--domain', default='floodintelligence.duckdns.org')
    parser.add_argument('--allow-install', action='store_true')
    parser.add_argument('--configure-firewall', action='store_true')
    parser.add_argument('--ssh-cidr')
    parser.add_argument('--admin-user', help='Explicit named operator; password generated only on first creation')
    args = parser.parse_args()
    validate(args.root, args.domain)
    if args.admin_user and not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', args.admin_user):
        raise ValueError('Invalid named administrator')
    if args.mode == 'plan':
        print(json.dumps({'state': 'INFRASTRUCTURE-SELECTED', 'domain': args.domain, 'root': str(args.root), **RELEASE,
                          'integrations': 'disabled', 'production_host_provisioned': False}))
        return
    distro, codename = verify_linux(args.root)
    prepare(args.root, args.domain, RELEASE['amd64_image'] if platform.machine() == 'x86_64' else 'ARM64-PIN-PENDING')
    if args.mode == 'prepare':
        print('PREPARED; no containers, firewall, provider account or paid resource changed')
        return
    if not Path('/run/systemd/system').exists():
        raise ValueError('Require systemd production host; preparation remains available in sandboxes')
    if args.allow_install:
        install_docker(distro, codename)
        if platform.machine() == 'aarch64' and not shutil.which('git'):
            run(['apt-get', 'update'])
            run(['apt-get', 'install', '-y', 'git'])
    else:
        run(['docker', 'compose', 'version'], stdout=subprocess.DEVNULL)
    image = release_image(args.root)
    # Replace only the bootstrap-owned ARM pending placeholder, never an operator configuration.
    env = args.root / 'compose.env'
    if 'ARM64-PIN-PENDING' in env.read_text():
        env.write_text(env.read_text().replace('ARM64-PIN-PENDING', image)); env.chmod(0o600)
    elif next(line.split('=', 1)[1] for line in env.read_text().splitlines() if line.startswith('FLOOD_RELEASE_IMAGE=')) != image:
        raise ValueError('Existing image pin differs; preserve host and review release configuration')
    if args.configure_firewall:
        firewall(args.ssh_cidr)
    compose(args.root, 'config', '--quiet')
    key = args.root / 'secrets' / 'backup-signing.key'
    if not key.exists():
        with key.open('xb') as handle:
            handle.write(secrets.token_bytes(64))
        key.chmod(0o600); os.chown(key, 10001, 10001)
    if args.admin_user:
        password = secrets.token_urlsafe(32)
        code = "import json,sys; from flood.repository import Repository; from flood.auth import create_user; p=json.load(sys.stdin); r=Repository('/data/flood.sqlite3'); exists=r.rows('SELECT id FROM users WHERE username=?',(p['user'],)); print('EXISTS' if exists else create_user(r,p['user'],'administrator',p['password']))"
        result = compose(args.root, 'run', '--rm', '--no-deps', '-T', 'maintenance', 'python', '-c', code,
                         input=json.dumps({'user': args.admin_user, 'password': password}), capture_output=True)
        if 'EXISTS' not in result.stdout:
            write_once(args.root / 'initial-admin-password', password + '\n')
            print('Named operator created; initial password is only in the private host file initial-admin-password')
    compose(args.root, 'up', '-d', 'app', 'backup', 'proxy')
    wait_ready(args.root)
    verify_persistence(args.root)
    systemd(args.root)
    digest = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image], capture_output=True).stdout.strip()
    config_hash = hashlib.sha256(b''.join((HERE / n).read_bytes() for n in ('release.json', 'compose.yml', 'Caddyfile', 'bootstrap.py', 'host-monitor.py', 'offsite.py', 'external-probe.py'))).hexdigest()
    receipt = {**RELEASE, 'image': image, 'image_config_digest': digest, 'configuration_sha256': config_hash,
               'deployment_timestamp': datetime.now(timezone.utc).isoformat(), 'container_restart': 'PASS', 'container_recreation': 'PASS',
               'host_reboot': 'NOT TESTED', 'public_https': 'NOT VERIFIED', 'offsite_restore': 'NOT VERIFIED'}
    (args.root / 'deployment-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('DEPLOYED; container persistence verified. External HTTPS, reboot and off-site restore remain separate checks.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'Bootstrap stopped safely: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
