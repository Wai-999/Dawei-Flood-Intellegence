"""Synthetic trial lifecycle regressions; never claim these are account evidence."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('trial_guard', ROOT / 'infra/trial_guard.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
NOW = datetime(2026, 10, 3, 23, tzinfo=timezone.utc)


def evidence():
    return {'policy': 'TEMPORARY_FREE_TRIAL_NO_UPGRADE_V1', 'account_type': 'FREE_TRIAL',
            'nonbillable': True, 'upgraded': False, 'captured_at': NOW.isoformat(),
            'remaining_credit_usd': 300, 'expires_at': (NOW + timedelta(days=90)).isoformat(),
            'shutdown_at': (NOW + timedelta(days=80)).isoformat(),
            'official_terms_checked_on': NOW.date().isoformat(),
            'billing_reporting_lag_reviewed': True, 'credit_source': 'SYNTHETIC FIXTURE',
            'credit_evidence_sha256': 'a' * 64, 'billing_account': 'synthetic-account',
            'projects': ['synthetic-project'], 'all_projects_visible': True,
            'independent_recovery': {'independent_of_trial_account': True,
                                     'encrypted_before_transfer': True,
                                     'signature_verified': 'PASS', 'isolated_integrity_check': 'PASS',
                                     'ciphertext_sha256': 'b' * 64,
                                     'destination_evidence': 'SYNTHETIC FIXTURE', 'completed_at': NOW.isoformat()}}


class TrialPolicyTests(unittest.TestCase):
    def test_observation_refresh_preserves_deadline_account_and_stop_latch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            value = evidence()
            with patch.object(trial, 'validate_trial'):
                trial.install_evidence(root, value)
                (root / 'STOP_WRITES').write_text('PRESERVED')
                trial.install_evidence(root, {**value, 'remaining_credit_usd': 290})
                for key, replacement in [('billing_account', 'another'), ('shutdown_at', (NOW + timedelta(days=89)).isoformat())]:
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        trial.install_evidence(root, {**value, key: replacement})
            self.assertEqual(json.loads((root / 'trial-evidence.json').read_text())['remaining_credit_usd'], 290)
            self.assertEqual((root / 'STOP_WRITES').read_text(), 'PRESERVED')
            self.assertEqual((root / 'trial-evidence.json').stat().st_mode & 0o777, 0o600)

    def test_only_explicit_unupgraded_nonbillable_trial_is_accepted(self):
        trial.validate_trial(evidence(), NOW, require_recovery=True,
                             billing_account='synthetic-account', projects=['synthetic-project'])
        for key, value in [('policy', ''), ('account_type', 'ACTIVE_NON_TRIAL'),
                           ('nonbillable', False), ('upgraded', True), ('upgraded', None)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                trial.validate_trial({**evidence(), key: value}, NOW)

    def test_credit_reserve_invalid_numbers_and_missing_evidence(self):
        for value in [49.99, True, float('nan'), float('inf'), '300', None, 301]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                trial.validate_trial({**evidence(), 'remaining_credit_usd': value}, NOW)
        for key in ['credit_source', 'credit_evidence_sha256', 'billing_reporting_lag_reviewed']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                trial.validate_trial({**evidence(), key: None}, NOW)

    def test_expiry_cutoff_future_and_stale_evidence(self):
        for key, value in [('captured_at', (NOW - timedelta(minutes=16)).isoformat()),
                           ('captured_at', (NOW + timedelta(seconds=1)).isoformat()),
                           ('shutdown_at', NOW.isoformat()),
                           ('shutdown_at', (NOW + timedelta(days=89)).isoformat()),
                           ('expires_at', NOW.replace(tzinfo=None).isoformat())]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                trial.validate_trial({**evidence(), key: value}, NOW)

    def test_whole_account_and_current_terms_are_required(self):
        with self.assertRaises(ValueError):
            trial.validate_trial(evidence(), NOW, billing_account='different-account')
        with self.assertRaises(ValueError):
            trial.validate_trial(evidence(), NOW, projects=['another-project'])
        with self.assertRaises(ValueError):
            trial.validate_trial({**evidence(), 'all_projects_visible': False}, NOW, projects=['synthetic-project'])
        with self.assertRaises(ValueError):
            trial.validate_trial({**evidence(), 'official_terms_checked_on': '2026-10-02'}, NOW)

    def test_same_account_unsigned_unencrypted_or_stale_restore_is_refused(self):
        for key, value in [('independent_of_trial_account', False), ('encrypted_before_transfer', False),
                           ('signature_verified', 'NOT VERIFIED'), ('isolated_integrity_check', 'NOT VERIFIED'),
                           ('ciphertext_sha256', ''), ('destination_evidence', ''),
                           ('completed_at', (NOW - timedelta(hours=13)).isoformat())]:
            unsafe = copy.deepcopy(evidence()); unsafe['independent_recovery'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                trial.validate_trial(unsafe, NOW, require_recovery=True)

    def test_guard_disabled_for_sustainable_hosts_and_readonly_when_requested(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(trial.guard(root, now=NOW)['status'], 'DISABLED')
            (root / 'TRIAL_REQUIRED').write_text('fixture')
            self.assertEqual(trial.guard(root, now=NOW)['status'], 'STOP WRITES')
            self.assertFalse((root / 'STOP_WRITES').exists())

    def test_expired_guard_stops_all_services_preserves_bytes_and_never_clears_latch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'data').mkdir(); (root / 'data/flood.sqlite3').write_bytes(b'SYNTHETIC DATA')
            value = evidence(); value['captured_at'] = (NOW - timedelta(hours=13)).isoformat()
            path = root / 'trial-evidence.json'; path.write_text(json.dumps(value)); path.chmod(0o600)
            with patch.object(trial.subprocess, 'run', return_value=Mock(returncode=0)) as run:
                result = trial.guard(root, apply=True, now=NOW)
            self.assertTrue(result['writers_stopped'])
            self.assertEqual(run.call_args.args[0][-1], 'stop')
            self.assertEqual((root / 'evidence/trial-stop/flood.sqlite3').read_bytes(), b'SYNTHETIC DATA')
            path.write_text(json.dumps(evidence()))
            self.assertEqual(trial.guard(root, now=NOW)['status'], 'STOP WRITES')
            self.assertEqual((root / 'STOP_WRITES').stat().st_mode & 0o777, 0o600)

    def test_existing_corruption_latch_and_evidence_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'TRIAL_REQUIRED').write_text('fixture')
            latch = root / 'STOP_WRITES'; latch.write_text('ORIGINAL CORRUPTION INCIDENT')
            with patch.object(trial.subprocess, 'run', return_value=Mock(returncode=1)):
                result = trial.guard(root, apply=True, now=NOW)
            self.assertFalse(result['writers_stopped'])
            self.assertEqual(latch.read_text(), 'ORIGINAL CORRUPTION INCIDENT')

    def test_unsafe_secret_permissions_and_symlinks_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root / 'trial-evidence.json'
            path.write_text(json.dumps(evidence())); path.chmod(0o644)
            self.assertEqual(trial.guard(root, now=NOW)['status'], 'STOP WRITES')
            path.chmod(0o600)
            self.assertEqual(trial.guard(root, now=NOW)['status'], 'TEMPORARY FREE — NOT SUSTAINABLE')
            path.rename(root / 'original'); path.symlink_to(root / 'original')
            self.assertEqual(trial.guard(root, now=NOW)['status'], 'STOP WRITES')
