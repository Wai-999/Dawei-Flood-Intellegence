import contextlib
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flood.domain import DomainError
from flood.repository import Repository

spec = importlib.util.spec_from_file_location('keyless_sheets', Path(__file__).resolve().parents[1] / 'infra/keyless-sheets.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class KeylessSheetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / 'workload.json'
        self.value = {'caller_service_account': 'flood-backup@example-project.iam.gserviceaccount.com',
                      'service_account': 'flood-sheets@example-project.iam.gserviceaccount.com',
                      'sheet_id': 'synthetic-sheet-123'}
        self.config.write_text(json.dumps(self.value)); self.config.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def test_private_configuration_refuses_keys_unsafe_paths_and_unexpected_scope(self):
        self.config.chmod(0o644)
        with self.assertRaises(ValueError): adapter.configuration(self.config)
        self.config.chmod(0o600)
        link = self.root / 'link'; link.symlink_to(self.config)
        with self.assertRaises(ValueError): adapter.configuration(link)
        for extra in ('private_key', 'scope', 'token_url'):
            self.config.write_text(json.dumps({**self.value, extra: 'SYNTHETIC'}))
            with self.assertRaises(ValueError): adapter.configuration(self.config)

    def test_tokens_have_one_scope_short_lifetime_memory_cache_and_verified_caller(self):
        current = [1000000000.0]; calls = []
        def request(url, data=None, headers=None):
            calls.append((url, data, headers))
            if url.endswith('/email'): return {'email': self.value['caller_service_account']}
            if url.endswith('/token'): return {'access_token': 'synthetic-source-token'}
            self.assertEqual(data, {'scope': [adapter.SCOPE], 'lifetime': '1800s'})
            return {'accessToken': 'synthetic-projection-token',
                    'expireTime': datetime.fromtimestamp(current[0] + 1800, timezone.utc).isoformat()}
        token = adapter.WorkloadToken(self.config, request=request, clock=lambda: current[0])
        self.assertEqual(token(self.config), 'synthetic-projection-token')
        self.assertEqual(token(self.config), 'synthetic-projection-token')
        self.assertEqual(len(calls), 3)
        current[0] += 1741
        token(self.config)
        self.assertEqual(len(calls), 6)
        self.assertEqual(set(p.name for p in self.root.iterdir()), {'workload.json'})
        wrong = adapter.WorkloadToken(self.config, request=lambda *a, **kw: {'email': 'wrong'}, clock=lambda: current[0])
        with self.assertRaises(DomainError): wrong(self.config)

    def test_malformed_or_excessive_lifetime_tokens_are_refused(self):
        for token_value, expiry in [('unsafe\r\nheader', 1800), ('synthetic-token', 7200), ('synthetic-token', 10)]:
            def request(url, data=None, headers=None):
                if url.endswith('/email'): return {'email': self.value['caller_service_account']}
                if url.endswith('/token'): return {'access_token': 'synthetic-source-token'}
                return {'accessToken': token_value, 'expireTime': datetime.fromtimestamp(1000000000 + expiry, timezone.utc).isoformat()}
            token = adapter.WorkloadToken(self.config, request=request, clock=lambda: 1000000000)
            with self.assertRaises(DomainError): token(self.config)

    def test_untrusted_endpoints_redirects_and_metadata_auth_leaks_are_refused(self):
        with self.assertRaises(DomainError):
            adapter.credential_request('https://untrusted.example/token', headers={'Authorization': 'Bearer synthetic-token'})
        with self.assertRaises(DomainError):
            adapter.credential_request(adapter.METADATA + 'token', headers={'Authorization': 'Bearer synthetic-token'})
        with self.assertRaises(DomainError):
            adapter.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://untrusted.example/')

    def test_projection_request_limit_and_destination_isolation(self):
        current = [0.0]; calls = []
        def sleep(seconds): current[0] += seconds
        def client(*args): calls.append(current[0]); return {}
        client = adapter.ProjectionClient(self.value['sheet_id'], client=client, clock=lambda: current[0], sleep=sleep)
        for _ in range(11): client(client.base + '?fields=sheets.properties')
        self.assertGreaterEqual(calls[-1] - calls[0], 60)
        with self.assertRaises(DomainError): client(client.base + '-unrelated/values/A1')

    def test_eight_failures_stop_and_logs_do_not_contain_exception_payload(self):
        repo = Repository(str(self.root / 'fixture.sqlite3')); waits = []; output = io.StringIO()
        with patch.object(adapter, 'sync_sheets', side_effect=DomainError('synthetic-sensitive-error-token')) as sync, contextlib.redirect_stdout(output):
            self.assertEqual(adapter.run(repo, None, None, sleep=waits.append), 1)
        self.assertEqual(sync.call_count, 8)
        self.assertEqual(waits, [2, 4, 8, 16, 32, 60, 60])
        self.assertNotIn('synthetic-sensitive-error-token', output.getvalue())
        self.assertNotIn('synthetic-sensitive-error-token', repo.rows('SELECT value FROM integration_state')[0]['value'])

    def test_idle_projection_records_heartbeat_without_provider_calls(self):
        repo = Repository(str(self.root / 'fixture.sqlite3'))
        def forbidden(*args, **kwargs): raise AssertionError('Idle projection contacted provider')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(adapter.run(repo, forbidden, forbidden, once=True), 0)
        state = json.loads(repo.rows("SELECT value FROM integration_state WHERE key='sheets'")[0]['value'])
        self.assertEqual(state['status'], 'idle')


if __name__ == '__main__':
    unittest.main()
