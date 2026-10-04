import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('scheduled_offsite', Path(__file__).parents[1] / 'infra/scheduled-offsite.py')
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


class ScheduledOffsiteTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'secrets').mkdir()
        config = root / 'secrets/offsite.json'
        config.write_text(json.dumps({'destination': 'fixture:private/backups', 'recipient': 'age1' + 'a' * 58,
                                     'max_remote_bytes': 4_000_000_000}))
        config.chmod(0o600)
        return config

    def test_exposed_or_symlinked_configuration_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); config = self.fixture(root)
            config.chmod(0o644)
            with self.assertRaises(ValueError): scheduler.settings(root)
            config.chmod(0o600); hidden = root / 'original.json'; config.rename(hidden); config.symlink_to(hidden)
            with self.assertRaises(ValueError): scheduler.settings(root)

    def test_secret_identity_and_capacity_expansion_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); config = self.fixture(root); value = json.loads(config.read_text())
            value['identity'] = 'do-not-copy-owner-identity'
            config.write_text(json.dumps(value))
            with self.assertRaises(ValueError): scheduler.settings(root)
            del value['identity']; value['max_remote_bytes'] = 4_000_000_001; config.write_text(json.dumps(value))
            with self.assertRaises(ValueError): scheduler.settings(root)

    def test_latched_writes_prevent_upload_without_cloud_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self.fixture(root); (root / 'STOP_WRITES').write_text('preserve evidence')
            with patch.object(scheduler.subprocess, 'run') as run:
                with self.assertRaises(ValueError): scheduler.upload(root)
                run.assert_not_called()
            self.assertTrue((root / 'STOP_WRITES').exists())

    def test_stale_trial_evidence_prevents_upload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self.fixture(root)
            with patch.object(scheduler.runpy, 'run_path', return_value={'guard': lambda *args, **kwargs: {'status': 'STOP WRITES'}}), patch.object(scheduler.subprocess, 'run') as run:
                with self.assertRaises(ValueError): scheduler.upload(root)
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
