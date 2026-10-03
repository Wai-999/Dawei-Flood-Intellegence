#!/usr/bin/env python3
"""Export the exact approved AMD64 image for private IAP transfer to an IPv6 host."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
RELEASE = json.loads((HERE / 'release.json').read_text())


def run(arguments):
    return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=600)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def canonical_digest(reference):
    repository, value = reference.rsplit('@', 1)
    prefix, slash, name = repository.rpartition('/')
    name = name.split(':', 1)[0]
    repository = prefix + slash + name
    for docker_prefix in ('docker.io/library/', 'index.docker.io/library/'):
        if repository.startswith(docker_prefix):
            repository = repository[len(docker_prefix):]
    return repository + '@' + value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='Private ignored directory, never a tracked source directory')
    args = parser.parse_args()
    os.umask(0o077)
    root = args.output.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or root.exists():
        raise ValueError('Use a new private output directory')
    # Archives and receipts contain no DB, source imports, passwords, tokens or operational data.
    root.mkdir(mode=0o700, parents=True)
    receipt = {'application_commit': RELEASE['commit'], 'created_at': datetime.now(timezone.utc).isoformat(), 'images': []}
    for label, image in [('application', RELEASE['amd64_image']), ('caddy', RELEASE['caddy_image'])]:
        run(['docker', 'pull', '--platform', 'linux/amd64', image])
        observed = json.loads(run(['docker', 'image', 'inspect', image]).stdout)[0]
        select_platform = observed['Architecture'] != 'amd64'
        if select_platform:
            # Needed for mixed-platform containerd stores; legacy AMD64 stores lack this flag.
            observed = json.loads(run(['docker', 'image', 'inspect', '--platform', 'linux/amd64', image]).stdout)[0]
        if observed['Architecture'] != 'amd64' or observed['Os'] != 'linux' or canonical_digest(image) not in {canonical_digest(x) for x in observed.get('RepoDigests', [])}:
            raise ValueError('Registry digest or architecture does not match approved pin')
        archive = root / (label + '.tar')
        # Docker save requires a name/tag; a digest-only pull often has no tag.
        tag = 'dawei-transfer/' + label + ':' + observed['Id'].split(':')[1][:20]
        # A multi-platform local store may also contain ARM64 under the same digest.
        run(['docker', 'tag', image, tag])
        run(['docker', 'save', *(['--platform', 'linux/amd64'] if select_platform else []), '--output', str(archive), tag])
        receipt['images'].append({'kind': label, 'registry_digest': image, 'image_config_digest': observed['Id'],
                                  'tag': tag, 'archive': archive.name, 'archive_sha256': digest(archive)})
    (root / 'image-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Pinned image archives and receipt prepared privately. Transfer over authenticated IAP/SSH; not a deployment.')


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print('Image transfer preparation refused: ' + str(error))
        raise SystemExit(1)
    except (OSError, KeyError, subprocess.SubprocessError):
        print('Image transfer preparation stopped safely; no private command output printed.')
        raise SystemExit(1)
