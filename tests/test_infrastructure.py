import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest


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


if __name__ == '__main__':
    unittest.main()
