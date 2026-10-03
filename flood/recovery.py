"""Verified private backup bundles with source snapshots and checksummed manifests."""
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
import json
import os
from pathlib import Path
import re
import shutil
import signal
import tarfile
import tempfile
import time
from .cli import backup, check_backup, database_path
from .domain import DomainError, now
from .integrations import state
from .repository import Repository, ROOT, dump

SOURCE_FILES = ('source_snapshot.json','source_profile.json','source-original.xlsx')


def sha(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file,'sha256').hexdigest()


def signing_key():
    path=os.environ.get("FLOOD_BACKUP_SIGNING_KEY_FILE")
    if not path:
        if os.environ.get("FLOOD_ENV")=="production": raise DomainError("Production backup signing key is not configured")
        return None
    key=Path(path).read_bytes()
    if not 32<=len(key)<=64: raise DomainError("Backup signing key must contain 32–64 private bytes")
    return key


def seal(manifest):
    key=signing_key()
    if key:
        manifest["key_id"]=hashlib.sha256(key).hexdigest()[:16]
        manifest["signature"]=hmac.new(key,dump(manifest).encode(),hashlib.sha256).hexdigest()
    return manifest


def verify_seal(manifest):
    key=signing_key()
    if key:
        unsigned={k:v for k,v in manifest.items() if k!="signature"}
        expected=hmac.new(key,dump(unsigned).encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,str(manifest.get("signature",""))): raise DomainError("Backup signature mismatch")
    elif manifest.get("signature"): raise DomainError("Configure the trusted signing key to verify this backup")


def bundle(repo, destination, source_directory):
    destination=Path(destination)
    if destination.exists(): raise DomainError('Backup destination exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
            staging=Path(staging)
            verification=backup(repo,staging/'database.sqlite3')
            for name in SOURCE_FILES:
                source=Path(source_directory)/name
                if source.is_file() and not source.is_symlink(): shutil.copyfile(source,staging/name)
            files={p.name:sha(p) for p in staging.iterdir() if p.name in {"database.sqlite3",*SOURCE_FILES}}
            (staging/'manifest.json').write_text(dump(seal({'created_at':now(),'schema_version':2,'files':files,'verification':verification})))
            temporary=destination.with_name(destination.name+'.partial')
            try:
                with tarfile.open(temporary,'w:gz') as archive:
                    for name in [*files,"manifest.json"]: archive.add(staging/name,arcname=name,recursive=False)
                os.chmod(temporary,0o600)
                inspect_bundle(temporary)
                os.replace(temporary,destination)
            finally:
                temporary.unlink(missing_ok=True)
        state(repo,'last_bundle',{'status':'HEALTHY','created_at':now(),'database':verification,'source_snapshots':len(files)-1})
        return verification
    except Exception:
        state(repo,'last_bundle',{'status':'FAILED','created_at':now(),'error':'Backup bundle failed'})
        raise


def _unpack(path, destination):
    allowed={'database.sqlite3','manifest.json',*SOURCE_FILES}
    with tarfile.open(path,'r:gz') as archive:
        members=archive.getmembers()
        if len(members)>len(allowed) or len({m.name for m in members})!=len(members): raise DomainError('Invalid backup members')
        if any(m.name not in allowed or not m.isfile() or m.size>1024**3 for m in members): raise DomainError('Unsafe backup member')
        for member in members:
            stream=archive.extractfile(member)
            with (destination/member.name).open('xb') as output: shutil.copyfileobj(stream,output)
            os.chmod(destination/member.name,0o600)
    manifest=json.loads((destination/'manifest.json').read_text())
    verify_seal(manifest)
    files=manifest.get('files',{})
    actual={p.name for p in destination.iterdir()}-{'manifest.json'}
    if set(files)!=actual or 'database.sqlite3' not in actual: raise DomainError('Backup manifest mismatch')
    if any(sha(destination/name)!=digest for name,digest in files.items()): raise DomainError('Backup checksum mismatch')
    result=check_backup(destination/'database.sqlite3')
    if result!=manifest['verification']: raise DomainError('Restored database counts differ from manifest')
    return manifest


def inspect_bundle(path):
    with tempfile.TemporaryDirectory(dir=Path(path).parent) as directory: return _unpack(path,Path(directory))


def restore_bundle(path, destination):
    destination=Path(destination)
    if destination.exists(): raise DomainError('Restore destination must be a new directory')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        manifest=_unpack(path,Path(staging))
        destination.mkdir(mode=0o700)
        for file in Path(staging).iterdir(): shutil.copyfile(file,destination/file.name);os.chmod(destination/file.name,0o600)
    return manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['once','worker','inspect','restore','keygen'])
    parser.add_argument('--path',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.command=='keygen':
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('xb') as file:file.write(secrets.token_bytes(32))
        os.chmod(args.output,0o600)
        print('Backup signing key created privately. Keep old keys during rotation.');return
    if args.command=='inspect': print(dump(inspect_bundle(args.path)));return
    if args.command=='restore': print(dump(restore_bundle(args.path,args.output)));return
    repo=Repository(database_path())
    folder=Path(os.environ.get('FLOOD_BACKUP_DIRECTORY',Path(repo.path).parent/'backups'))
    source=Path(os.environ.get('FLOOD_SOURCE_DIRECTORY',ROOT/'data'))
    interval=int(os.environ.get('FLOOD_BACKUP_INTERVAL_SECONDS','3600'))
    retention=int(os.environ.get('FLOOD_BACKUP_RETENTION_DAYS','30'))
    if interval<60 or retention<1: raise DomainError('Invalid backup schedule')
    running=True
    def stop(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    from .workers import worker_lock
    with worker_lock(repo,'backup'):
        while running:
            try:
                name=datetime.now(timezone.utc).strftime('flood-%Y%m%dT%H%M%S%fZ.tar.gz')
                output=args.output or folder/name
                bundle(repo,output,source)
                # Delete only owned, verified bundles after a successful new backup.
                for file in folder.glob('flood-*.tar.gz'):
                    if re.fullmatch(r'flood-\d{8}T\d{12}Z\.tar\.gz',file.name) and time.time()-file.stat().st_mtime>retention*86400:
                        inspect_bundle(file);file.unlink()
                state(repo,'backup_worker',{'status':'HEALTHY','time':now()})
                print(dump({'event':'backup','status':'HEALTHY','time':now()}),flush=True)
            except Exception:
                state(repo,'backup_worker',{'status':'FAILED','error':'Backup failed','time':now()})
                print(dump({'event':'backup','status':'FAILED','time':now()}),flush=True)
                if args.command=='once': raise SystemExit(1)
            if args.command=='once': break
            deadline=time.monotonic()+interval
            while running and time.monotonic()<deadline: time.sleep(min(1,deadline-time.monotonic()))


if __name__=='__main__':main()
