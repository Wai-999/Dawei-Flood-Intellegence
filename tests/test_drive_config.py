import configparser
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'infra' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


drive = load('drive_config', 'drive-config.py')
offsite = load('offsite_drive_test', 'offsite.py')


class DriveConfigTests(unittest.TestCase):
    def fixture(self):
        now = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
        installed = {'client_id': 'fixture-desktop-client', 'client_secret': 'fixture-secret',
                     'auth_uri': 'https://accounts.google.com/o/oauth2/auth', 'token_uri': drive.TOKEN_URI}
        credential = {'client_id': installed['client_id'], 'client_secret': installed['client_secret'],
                      'token_uri': drive.TOKEN_URI, 'scopes': [drive.SCOPE], 'token': 'fixture-access',
                      'refresh_token': 'fixture-refresh', 'expiry': (now + timedelta(minutes=30)).isoformat()}
        consent = {'captured_at': now.isoformat(), 'requested_scopes': [drive.SCOPE],
                   'actual_granted_scopes': [drive.SCOPE], 'refresh_token_present': True}
        return {'installed': installed}, credential, consent, now

    def render(self, client, credential, consent, now):
        return drive.render_config(client, credential, consent, 'fixture-folder-id', now)

    def test_exact_scope_conversion_and_no_wider_remote_access(self):
        client, credential, consent, now = self.fixture()
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(self.render(client, credential, consent, now))
        self.assertEqual(config.sections(), ['dawei_drive'])
        self.assertEqual(config['dawei_drive']['scope'], 'drive.file')
        self.assertEqual(config['dawei_drive']['root_folder_id'], 'fixture-folder-id')
        self.assertEqual(config['dawei_drive']['skip_shortcuts'], 'true')
        self.assertEqual(json.loads(config['dawei_drive']['token'])['refresh_token'], 'fixture-refresh')

    def test_broader_grant_missing_refresh_and_client_mismatch_refused(self):
        for changed in ('scopes', 'refresh_token', 'client_secret', 'token_uri'):
            client, credential, consent, now = self.fixture()
            credential[changed] = ['https://www.googleapis.com/auth/drive'] if changed == 'scopes' else 'unexpected'
            if changed == 'refresh_token': credential[changed] = ''
            with self.assertRaises(ValueError): self.render(client, credential, consent, now)
        client, credential, consent, now = self.fixture()
        consent['actual_granted_scopes'].append('https://www.googleapis.com/auth/cloud-platform')
        with self.assertRaises(ValueError): self.render(client, credential, consent, now)

    def test_expired_future_naive_and_old_evidence_refused(self):
        for changed, offset in [('expiry', -1), ('captured_at', -86401), ('captured_at', 1)]:
            client, credential, consent, now = self.fixture()
            target = credential if changed == 'expiry' else consent
            target[changed] = (now + timedelta(seconds=offset)).isoformat()
            with self.assertRaises(ValueError): self.render(client, credential, consent, now)
        client, credential, consent, now = self.fixture()
        credential['expiry'] = '2026-10-04T12:30:00'
        with self.assertRaises(ValueError): self.render(client, credential, consent, now)

    def test_config_injection_refused_without_disclosing_values(self):
        client, credential, consent, now = self.fixture()
        credential['refresh_token'] = 'fixture\n[unapproved_remote]'
        with self.assertRaises(ValueError) as error: self.render(client, credential, consent, now)
        self.assertNotIn('unapproved_remote', str(error.exception))
        with self.assertRaises(ValueError):
            drive.render_config(client, credential, consent, '../outside', now)

    def test_private_atomic_install_preserves_existing_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = drive.write_config(root, 'fixture-only-data')
            self.assertEqual(target, root / 'backup-secrets/drive.conf')
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
            self.assertFalse((root / 'secrets').exists())
            with self.assertRaises(FileExistsError): drive.write_config(root, 'replacement')
            self.assertEqual(target.read_text(), 'fixture-only-data')
            self.assertEqual([p.name for p in target.parent.iterdir()], ['drive.conf'])

    def test_symlinked_and_exposed_credential_locations_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); outside = root / 'outside'; outside.mkdir()
            (root / 'backup-secrets').symlink_to(outside)
            with self.assertRaises(ValueError): drive.write_config(root, 'fixture')
            (root / 'backup-secrets').unlink(); (root / 'backup-secrets').mkdir(mode=0o755)
            with self.assertRaises(ValueError): drive.write_config(root, 'fixture')
            source = root / 'source.json'; source.write_text('{}'); source.chmod(0o644)
            with self.assertRaises(ValueError): drive.private_json(source)
            source.chmod(0o600); alias = root / 'alias.json'; alias.symlink_to(source)
            with self.assertRaises(ValueError): drive.private_json(alias)

    def test_explicit_transport_uses_only_backup_credential_and_keeps_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); default = root / 'secrets/rclone.conf'
            default.parent.mkdir(); default.write_text('fixture-default'); default.chmod(0o600)
            isolated = drive.write_config(root, 'fixture-drive')
            with patch.object(offsite, 'run') as run:
                offsite.rclone(root, 'size', '--json', 'fixture:backups', config=isolated)
                command = run.call_args.args[0]
                self.assertEqual(command[command.index('--config') + 1], str(isolated))
                self.assertIn('--retries', command)
                offsite.rclone(root, 'size', '--json', 'fixture:backups')
                self.assertEqual(run.call_args.args[0][2], str(default))
                with self.assertRaises(ValueError): offsite.rclone(root, 'size', 'fixture:', config=default)
                isolated.chmod(0o644)
                with self.assertRaises(ValueError): offsite.rclone(root, 'size', 'fixture:', config=isolated)
                run.reset_mock(); isolated.chmod(0o600); isolated.rename(root / 'original.conf'); isolated.symlink_to(root / 'original.conf')
                with self.assertRaises(ValueError): offsite.rclone(root, 'size', 'fixture:', config=isolated)
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
