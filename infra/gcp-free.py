#!/usr/bin/env python3
"""Free-only Google infrastructure plan and guarded, resumable resource provisioning.

Never creates accounts, enables billing, upgrades plans, or accepts provider terms.
Monthly usage evidence is separate from resource inventory: limits are not free usage.
"""
import argparse
import calendar
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / 'gcp-free.json').read_text())
RELEASE = json.loads((HERE / 'release.json').read_text())
COMPUTE = 'https://compute.googleapis.com/compute/v1/'
BILLING = 'https://cloudbilling.googleapis.com/v1/'
STORAGE = 'https://storage.googleapis.com/storage/v1/'


def private_json(path, value=None):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Private evidence symlink refused')
    if value is None:
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError('Private mode-600 evidence required')
        return json.loads(path.read_text())
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    path.chmod(0o600)


def validate_ids(project, billing):
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', project):
        raise ValueError('Actual authorized Google project ID required')
    if not re.fullmatch(r'[A-Z0-9]{6}-[A-Z0-9]{6}-[A-Z0-9]{6}', billing):
        raise ValueError('Actual authorized billing account ID required')


def plan(project, image):
    """No IPv4, NAT, load balancer, DNS zone, SSD, snapshot or paid image."""
    if not re.fullmatch(r'projects/ubuntu-os-cloud/global/images/ubuntu-2404-[a-z0-9-]+', image):
        raise ValueError('Resolved immutable Ubuntu 24.04 image required')
    region, zone = CONFIG['region'], CONFIG['zone']
    base = f'projects/{project}/'
    network = base + 'global/networks/dawei-free'
    subnet = base + f'regions/{region}/subnetworks/dawei-free'
    account = f'dawei-backup@{project}.iam.gserviceaccount.com'
    bucket = project + '-dawei-encrypted'
    return {
        'network': {'name': 'dawei-free', 'autoCreateSubnetworks': False},
        'subnet': {'name': 'dawei-free', 'network': COMPUTE + network,
                   'ipCidrRange': '10.77.0.0/24', 'stackType': 'IPV4_IPV6',
                   'ipv6AccessType': 'EXTERNAL'},
        'ipv6_address': {'name': 'dawei-ipv6', 'ipVersion': 'IPV6', 'ipv6EndpointType': 'VM',
                         'networkTier': 'PREMIUM', 'subnetwork': COMPUTE + subnet},
        'firewalls': [
            {'name': 'dawei-iap-ssh', 'network': COMPUTE + network,
             'direction': 'INGRESS', 'sourceRanges': ['35.235.240.0/20'],
             'targetTags': ['dawei-free'], 'allowed': [{'IPProtocol': 'tcp', 'ports': ['22']}]},
            {'name': 'dawei-public-ipv6', 'network': COMPUTE + network,
             'direction': 'INGRESS', 'sourceRanges': ['::/0'], 'targetTags': ['dawei-free'],
             'allowed': [{'IPProtocol': 'tcp', 'ports': ['80', '443']}]}
        ],
        'bucket': {'name': bucket, 'location': region.upper(), 'storageClass': 'STANDARD',
                   'iamConfiguration': {'uniformBucketLevelAccess': {'enabled': True},
                                        'publicAccessPrevention': 'enforced'},
                   'versioning': {'enabled': False},
                   'softDeletePolicy': {'retentionDurationSeconds': '0'}},
        'instance': {
            'name': 'dawei-pilot', 'machineType': base + f'zones/{zone}/machineTypes/e2-micro',
            'deletionProtection': True, 'tags': {'items': ['dawei-free']},
            'scheduling': {'preemptible': False, 'provisioningModel': 'STANDARD'},
            'disks': [{'boot': True, 'autoDelete': False, 'type': 'PERSISTENT',
                       'initializeParams': {'diskName': 'dawei-pilot', 'diskSizeGb': '30',
                                            'diskType': base + f'zones/{zone}/diskTypes/pd-standard',
                                            'sourceImage': image}}],
            'networkInterfaces': [{'subnetwork': COMPUTE + subnet, 'stackType': 'IPV4_IPV6',
                                   'ipv6AccessConfigs': [{'type': 'DIRECT_IPV6', 'networkTier': 'PREMIUM'}]}],
            'serviceAccounts': [{'email': account, 'scopes': ['https://www.googleapis.com/auth/devstorage.read_write']}],
            'metadata': {'items': [{'key': 'enable-oslogin', 'value': 'TRUE'},
                                   {'key': 'block-project-ssh-keys', 'value': 'TRUE'}]},
            'labels': {'application': 'dawei-flood', 'configuration': CONFIG['configuration_version'],
                       'release': RELEASE['commit'][:12]}
        }
    }


