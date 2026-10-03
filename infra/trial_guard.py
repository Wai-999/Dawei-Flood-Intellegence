#!/usr/bin/env python3
"""Explicit temporary, non-billable trial policy. Never upgrades or renews billing."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def moment(value):
    if not isinstance(value, str):
        raise ValueError('Trial timestamps are missing or malformed')
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Trial timestamps must include a timezone')
    return result


def validate_trial(evidence, now=None, *, max_age_seconds=900, require_recovery=False,
                   billing_account=None, projects=None):
    """Validate observed evidence, not a billing cap inferred from a budget."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(evidence, dict):
        raise ValueError('Trial evidence must be an object')
    if evidence.get('policy') != 'TEMPORARY_FREE_TRIAL_NO_UPGRADE_V1':
        raise ValueError('Explicit owner-authorized temporary policy required')
    if evidence.get('account_type') != 'FREE_TRIAL' or evidence.get('nonbillable') is not True or evidence.get('upgraded') is not False:
        raise ValueError('Only a verified non-billable, unupgraded trial is permitted')
    age = (now - moment(evidence.get('captured_at'))).total_seconds()
    if not 0 <= age <= max_age_seconds:
        raise ValueError('Trial credit/account evidence is stale or future-dated')
    credit = evidence.get('remaining_credit_usd')
    if isinstance(credit, bool) or not isinstance(credit, (int, float)) or not math.isfinite(credit) or not 50 <= credit <= 300:
        raise ValueError('Trial credit is unknown or below the $50 recovery reserve')
    cutoff = moment(evidence.get('shutdown_at'))
    if cutoff > moment(evidence.get('expires_at')) - timedelta(days=7) or now >= cutoff:
        raise ValueError('Trial needs a shutdown at least seven days before expiry')
    if evidence.get('official_terms_checked_on') != now.date().isoformat():
        raise ValueError('Current official trial terms must be checked')
    if evidence.get('billing_reporting_lag_reviewed') is not True or not evidence.get('credit_source'):
        raise ValueError('Actual credit evidence and billing lag review required')
    if not isinstance(evidence.get('credit_evidence_sha256'), str) or not re.fullmatch('[a-f0-9]{64}', evidence['credit_evidence_sha256']):
        raise ValueError('Private evidence content hash required')
    if billing_account and evidence.get('billing_account') != billing_account:
        raise ValueError('Trial evidence account mismatch')
    if projects is not None and (sorted(evidence.get('projects', [])) != sorted(projects) or evidence.get('all_projects_visible') is not True):
        raise ValueError('Whole billing-account project visibility required')
    if require_recovery:
        recovery = evidence.get('independent_recovery', {})
        if not isinstance(recovery, dict):
            raise ValueError('Independent recovery evidence must be an object')
        if recovery.get('independent_of_trial_account') is not True or recovery.get('encrypted_before_transfer') is not True:
            raise ValueError('Encrypted recovery outside the trial account is required')
        if recovery.get('signature_verified') != 'PASS' or recovery.get('isolated_integrity_check') != 'PASS':
            raise ValueError('An actual independent signed restore is required')
        if not isinstance(recovery.get('ciphertext_sha256'), str) or not re.fullmatch('[a-f0-9]{64}', recovery['ciphertext_sha256']) or not recovery.get('destination_evidence'):
            raise ValueError('Independent recovery evidence is incomplete')
        if not 0 <= (now - moment(recovery.get('completed_at'))).total_seconds() <= 43200:
            raise ValueError('Independent recovery is stale; refresh it before writes')


def guard(root, *, apply=False, now=None):
    """Refuse writes and latch shutdown on missing/expired trial evidence."""
    root = Path(root)
    path = root / 'trial-evidence.json'
    required = root / 'TRIAL_REQUIRED'
    if not path.exists() and not required.exists():
        return {'status': 'DISABLED'}
    reason = None
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError('Private trial evidence file is missing or unsafe')
        validate_trial(json.loads(path.read_text()), now, max_age_seconds=43200, require_recovery=True)
        if (root / 'STOP_WRITES').exists():
            raise ValueError('STOP_WRITES latch requires reviewed recovery')
    except (ValueError, KeyError, TypeError, OSError) as error:
        reason = str(error) if isinstance(error, ValueError) else 'Trial evidence unavailable or malformed'
    if reason is None:
        return {'status': 'TEMPORARY FREE — NOT SUSTAINABLE'}
    result = {'status': 'STOP WRITES', 'reason': reason, 'writers_stopped': False}
    if apply:
        os.umask(0o077)
        latch = root / 'STOP_WRITES'
        # Preserve any earlier corruption incident; never clear a latch automatically.
        if not latch.exists():
            latch.write_text(json.dumps({'reason': 'TRIAL_GUARD: ' + reason,
                                         'time': datetime.now(timezone.utc).isoformat()}) + '\n')
            latch.chmod(0o600)
        command = ['docker', 'compose', '--env-file', str(root / 'compose.env'), '-f', str(root / 'compose.yml'),
                   '--profile', 'telegram', '--profile', 'sheets', 'stop']
        try:
            stopped = subprocess.run(command, capture_output=True, timeout=90)
            result['writers_stopped'] = stopped.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            result['writers_stopped'] = False
        if result['writers_stopped']:
            folder = root / 'evidence' / 'trial-stop'
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            for name in ('flood.sqlite3', 'flood.sqlite3-wal', 'flood.sqlite3-shm'):
                source = root / 'data' / name
                destination = folder / name
                if source.is_file() and not destination.exists():
                    shutil.copy2(source, destination)
                    destination.chmod(0o600)
    return result


def install_evidence(root, evidence, *, require_recovery=True):
    """Refresh private observations without changing the account, deadline or latch."""
    validate_trial(evidence, require_recovery=require_recovery)
    root = Path(root)
    path = root / 'trial-evidence.json'
    if path.is_symlink():
        raise ValueError('Trial evidence symlink refused')
    if path.exists():
        if path.stat().st_mode & 0o077:
            raise ValueError('Existing trial evidence permissions are unsafe')
        previous = json.loads(path.read_text())
        for key in ('policy', 'billing_account', 'projects', 'expires_at', 'shutdown_at'):
            if previous.get(key) != evidence.get(key):
                raise ValueError('Trial account or shutdown policy drift refused')
    with tempfile.NamedTemporaryFile(mode='w', dir=root, prefix='.trial-evidence-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            temporary.chmod(0o600)
            stream.write(json.dumps(evidence, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    result = guard(args.root, apply=args.apply)
    print(json.dumps(result))
    return 1 if result['status'] == 'STOP WRITES' else 0


if __name__ == '__main__':
    raise SystemExit(main())
