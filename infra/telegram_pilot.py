"""Opt-in, isolated operator exercise using the approved single Telegram poller.

Only conversation storage changes after an explicitly approved operator sends
/pilot_start. Transport, authorization, retry and offset handling stay in the
approved application. Test storage is never mounted into the app or Sheets.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flood.domain import DomainError
from flood.repository import Repository
from flood.telegram import Conversation


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Pilot deadline requires timezone")
    return result.astimezone(timezone.utc)


class PilotConversation:
    def __init__(self, production, isolated, config, clock=None):
        if Path(production.path).resolve() == Path(isolated.path).resolve():
            raise ValueError("Pilot database must be separate")
        if config.get("scope") != "descriptive-only isolated technical exercise":
            raise ValueError("Explicit technical exercise scope required")
        seconds = config.get("session_seconds")
        if type(seconds) is not int or not 60 <= seconds <= 3600:
            raise ValueError("Pilot session must be bounded to one hour")
        self.deadline = utc(config["authorization_expires_at"])
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.production = production
        self.isolated = isolated
        self.seconds = seconds
        self.operator = config["operator"]
        owners = production.rows("SELECT id,role FROM users WHERE username=? AND active=1", (self.operator,))
        if len(owners) != 1:
            raise ValueError("Approved operator must already exist")
        self.actor, self.role = owners[0]["id"], owners[0]["role"]
        shadow = isolated.rows("SELECT id,role FROM users WHERE id=? AND username=? AND active=1", (self.actor, self.operator))
        if len(shadow) != 1 or shadow[0]["role"] != self.role:
            raise ValueError("Isolated operator must match existing authorization")
        self.normal = Conversation(production)
        self.exercise = Conversation(isolated)

    def session(self):
        rows = self.isolated.rows("SELECT value FROM integration_state WHERE key='technical_pilot_session'")
        return json.loads(rows[0]["value"]) if rows else {"active": False}

    def save(self, value):
        from flood.integrations import state
        state(self.isolated, "technical_pilot_session", value)

    def handle(self, actor, role, text, update_id):
        command = text.strip()
        if actor != self.actor or role != self.role:
            if command in ("/pilot_start", "/pilot_end"):
                raise DomainError("This technical exercise is not authorized for your account")
            return self.normal.handle(actor, role, text, update_id)
        session = self.session()
        if command in ("/pilot_start", "/pilot_end"):
            # Preserve the control reply after send failure or process restart.
            if session.get("control_update_id") == update_id:
                return session["control_reply"]
            if command == "/pilot_end":
                reply = "Technical exercise ended. Test records remain isolated. Ordinary intake has resumed."
                session.update(active=False)
            else:
                if self.clock() >= self.deadline:
                    raise DomainError("Technical exercise authorization has expired")
                if session.get("active"):
                    return "Technical exercise already active; use /pilot_end before starting another session."
                session.update(active=True, expires_at=min(self.deadline, self.clock()+timedelta(seconds=self.seconds)).isoformat())
                reply = "TECHNICAL TEST — isolated database, no real disaster claims. Send /new to begin. Use /pilot_end when finished. This session lasts at most one hour."
            session.update(control_update_id=update_id, control_reply=reply)
            self.save(session)
            return reply
        if session.get("active"):
            if self.clock() >= min(self.deadline, utc(session["expires_at"])):
                # Never fall through to operational ingestion after expiry.
                return "Technical exercise expired. No report was submitted. Send /pilot_end to leave test mode."
            try:
                return "TECHNICAL TEST — isolated data.\n" + self.exercise.handle(actor, role, text, update_id)
            except DomainError as exc:
                raise DomainError("TECHNICAL TEST — " + str(exc)) from exc
        return self.normal.handle(actor, role, text, update_id)


def install(config_path):
    """Install into the imported approved integration module, without another poller."""
    from flood import integrations
    path = Path(config_path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("Private regular pilot configuration required")
    config = json.loads(path.read_text())
    isolated_path = Path(config["database"])
    if isolated_path.parent != Path("/run/pilot-data") or isolated_path.is_symlink() or not isolated_path.is_file():
        raise ValueError("Existing isolated worker-only database required")
    isolated = Repository(isolated_path, migrate=False)
    integrations.Conversation = lambda production: PilotConversation(production, isolated, config)
    integrations.main()
