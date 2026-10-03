#!/usr/bin/env python3
"""Private host checks; bounded container recovery and a latched stop on corruption."""
import argparse
from datetime import datetime, timezone
import json
import os
import runpy
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time


def database_status(path):
    if not path.is_file():
        return 'UNAVAILABLE'
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3) as connection:
            result = connection.execute('PRAGMA quick_check').fetchall()
            if result != [('ok',)]:
                return 'CORRUPT'
            connection.execute('SELECT 1').fetchone()
        return 'HEALTHY'
    except sqlite3.DatabaseError as error:
        # Busy/permission/missing-file errors are not evidence of corrupted bytes.
        return 'CORRUPT' if getattr(error, 'sqlite_errorcode', None) in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB} else 'UNAVAILABLE'


def worker_status(path, enabled, now):
    result = {name: 'DISABLED' for name in ('telegram', 'sheets') if name not in enabled}
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3) as connection:
            rows = connection.execute('SELECT key,value,updated_at FROM integration_state').fetchall()
        states = {key: (json.loads(value), updated) for key, value, updated in rows}
        for name in enabled:
            value, updated = states.get(name, ({}, None))
            if not updated:
                result[name] = 'STALE'
            else:
                age = now - datetime.fromisoformat(updated.replace('Z', '+00:00')).timestamp()
                result[name] = 'FAILED' if value.get('status') in {'failed', 'FAILED'} else 'STALE' if age > 300 else 'FRESH'
        value, updated = states.get('backup_worker', ({}, None))
        result['backup_worker'] = 'FAILED' if value.get('status') == 'FAILED' else 'PRESENT' if updated else 'NOT_STARTED'
    except (sqlite3.Error, ValueError, TypeError):
        result['worker_check'] = 'UNAVAILABLE'
    return result


def compose(root, *args):
    return subprocess.run(['docker', 'compose', '--env-file', str(root / 'compose.env'), '-f', str(root / 'compose.yml'), *args],
                          check=True, text=True, capture_output=True, timeout=40)


def preserve_and_stop(root, reason):
    latch = root / 'STOP_WRITES'
    if latch.exists():
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    latch.write_text(json.dumps({'reason': reason, 'time': stamp, 'recovery': 'Preserve evidence; verify trusted signed backup; isolated restore; owner review'}) + '\n')
    latch.chmod(0o600)
    # Stop every process capable of writing; Caddy remains to return an unavailable response.
    compose(root, '--profile', 'telegram', '--profile', 'sheets', 'stop', 'app', 'backup', 'telegram', 'sheets')
    evidence = root / 'evidence' / ('incident-' + stamp)
    evidence.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in ('flood.sqlite3', 'flood.sqlite3-wal', 'flood.sqlite3-shm'):
        path = root / 'data' / name
        if path.is_file():
            shutil.copy2(path, evidence / name)
            (evidence / name).chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Enable bounded recovery and corruption stop')
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve()
    trial = runpy.run_path(str(Path(__file__).with_name('trial_guard.py')))['guard'](root, apply=args.apply)
    if trial['status'] == 'STOP WRITES':
        print(json.dumps({'trial': trial}))
        return 1
    now = time.time()
    database = database_status(root / 'data' / 'flood.sqlite3')
    free = shutil.disk_usage(root).free
    local = list((root / 'backups').glob('flood-*.tar.gz'))
    age = now - max(p.stat().st_mtime for p in local) if local else None
    upload = root / 'offsite-receipt.json'
    offsite_age = now - upload.stat().st_mtime if upload.exists() else None
    enabled_file = root / 'enabled-workers.json'
    enabled = json.loads(enabled_file.read_text()) if enabled_file.exists() else []
    if not isinstance(enabled, list) or any(name not in {'telegram', 'sheets'} for name in enabled):
        raise ValueError('Invalid enabled worker declaration')
    status = {'timestamp': datetime.now(timezone.utc).isoformat(), 'database': database,
              'disk': 'CRITICAL' if free < 128 * 1024**2 else 'LOW' if free < 2 * 1024**3 else 'HEALTHY',
              'backup': 'FRESH' if age is not None and age <= 7200 else 'STALE',
              'offsite': 'FRESH' if offsite_age is not None and offsite_age <= 86400 else 'NOT_VERIFIED_OR_STALE',
              'workers': worker_status(root / 'data' / 'flood.sqlite3', enabled, now),
              'writes_latched': (root / 'STOP_WRITES').exists(), 'containers': 'UNKNOWN'}
    if args.apply and (database == 'CORRUPT' or status['disk'] == 'CRITICAL'):
        preserve_and_stop(root, 'DATABASE_CORRUPTION' if database == 'CORRUPT' else 'LOW_DISK')
        status['writes_latched'] = True
    try:
        data = compose(root, 'ps', '--all', '--format', 'json').stdout.strip()
        rows = json.loads(data) if data.startswith('[') else [json.loads(line) for line in data.splitlines() if line]
        states = {row['Service']: row for row in rows}
        wanted = ['app', 'backup', 'proxy', *enabled]
        unhealthy = [name for name in wanted if states.get(name, {}).get('State') != 'running' or states.get(name, {}).get('Health') == 'unhealthy']
        status['containers'] = 'DEGRADED' if unhealthy else 'HEALTHY'
        statefile = root / 'recovery-attempts.json'
        previous = json.loads(statefile.read_text()) if statefile.exists() else {'started': now, 'attempts': 0}
        if now - previous['started'] > 1800:
            previous = {'started': now, 'attempts': 0}
        if args.apply and unhealthy and database == 'HEALTHY' and free >= 128 * 1024**2 and not (root / 'STOP_WRITES').exists() and previous['attempts'] < 3:
            # One recovery attempt per timer run; at most three per 30 minutes.
            previous['attempts'] += 1
            statefile.write_text(json.dumps(previous) + '\n')
            time.sleep(2 ** (previous['attempts'] - 1))
            for name in unhealthy:
                if states.get(name, {}).get('State') == 'running':
                    compose(root, 'restart', name)
                else:
                    compose(root, '--profile', 'telegram', '--profile', 'sheets', 'up', '-d', '--no-deps', name)
            status['recovery_attempt'] = previous['attempts']
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        status['containers'] = 'CHECK_FAILED'
    (root / 'health-status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status))
    return 1 if database != 'HEALTHY' or status['disk'] != 'HEALTHY' or status['containers'] != 'HEALTHY' or status['backup'] != 'FRESH' or status['offsite'] != 'FRESH' else 0


if __name__ == '__main__':
    raise SystemExit(main())
