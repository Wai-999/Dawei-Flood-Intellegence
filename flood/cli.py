import argparse
import getpass
import json
import os
from pathlib import Path
import sqlite3
from .auth import create_user, ROLES
from .domain import DomainError, now
from .repository import Repository, ROOT, dump

def database_path():
    return Path(os.environ.get("FLOOD_DATABASE", ROOT / "data/flood.sqlite3"))

def check_backup(path: Path) -> dict:
    if not path.is_file():
        raise DomainError("Backup file does not exist")
    db=sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True)
    try:
        integrity=db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign=db.execute("PRAGMA foreign_key_check").fetchall()
        if integrity!="ok" or foreign:
            raise DomainError("Backup failed integrity or foreign-key validation")
        queries={"locations":"SELECT COUNT(*) FROM locations","assessments":"SELECT COUNT(*) FROM assessments","submissions":"SELECT COUNT(*) FROM submissions","assessment_versions":"SELECT COUNT(*) FROM assessment_versions","audit_events":"SELECT COUNT(*) FROM audit_events","assistance_events":"SELECT COUNT(*) FROM assistance_events"}
        counts={name:db.execute(sql).fetchone()[0] for name,sql in queries.items()}
        return {"integrity":integrity,"counts":counts}
    finally:
        db.close()

def backup(repo: Repository, output: Path) -> dict:
    if output.exists():
        raise DomainError("Backup destination already exists; choose a new path")
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("xb") as new_file: pass
    os.chmod(output,0o600)
    src=repo.connect()
    dst=sqlite3.connect(output)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
    finally:
        src.close();dst.close()
    result=check_backup(output)
    with repo.transaction() as db:
        db.execute("INSERT OR REPLACE INTO integration_state VALUES('last_backup',?,?)",(dump(result),now()))
        repo.audit(db,"local-admin-cli","BackupCreated","database",None,result,"Consistent SQLite backup")
    return result

def main():
    parser=argparse.ArgumentParser(description="Flood intelligence local operations")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("init")
    user=sub.add_parser("create-user");user.add_argument("--username",required=True);user.add_argument("--role",choices=sorted(ROLES),required=True)
    b=sub.add_parser("backup");b.add_argument("--output",type=Path,required=True)
    c=sub.add_parser("check-backup");c.add_argument("--input",type=Path,required=True)
    r=sub.add_parser("restore");r.add_argument("--input",type=Path,required=True);r.add_argument("--output",type=Path,required=True)
    retry=sub.add_parser("retry-failed");retry.add_argument("--kind",choices=['sheets','feedback'],required=True);retry.add_argument("--reason",required=True)
    args=parser.parse_args()
    if args.command=="check-backup":
        print(json.dumps(check_backup(args.input)));return
    if args.command=="restore":
        expected=check_backup(args.input)
        if args.output.exists():raise DomainError("Restore cannot overwrite an existing file")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        src=sqlite3.connect(f"file:{args.input.resolve()}?mode=ro",uri=True);dst=sqlite3.connect(args.output)
        os.chmod(args.output,0o600)
        try:src.backup(dst)
        finally:src.close();dst.close()
        result=check_backup(args.output)
        if result!=expected:raise DomainError("Restored counts differ from backup")
        print(json.dumps(result));return
    repo=Repository(database_path(),migrate=args.command!="backup")
    if args.command=="init":
        source_directory=Path(os.environ.get("FLOOD_SOURCE_DIRECTORY",ROOT/"data"))
        snapshot=source_directory/"source_snapshot.json";profile=source_directory/"source_profile.json"
        result=repo.import_snapshot(json.loads(snapshot.read_text()),json.loads(profile.read_text())) if snapshot.exists() else {"initialized":True,"source":"No snapshot supplied"}
        print(json.dumps(result))
    elif args.command=="create-user":
        password=getpass.getpass("New individual password: ")
        if getpass.getpass("Confirm password: ")!=password:raise DomainError("Passwords differ")
        print(create_user(repo,args.username,args.role,password))
    elif args.command=="backup":
        print(json.dumps(backup(repo,args.output)))
    elif args.command=="retry-failed":
        if not args.reason.strip() or len(args.reason)>1000:raise DomainError('A bounded operator reason is required')
        with repo.transaction() as db:
            if args.kind=='sheets':
                ids=[row[0] for row in db.execute("SELECT id FROM outbox WHERE status='failed'")]
                db.execute("UPDATE outbox SET status='pending',attempts=0,last_error=NULL WHERE status='failed'")
            else:
                ids=[row[0] for row in db.execute('SELECT id FROM feedback WHERE sent_at IS NULL AND attempts>0')]
                db.execute('UPDATE feedback SET attempts=0,last_error=NULL WHERE sent_at IS NULL AND attempts>0')
            repo.audit(db,'local-admin-cli','FailedJobsRequeued',args.kind,None,{'ids':ids},args.reason)
        print(json.dumps({'requeued':len(ids)}))

if __name__=="__main__":main()
