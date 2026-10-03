"""Fail closed on tracked private artifacts and recognizable credential patterns."""
from pathlib import Path
import re
import subprocess
import sys

PATTERNS={
    'private key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'Telegram token':re.compile(r'\b\d{6,12}:[A-Za-z0-9_-]{30,}\b'),
    'AWS access key':re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'service account key':re.compile(r'"private_key"\s*:\s*"[^"\s]{20,}'),
}
DENIED_PREFIXES=('data/','outputs/','secrets/','backups/','.venv/','node_modules/')
DENIED_SUFFIXES=('.sqlite3','.sqlite3-wal','.sqlite3-shm','.xlsx','.tar.gz','.pem','.key','.p12')

def scan(paths):
    failures=[]
    for path in paths:
        name=str(path).replace('\\','/')
        if name.startswith(DENIED_PREFIXES) or name.endswith(DENIED_SUFFIXES) or Path(name).name.startswith('.env') and Path(name).name!='.env.example':
            failures.append((name,'private artifact'));continue
        file=Path(path)
        if file.is_symlink(): failures.append((name,'symlink'));continue
        try: content=file.read_text(encoding='utf-8')
        except UnicodeDecodeError: failures.append((name,'unreviewed binary'));continue
        for label,pattern in PATTERNS.items():
            if pattern.search(content): failures.append((name,label))
    return failures

if __name__=='__main__':
    paths=subprocess.check_output(['git','ls-files','-z'],text=True).split('\0')
    failures=scan([p for p in paths if p])
    for name,label in failures:print(name+': '+label) # Never print matched credential contents.
    print('Secret/privacy scan: '+('FAILED' if failures else 'PASS'))
    sys.exit(bool(failures))
