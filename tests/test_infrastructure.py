import hashlib
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone


def module(name):
    path = Path(__file__).resolve().parents[1] / 'infra' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


bootstrap = module('bootstrap')
monitor = module('host-monitor')
offsite = module('offsite')


class InfrastructureTests(unittest.TestCase):
    def test_plan_has_immutable_pilot_source_and_image(self):
        release = bootstrap.RELEASE
        self.assertEqual(release['commit'], 'c05aba604a9827a3f5cc55f5fc8ba478e9ae54dc')
        self.assertEqual(release['schema_version'], 2)
        self.assertIn('@sha256:', release['amd64_image'])

    def test_configuration_preserves_existing_credentials_and_refuses_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'private.env'
            bootstrap.write_once(path, 'PRIVATE=unchanged\n')
            bootstrap.write_once(path, 'PRIVATE=unchanged\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                bootstrap.write_once(path, 'PRIVATE=replaced\n')
            self.assertEqual(path.read_text(), 'PRIVATE=unchanged\n')

    def test_rejects_configuration_injection_and_shared_roots(self):
        for domain in ['https://flood.example', 'flood.example\nFLOOD_ENV=preview', 'flood.example:443', '-flood.example']:
            with self.assertRaises(ValueError):
                bootstrap.validate(Path('/srv/dawei-test'), domain)
        for root in ['/', '/srv', '/tmp', '/srv/a/../b', '/srv/${SECRET}']:
            with self.assertRaises(ValueError):
                bootstrap.validate(Path(root), 'flood.example')

    def test_configuration_symlink_does_not_overwrite_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'target'
            target.write_text('preserve')
            link = Path(temporary) / 'config'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                bootstrap.write_once(link, 'preserve')
            self.assertEqual(target.read_text(), 'preserve')

    def test_database_check_is_read_only_and_distinguishes_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'valid.sqlite3'
            self.assertEqual(monitor.database_status(path), 'UNAVAILABLE')
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE preserved(value TEXT)')
                db.execute("INSERT INTO preserved VALUES('original')")
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(monitor.database_status(path), 'HEALTHY')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            corrupt = Path(temporary) / 'corrupt.sqlite3'
            corrupt.write_bytes(b'not a sqlite database')
            self.assertEqual(monitor.database_status(corrupt), 'CORRUPT')
            self.assertEqual(corrupt.read_bytes(), b'not a sqlite database')

    def test_offsite_refuses_exposed_secret_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'recovery-key'
            path.write_text('synthetic test material')
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                offsite.private_file(path)
            path.chmod(0o600)
            offsite.private_file(path)

    def test_stalled_workers_fail_monitoring_without_writes_and_idle_sheets_are_healthy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'data').mkdir(); (root / 'backups').mkdir()
            path = root / 'data/flood.sqlite3'
            fresh = datetime.now(timezone.utc).isoformat()
            stale = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE integration_state(key TEXT PRIMARY KEY,value TEXT,updated_at TEXT)')
                db.execute('CREATE TABLE outbox(status TEXT,attempts INTEGER)')
                db.executemany('INSERT INTO integration_state VALUES(?,?,?)', [
                    ('backup_worker', '{"status":"SUCCESS"}', fresh),
                    ('telegram', '{"status":"polled"}', stale),
                    ('sheets', '{"status":"synced"}', stale)])
            (root / 'backups/flood-fixture.tar.gz').write_bytes(b'SYNTHETIC')
            (root / 'offsite-receipt.json').write_text('{}')
            (root / 'enabled-workers.json').write_text('["telegram","sheets"]')
            rows = [{'Service': name, 'State': 'running', 'Health': 'healthy'}
                    for name in ('app', 'backup', 'proxy', 'telegram', 'sheets')]
            transport = subprocess.CompletedProcess([], 0, json.dumps(rows), '')
            with patch('sys.argv', ['host-monitor', '--root', str(root)]), \
                 patch.object(monitor, 'compose', return_value=transport) as compose, \
                 patch.object(monitor, 'tls_status', return_value={'status': 'HEALTHY'}), \
                 contextlib.redirect_stdout(io.StringIO()):
                before = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(monitor.main(), 1)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
                self.assertFalse((root / 'STOP_WRITES').exists())
                self.assertEqual(monitor.worker_status(path, ['telegram', 'sheets'], time.time())['sheets'], 'IDLE')
                with sqlite3.connect(path) as db:
                    db.execute('UPDATE integration_state SET updated_at=? WHERE key=?', (fresh, 'telegram'))
                self.assertEqual(monitor.main(), 0)
                with sqlite3.connect(path) as db:
                    db.execute("INSERT INTO outbox VALUES('pending',0)")
                self.assertEqual(monitor.main(), 1)
                with sqlite3.connect(path) as db:
                    db.execute('DELETE FROM outbox')
                    db.execute('UPDATE integration_state SET value=? WHERE key=?', ('{"status":"failed"}', 'sheets'))
                self.assertEqual(monitor.main(), 1)
                self.assertTrue(all(call.args[1:] == ('ps', '--all', '--format', 'json') for call in compose.call_args_list))


if __name__ == '__main__':
    unittest.main()
