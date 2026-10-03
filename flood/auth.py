"""Individual local identity, password hashing and revocable server-side sessions."""
import hashlib
import hmac
import secrets
import time
from .domain import DomainError, now
from .repository import Repository, uid

ROLES = {"contributor", "reviewer", "analyst", "coordinator", "administrator"}
ITERATIONS = 600_000

def password_hash(password: str) -> str:
    if len(password) < 12 or len(password) > 512:
        raise DomainError("Use a password of 12–512 characters")
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${value}"

def check_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        value = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return algorithm == "pbkdf2_sha256" and hmac.compare_digest(value, digest)
    except (ValueError, TypeError):
        return False

def create_user(repo: Repository, username: str, role: str, password: str) -> str:
    if role not in ROLES or not username.strip() or len(username) > 100:
        raise DomainError("Invalid username or role")
    user_id = uid("USR")
    encoded = password_hash(password)
    with repo.transaction() as db:
        db.execute("INSERT INTO users VALUES(?,?,?,?,1)", (user_id, username.strip(), role, encoded))
        repo.audit(db, "local-admin-cli", "UserCreated", user_id, None, {"username":username,"role":role}, "Individual account provisioning")
    return user_id

def login(repo: Repository, username: str, password: str) -> tuple[str,dict]:
    rows = repo.rows("SELECT * FROM users WHERE username=? AND active=1", (username,))
    # Same slow hash path when identity is absent.
    dummy = f"pbkdf2_sha256${ITERATIONS}$" + "00"*16 + "$" + "00"*32
    valid = check_password(password, rows[0]["password_hash"] if rows else dummy)
    if not rows or not valid:
        with repo.transaction() as db:repo.audit(db,"unauthenticated","LoginFailed",hashlib.sha256(username.casefold().encode()).hexdigest(),None,None,"Invalid credentials; no password retained")
        raise DomainError("Invalid username or password", 401)
    user = rows[0]
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with repo.transaction() as db:
        db.execute("DELETE FROM sessions WHERE expires<?",(time.time(),))
        db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], csrf, time.time()+8*3600))
        repo.audit(db, user["id"], "Login", user["id"], None, None, "Authenticated")
    return token, {"id": user["id"], "username":user["username"], "role":user["role"], "csrf":csrf,"read_only":False}

def session(repo: Repository, token: str) -> dict:
    rows = repo.rows("SELECT u.id,u.username,u.role,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.active=1", (hashlib.sha256(token.encode()).hexdigest(),time.time()))
    if not rows:
        raise DomainError("Sign in to continue", 401)
    return {**rows[0], "read_only":False}


def throttle(repo, address, username):
    """Atomic persistent buckets survive worker restarts; labels reveal no account/IP."""
    current = time.time()
    keys = [("identity:"+username.casefold(), 5), ("address:"+address, 30)]
    with repo.transaction() as db:
        db.execute("DELETE FROM login_buckets WHERE started<?", (current-60,))
        for label, limit in keys:
            key = hashlib.sha256(label.encode()).hexdigest()
            row = db.execute("SELECT attempts FROM login_buckets WHERE key=?", (key,)).fetchone()
            if row and row[0] >= limit:
                raise DomainError("Too many login attempts; retry after one minute", 429)
        for label, _ in keys:
            key = hashlib.sha256(label.encode()).hexdigest()
            db.execute("INSERT INTO login_buckets VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET attempts=attempts+1", (key,current))


def deactivate_user(repo, user_id, actor, role, reason):
    from .repository import permit
    permit(role, set())
    if not reason.strip():
        raise DomainError("An account change reason is required")
    with repo.transaction() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise DomainError("User not found",404)
        if row["role"] == "administrator" and row["active"] and db.execute("SELECT COUNT(*) FROM users WHERE active=1 AND role='administrator'").fetchone()[0] <= 1:
            raise DomainError("Cannot deactivate the last active administrator",409)
        db.execute("UPDATE users SET active=0 WHERE id=?", (user_id,))
        db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        repo.audit(db,actor,"UserDeactivated",user_id,{"active":row["active"]},{"active":0},reason)
