"""Single-host OS locks prevent concurrent consumers of one persistent database."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
from .domain import DomainError

@contextmanager
def worker_lock(repo,kind):
    path=Path(repo.path).parent/('.'+kind+'.lock')
    with path.open('a') as file:
        try: fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise DomainError('Another '+kind+' worker is active') from None
        try: yield
        finally: fcntl.flock(file,fcntl.LOCK_UN)
