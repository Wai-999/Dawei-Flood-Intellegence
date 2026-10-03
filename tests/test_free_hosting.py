"""Safety gates for the selected free VM path; no account or network access."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_infrastructure import module

gcp = module('gcp-free')
bootstrap = module('bootstrap')
dns = module('duckdns-update')
transfer = module('transfer-image')
NOW = datetime(2026, 10, 3, 16, tzinfo=timezone.utc)
PROJECT = 'synthetic-project'
ACCOUNT = 'AAAAAA-BBBBBB-CCCCCC'
IMAGE = 'projects/ubuntu-os-cloud/global/images/ubuntu-2404-noble-amd64-v20260930'


def evidence():
    observed = {'project': PROJECT, 'billing_account': ACCOUNT, 'projects': [PROJECT],
                'resources': {PROJECT: {'instances': [], 'disks': [], 'buckets': []}}}
    usage = {'captured_at': NOW.isoformat(), 'period': '2026-10', 'billing_account': ACCOUNT,
             'projects': [PROJECT], 'all_projects_visible': True, 'account_type': 'ACTIVE_NON_TRIAL',
             'custom_rate_card': False, 'official_free_terms_checked_on': '2026-10-03',
             'usage_source': 'SYNTHETIC FIXTURE ONLY', 'billing_reporting_lag_reviewed': True,
             'nonbillable_destinations_verified': True, 'egress_enforcement_plan_verified': True,
             'usage': {k: 0 for k in ['e2_micro_hours', 'pd_standard_gb_month', 'compute_egress_bytes',
                                      'storage_gb_month', 'storage_class_a', 'storage_class_b', 'storage_egress_bytes']}}
    return observed, usage


class FreeHostingTests(unittest.TestCase):
    def test_plan_has_durable_free_disk_and_no_external_ipv4(self):
        value = gcp.plan(PROJECT, IMAGE)
        vm = value['instance']
        self.assertTrue(vm['deletionProtection'])
        self.assertFalse(vm['disks'][0]['autoDelete'])
        self.assertEqual(vm['disks'][0]['initializeParams']['diskSizeGb'], '30')
        self.assertEqual(vm['disks'][0]['initializeParams']['sourceImage'], IMAGE)
        self.assertNotIn('accessConfigs', vm['networkInterfaces'][0])
        self.assertEqual(value['bucket']['iamConfiguration']['publicAccessPrevention'], 'enforced')
        self.assertEqual(value['bucket']['softDeletePolicy']['retentionDurationSeconds'], '0')
        self.assertFalse(value['bucket']['versioning']['enabled'])
        self.assertNotIn('startup-script', json.dumps(vm))

    def test_registry_digest_normalizes_tag_without_changing_hash_or_registry_port(self):
        digest = 'sha256:' + 'a' * 64
        self.assertEqual(transfer.canonical_digest('caddy:2-alpine@' + digest), 'caddy@' + digest)
        self.assertEqual(transfer.canonical_digest('docker.io/library/caddy@' + digest), 'caddy@' + digest)
        self.assertEqual(transfer.canonical_digest('registry.example:5000/pilot:v1@' + digest), 'registry.example:5000/pilot@' + digest)

    def test_private_aggregate_usage_required_not_resource_quota(self):
        observed, usage = evidence()
        gcp.free_gate(observed, usage, NOW)
        for metric in list(usage['usage']):
            unsafe = copy.deepcopy(usage); del unsafe['usage'][metric]
            with self.assertRaises(ValueError): gcp.free_gate(observed, unsafe, NOW)

    def test_oauth_headers_never_go_to_untrusted_or_plaintext_endpoints(self):
        api = object.__new__(gcp.Google)
        api.token = 'SYNTHETIC IN-MEMORY FIXTURE'
        for url in ['http://compute.googleapis.com/', 'https://attacker.invalid/',
                    'https://compute.googleapis.com.attacker.invalid/', 'https://user@compute.googleapis.com/']:
            with self.assertRaises(ValueError): api.request(url)

    def test_trial_and_incomplete_visibility_and_egress_policy_are_refused(self):
        observed, usage = evidence()
        for key, value in [('account_type', 'FREE_TRIAL'), ('all_projects_visible', False),
                           ('custom_rate_card', True), ('nonbillable_destinations_verified', False),
                           ('egress_enforcement_plan_verified', False), ('projects', [])]:
            unsafe = {**usage, key: value}
            with self.assertRaises(ValueError): gcp.free_gate(observed, unsafe, NOW)

    def test_stale_wrong_month_and_clock_skew_are_refused(self):
        observed, usage = evidence()
        for captured in [NOW - timedelta(minutes=16), NOW + timedelta(seconds=1)]:
            with self.assertRaises(ValueError): gcp.free_gate(observed, {**usage, 'captured_at': captured.isoformat()}, NOW)
        with self.assertRaises(ValueError): gcp.free_gate(observed, {**usage, 'period': '2026-09'}, NOW)

    def test_other_vm_and_historical_disk_usage_consume_free_allowance(self):
        observed, usage = evidence()
        observed['resources'][PROJECT]['instances'] = [{'name': 'another-vm', 'machineType': 'zones/test/machineTypes/e2-micro'}]
        with self.assertRaises(ValueError): gcp.free_gate(observed, usage, NOW)
        observed['resources'][PROJECT]['instances'] = []
        usage['usage']['pd_standard_gb_month'] = 29
        with self.assertRaises(ValueError): gcp.free_gate(observed, usage, NOW)

    def test_charged_ip_storage_and_exhausted_allowances_are_refused(self):
        observed, usage = evidence()
        vm = {'name': 'dawei-pilot', 'machineType': 'zones/test/machineTypes/e2-micro',
              'networkInterfaces': [{'accessConfigs': [{'type': 'ONE_TO_ONE_NAT'}]}]}
        observed['resources'][PROJECT]['instances'] = [vm]
        with self.assertRaises(ValueError): gcp.free_gate(observed, usage, NOW)
        observed['resources'][PROJECT]['instances'] = []
        observed['resources'][PROJECT]['disks'] = [{'name': 'dawei-pilot', 'type': 'zones/test/diskTypes/pd-ssd', 'sizeGb': '30'}]
        with self.assertRaises(ValueError): gcp.free_gate(observed, usage, NOW)
        observed['resources'][PROJECT]['disks'] = []
        usage['usage']['compute_egress_bytes'] = 500000001
        with self.assertRaises(ValueError): gcp.free_gate(observed, usage, NOW)

    def test_provider_operation_is_completed_before_dependent_creation(self):
        desired = {'name': 'dawei-free', 'autoCreateSubnetworks': False}
        api = Mock()
        api.request.side_effect = [None, {'kind': 'compute#operation', 'status': 'RUNNING', 'selfLink': 'operation'},
                                   {'kind': 'compute#operation', 'status': 'DONE'}, desired]
        with patch.object(gcp.time, 'sleep'):
            self.assertEqual(gcp.ensure(api, 'networks', 'dawei-free', desired), desired)
        self.assertEqual(api.request.call_args_list[-1].args, ('networks/dawei-free',))

    def test_existing_provider_configuration_is_preserved_and_drift_refused(self):
        api = Mock(); api.request.return_value = {'name': 'dawei-free', 'autoCreateSubnetworks': False}
        desired = {'name': 'dawei-free', 'autoCreateSubnetworks': False}
        gcp.ensure(api, 'networks', 'dawei-free', desired)
        self.assertEqual(api.request.call_count, 1)
        with self.assertRaises(ValueError): gcp.ensure(api, 'networks', 'dawei-free', {**desired, 'autoCreateSubnetworks': True})

    def test_id_validation_and_unpinned_os_are_refused(self):
        gcp.validate_ids(PROJECT, ACCOUNT)
        for name in ['bad/project', 'unsafe\nproject', 'x']:
            with self.assertRaises(ValueError): gcp.validate_ids(name, ACCOUNT)
        with self.assertRaises(ValueError): gcp.plan(PROJECT, 'projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64')

    def test_private_evidence_permissions_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / 'evidence.json'
            gcp.private_json(path, {'synthetic': True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(gcp.private_json(path), {'synthetic': True})
            link = Path(folder).resolve() / 'link'; link.symlink_to(path)
            with self.assertRaises(ValueError): gcp.private_json(link, {})

    def test_preloaded_transfer_rejects_tampering_and_unapproved_registry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            receipt = {'application_commit': bootstrap.RELEASE['commit'], 'images': []}
            for kind, registry in [('application', bootstrap.RELEASE['amd64_image']), ('caddy', bootstrap.RELEASE['caddy_image'])]:
                archive = root / (kind + '.tar'); archive.write_bytes(b'SYNTHETIC ARCHIVE FIXTURE'); archive.chmod(0o600)
                receipt['images'].append({'kind': kind, 'registry_digest': registry, 'archive': archive.name,
                                          'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                                          'image_config_digest': 'sha256:' + 'a' * 64})
            path = root / 'image-receipt.json'; path.write_text(json.dumps(receipt)); path.chmod(0o600)
            self.assertEqual(set(bootstrap.preloaded_images(path)), {'application', 'caddy'})
            (root / 'application.tar').write_bytes(b'TAMPERED')
            with self.assertRaises(ValueError): bootstrap.preloaded_images(path)
            receipt['images'][0]['registry_digest'] = 'arbitrary:latest'; path.write_text(json.dumps(receipt))
            with self.assertRaises(ValueError): bootstrap.preloaded_images(path)

    def test_ipv6_only_dns_clear_and_publish_are_separate_and_private(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'token'; path.write_text('SYNTHETIC-CREDENTIAL'); path.chmod(0o600)
            with patch('sys.argv', ['duckdns-update.py', '--token-file', str(path), '--ipv6-only', '--ipv6', '2001:db8::1']), patch.object(dns, 'update') as update:
                dns.main()
            calls = update.call_args_list
            self.assertEqual(calls[0].args[0]['clear'], 'true')
            self.assertNotIn('ip', calls[1].args[0])
            self.assertEqual(calls[1].args[0]['ipv6'], '2001:db8::1')


if __name__ == '__main__': unittest.main()