class Google:
    def __init__(self):
        if not shutil.which('gcloud'):
            raise ValueError('GOOGLE CLOUD AUTHORIZATION REQUIRED; gcloud is not installed')
        result = subprocess.run(['gcloud', 'auth', 'print-access-token', '--quiet'],
                                check=False, capture_output=True, text=True, timeout=60)
        if result.returncode or not result.stdout.strip():
            raise ValueError('GOOGLE CLOUD AUTHORIZATION REQUIRED')
        self.token = result.stdout.strip()  # In memory only; never printed or written.
        self.storage_calls = 0

    def request(self, url, method='GET', body=None):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'compute.googleapis.com', 'cloudbilling.googleapis.com', 'storage.googleapis.com', 'iam.googleapis.com', 'www.googleapis.com'} or parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ValueError('Credential-bearing API requests require an official Google HTTPS endpoint')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, response, code, message, headers, new_url):
                return None  # Never forward OAuth headers through a redirect.
        opener = urllib.request.build_opener(NoRedirect)
        data = None if body is None else json.dumps(body).encode()
        for attempt in range(3):
            if parsed.hostname == 'storage.googleapis.com':
                self.storage_calls += 1
                if self.storage_calls > 1000:
                    raise ValueError('Storage request budget reached; no further metered inventory calls')
            request = urllib.request.Request(url, data=data, method=method,
                headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
            try:
                with opener.open(request, timeout=45) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    return None
                if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise ValueError(f'Google API refused action (HTTP {error.code}); private response withheld') from None
                time.sleep(2**attempt)
        raise ValueError('Bounded Google API retries exhausted')

    def pages(self, url, key):
        results = []
        for _ in range(100):
            value = self.request(url)
            if value is None:
                raise ValueError('Inventory endpoint unavailable; cannot assume zero usage')
            results.extend(value.get(key, []))
            token = value.get('nextPageToken')
            if not token:
                return results
            url = url.split('&pageToken=')[0] + ('&' if '?' in url else '?') + 'pageToken=' + urllib.parse.quote(token, safe='')
        raise ValueError('Inventory pagination limit reached; no creation authorized')


def inventory(api, project, billing):
    link = api.request(BILLING + 'projects/' + project + '/billingInfo')
    if not link or not link.get('billingEnabled') or link.get('billingAccountName') != 'billingAccounts/' + billing:
        raise ValueError('Existing owner-authorized billing link required; it will not be changed')
    projects = api.pages(BILLING + 'billingAccounts/' + billing + '/projects?pageSize=100', 'projectBillingInfo')
    result = {'captured_at': datetime.now(timezone.utc).isoformat(), 'billing_account': billing,
              'project': project, 'projects': [], 'resources': {}}
    for entry in projects:
        name = entry['projectId']
        result['projects'].append(name)
        resources = {}
        for kind in ('instances', 'disks', 'addresses', 'forwardingRules', 'routers'):
            groups = api.request(COMPUTE + f'projects/{name}/aggregated/{kind}?maxResults=500')
            if groups is None or groups.get('nextPageToken'):
                raise ValueError('Complete account inventory unavailable; no creation authorized')
            resources[kind] = [v for group in groups.get('items', {}).values() for v in group.get(kind, [])]
        buckets = api.pages(STORAGE + 'b?project=' + name + '&maxResults=100', 'items')
        resources['buckets'] = []
        for bucket in buckets:
            objects = api.pages(STORAGE + 'b/' + bucket['name'] + '/o?maxResults=1000&versions=true', 'items')
            resources['buckets'].append({**bucket, 'actual_bytes': sum(int(o['size']) for o in objects)})
        result['resources'][name] = resources
    if project not in result['projects']:
        raise ValueError('Authorized project missing from billing account inventory')
    return result


def free_gate(observed, usage, now=None):
    """Fail closed on incomplete, stale, shared or historically consumed allowances."""
    now = now or datetime.now(timezone.utc)
    captured = datetime.fromisoformat(usage['captured_at'])
    if captured.tzinfo is None or not 0 <= (now - captured).total_seconds() <= 900:
        raise ValueError('Usage evidence must be timezone-aware and less than 15 minutes old')
    if usage.get('period') != now.strftime('%Y-%m') or usage.get('billing_account') != observed['billing_account']:
        raise ValueError('Usage evidence belongs to a different account or month')
    if sorted(usage.get('projects', [])) != sorted(observed['projects']) or not usage.get('all_projects_visible'):
        raise ValueError('Whole billing account visibility required')
    if usage.get('account_type') != 'ACTIVE_NON_TRIAL' or usage.get('custom_rate_card') is not False:
        raise ValueError('Sustainable Free Tier eligibility unverified; trial data deletion is unacceptable')
    if usage.get('official_free_terms_checked_on') != now.date().isoformat():
        raise ValueError('Recheck current official eligibility before creating resources')
    project = observed['project']
    for name, resources in observed['resources'].items():
        if any(resources.get(k) for k in ('forwardingRules', 'routers')):
            raise ValueError('Existing charged networking or shared allowance requires review')
        for address in resources.get('addresses', []):
            if name != project or address['name'] != 'dawei-ipv6' or address.get('ipVersion') != 'IPV6' or not address.get('region', '').endswith('/' + CONFIG['region']):
                raise ValueError('Only the selected free regional IPv6 address is permitted')
        for vm in resources.get('instances', []):
            if name != project or vm['name'] != 'dawei-pilot' or not vm['machineType'].endswith('/e2-micro'):
                raise ValueError('Other VM consumes the aggregate free allowance')
            if any(n.get('accessConfigs') for n in vm.get('networkInterfaces', [])):
                raise ValueError('External IPv4 is chargeable and forbidden')
        for disk in resources.get('disks', []):
            if name != project or disk['name'] != 'dawei-pilot' or not disk['type'].endswith('/pd-standard') or int(disk['sizeGb']) > 30:
                raise ValueError('Disk allowance conflict or chargeable storage')
        for bucket in resources.get('buckets', []):
            if name != project or bucket['name'] != project + '-dawei-encrypted' or bucket['actual_bytes'] > CONFIG['bucket_max_bytes']:
                raise ValueError('Storage allowance conflict or capacity reached')
            if bucket['location'].lower() != CONFIG['region'] or bucket['storageClass'] != 'STANDARD':
                raise ValueError('Bucket location/class is outside selected free allowance')
    month_hours = calendar.monthrange(now.year, now.month)[1] * 24
    next_month = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
    remaining_hours = (next_month - now).total_seconds() / 3600
    required = {'e2_micro_hours': month_hours - remaining_hours, 'pd_standard_gb_month': 30,
                'compute_egress_bytes': 500000000, 'storage_gb_month': 1,
                'storage_class_a': 1000, 'storage_class_b': 10000,
                'storage_egress_bytes': 1000000000}
    for metric, maximum in required.items():
        value = usage.get('usage', {}).get(metric)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= maximum:
            raise ValueError('Missing or exhausted aggregate monthly allowance: ' + metric)
    if usage['usage']['pd_standard_gb_month'] + 30 * remaining_hours / month_hours > 30:
        raise ValueError('Historical disk consumption leaves insufficient free disk-months')
    if not usage.get('usage_source') or not usage.get('billing_reporting_lag_reviewed'):
        raise ValueError('Actual usage source and reporting lag review required; quotas are not usage')
    if not usage.get('nonbillable_destinations_verified') or not usage.get('egress_enforcement_plan_verified'):
        raise ValueError('Traffic cost controls unverified: China/Australia and overage are not free')


def subset(actual, wanted):
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and all(k in actual and subset(actual[k], v) for k, v in wanted.items())
    if isinstance(wanted, list):
        return isinstance(actual, list) and len(actual) == len(wanted) and all(subset(a, b) for a, b in zip(actual, wanted))
    if isinstance(wanted, str) and isinstance(actual, str) and wanted.startswith('projects/'):
        return actual.endswith('/' + wanted) or actual == wanted
    if isinstance(wanted, str) and isinstance(actual, str) and '/compute/v1/projects/' in wanted:
        return actual.split('/compute/v1/', 1)[-1] == wanted.split('/compute/v1/', 1)[-1]
    return actual == wanted


def ensure(api, collection, name, body):
    existing = api.request(collection + '/' + name)
    if existing is not None:
        expected = json.loads(json.dumps(body))
        if 'disks' in expected:
            for disk in expected['disks']:
                initialization = disk.pop('initializeParams')
                actual_disk = api.request(collection.rsplit('/instances', 1)[0] + '/disks/' + initialization['diskName'])
                if actual_disk is None or int(actual_disk['sizeGb']) != int(initialization['diskSizeGb']) or not subset(actual_disk['type'], initialization['diskType']) or not subset(actual_disk.get('sourceImage'), initialization['sourceImage']):
                    raise ValueError('Existing persistent disk differs; never replace it')
        if not subset(existing, expected):
            raise ValueError('Existing provider configuration differs; preserve and review')
        return existing
    identity = str(uuid.uuid5(uuid.NAMESPACE_URL, collection + '/' + name))
    created = api.request(collection + '?requestId=' + identity, 'POST', body)
    if created is None:
        raise ValueError('Creation result unavailable')
    if created.get('kind') == 'compute#operation':
        for _ in range(60):
            if 'error' in created:
                raise ValueError('Provider operation failed; private response withheld')
            if created.get('status') == 'DONE':
                return api.request(collection + '/' + name)
            time.sleep(5)
            created = api.request(created['selfLink'])
            if created is None:
                raise ValueError('Provider operation disappeared; preserve resources and inspect')
        raise ValueError('Provider operation timed out; inspect existing operation before retry')
    return created


def provision(api, project, desired):
    """Network and IAM first. Stop on failure; preserve existing disks and data."""
    prefix = COMPUTE + f'projects/{project}/'
    ensure(api, prefix + 'global/networks', 'dawei-free', desired['network'])
    ensure(api, prefix + f'regions/{CONFIG["region"]}/subnetworks', 'dawei-free', desired['subnet'])
    address = ensure(api, prefix + f'regions/{CONFIG["region"]}/addresses', 'dawei-ipv6', desired['ipv6_address'])
    if not address or not address.get('address'):
        raise ValueError('Reserved free IPv6 address not available')
    access = desired['instance']['networkInterfaces'][0]['ipv6AccessConfigs'][0]
    access.update({'externalIpv6': address['address'].split('/')[0], 'externalIpv6PrefixLength': 96})
    for rule in desired['firewalls']:
        ensure(api, prefix + 'global/firewalls', rule['name'], rule)
    account = f'dawei-backup@{project}.iam.gserviceaccount.com'
    iam = 'https://iam.googleapis.com/v1/projects/' + project + '/serviceAccounts'
    if api.request(iam + '/' + account) is None:
        api.request(iam, 'POST', {'accountId': 'dawei-backup', 'serviceAccount': {'displayName': 'Dawei encrypted backup only'}})
    bucket = desired['bucket']['name']
    existing_bucket = api.request(STORAGE + 'b/' + bucket)
    if existing_bucket is None:
        api.request(STORAGE + 'b?project=' + project, 'POST', desired['bucket'])
    elif not subset(existing_bucket, desired['bucket']):
        raise ValueError('Existing bucket configuration differs; preserve and review')
    # Append/read ciphertext only. No deletion, project role, public access or credential key.
    policy_url = STORAGE + 'b/' + bucket + '/iam'
    policy = api.request(policy_url)
    if policy is None:
        raise ValueError('Bucket access policy unavailable')
    bindings = policy.setdefault('bindings', [])
    member = 'serviceAccount:' + account
    for role in ('roles/storage.objectCreator', 'roles/storage.objectViewer'):
        binding = next((b for b in bindings if b['role'] == role and 'condition' not in b), None)
        if binding is None:
            binding = {'role': role, 'members': []}; bindings.append(binding)
        if member not in binding['members']:
            binding['members'].append(member)
    api.request(policy_url, 'PUT', policy)
    collection = prefix + f'zones/{CONFIG["zone"]}/instances'
    if api.request(collection + '/dawei-pilot') is None and api.request(prefix + f'zones/{CONFIG["zone"]}/disks/dawei-pilot') is not None:
        raise ValueError('Unattached persistent disk exists; preserve it and review recovery before VM creation')
    return ensure(api, collection, 'dawei-pilot', desired['instance'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('plan', 'inventory', 'provision'), default='plan')
    parser.add_argument('--project', required=True)
    parser.add_argument('--billing-account', required=True)
    parser.add_argument('--evidence', type=Path, default=Path('outputs/private-cloud/gcp-inventory.json'))
    parser.add_argument('--usage-evidence', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    validate_ids(args.project, args.billing_account)
    if args.mode == 'plan':
        print(json.dumps({'state': 'INFRASTRUCTURE-SELECTED', **RELEASE, **CONFIG,
                          'host_provisioned': False, 'required': ['owner Google authorization',
                          'active non-trial Free Tier account', 'whole-account usage evidence',
                          'DuckDNS private authorization after host readiness'],
                          'ipv4_clients': 'NOT SUPPORTED by direct free IPv6 origin'}))
        return
    if not args.usage_evidence:
        raise ValueError('Private billing-usage evidence required before potentially metered Storage inventory')
    usage = private_json(args.usage_evidence)
    now = datetime.now(timezone.utc)
    captured = datetime.fromisoformat(usage['captured_at'])
    if captured.tzinfo is None or not 0 <= (now - captured).total_seconds() <= 900 or usage.get('period') != now.strftime('%Y-%m') or usage.get('billing_account') != args.billing_account:
        raise ValueError('Fresh matching monthly evidence required before Storage inventory')
    calls = usage.get('usage', {}).get('storage_class_a')
    if not isinstance(calls, (int, float)) or isinstance(calls, bool) or not 0 <= calls <= 1000 or not usage.get('billing_reporting_lag_reviewed'):
        raise ValueError('Verified Storage request headroom required before inventory')
    api = Google()
    observed = inventory(api, args.project, args.billing_account)
    private_json(args.evidence, observed)
    if args.mode == 'inventory':
        print('Private whole-account inventory saved; resource quotas do not prove remaining free usage.')
        return
    free_gate(observed, usage)
    image = api.request(COMPUTE + 'projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64')
    if not image or image.get('deprecated', {}).get('state') in {'DEPRECATED', 'OBSOLETE', 'DELETED'}:
        raise ValueError('Supported immutable OS image unavailable')
    image_path = 'projects/ubuntu-os-cloud/global/images/' + image['name']
    desired = plan(args.project, image_path)
    private_json(args.evidence.with_name('gcp-plan.json'), desired)
    operation = provision(api, args.project, desired)
    private_json(args.evidence.with_name('gcp-plan.json'), desired)
    private_json(args.evidence.with_name('gcp-provision-operation.json'), {
        'timestamp': datetime.now(timezone.utc).isoformat(), 'operation': operation,
        'application_commit': RELEASE['commit'], 'configuration_version': CONFIG['configuration_version'],
        'plan_sha256': hashlib.sha256(json.dumps(desired, sort_keys=True).encode()).hexdigest(),
        'state': 'PROVISIONING' if operation.get('status') != 'RUNNING' else 'HOST-PROVISIONED',
        'deployed': False, 'https': 'NOT VERIFIED', 'restore': 'NOT VERIFIED'})
    print('Provider operation recorded privately. Verify completion before bootstrap; no deployment claimed.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, urllib.error.URLError):
        print('Google deployment stopped safely. Review private evidence or account authorization; no credentials logged.')
        raise SystemExit(1)
