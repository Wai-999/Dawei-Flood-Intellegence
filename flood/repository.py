"""Transactional canonical storage. No network effects occur inside a transaction."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterator
import uuid
from .domain import COUNTS, ENUMS, DomainError, identity, now, public_report, validate, parse_structured, parse_compact

ROOT = Path(__file__).resolve().parent.parent

def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def uid(prefix: str) -> str:
    return prefix + "-" + uuid.uuid4().hex[:20]

def permit(role: str, allowed: set[str]) -> None:
    if role not in allowed and role != "administrator":
        raise DomainError("This role cannot perform that action", 403)

class Repository:
    def __init__(self, path: str | Path, *, migrate: bool = True):
        self.path = str(path)
        self._local = threading.local()
        if not migrate and not Path(path).is_file(): raise DomainError("Database does not exist")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        db = self.connect()
        try:
            current = db.execute("PRAGMA user_version").fetchone()[0]
            if current > 2:
                raise DomainError("Database schema is newer than this application")
            for version, name in ((1, "001_initial.sql"), (2, "002_operations.sql")):
                if migrate and version > current:
                    db.executescript("BEGIN IMMEDIATE;\n" + (ROOT / "database/migrations" / name).read_text() + "\nCOMMIT;")
        finally:
            db.close()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=20)
        os.chmod(self.path,0o600)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        active = getattr(self._local,"connection",None)
        if active is not None:
            point="sp_"+uuid.uuid4().hex
            active.execute("SAVEPOINT "+point)
            try:
                yield active
                active.execute("RELEASE "+point)
            except BaseException:
                active.execute("ROLLBACK TO "+point)
                active.execute("RELEASE "+point)
                raise
            return
        db = self.connect()
        self._local.connection = db
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            del self._local.connection
            db.close()

    def rows(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        active=getattr(self._local,"connection",None)
        db=active or self.connect()
        try: return [dict(r) for r in db.execute(sql,args)]
        finally:
            if active is None: db.close()

    def audit(self, db: sqlite3.Connection, actor: str, action: str, entity: str, old: Any, new: Any, reason: str) -> None:
        db.execute("INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?)", (uid("EVT"), actor, action, entity,
                   dump(old), dump(new), reason, now()))

    def locations(self) -> list[dict[str, Any]]:
        rows = self.rows("SELECT * FROM locations ORDER BY township,village,id")
        for row in rows:
            row["flags"] = json.loads(row["flags"])
        return rows

    def _location(self, db: sqlite3.Connection, data: dict[str, Any]) -> str:
        if data.get("location_id"):
            row = db.execute("SELECT * FROM locations WHERE id=?", (data["location_id"],)).fetchone()
            if not row:
                raise DomainError("Unknown location_id; location matching requires review")
            for key in ("state_region", "township", "village"):
                if data.get(key) and identity(data[key]) != identity(row[key]):
                    raise DomainError(f"{key} conflicts with selected location")
                data[key] = row[key]
            return str(row["id"])
        key = "|".join(identity(data[k]) for k in ("state_region", "township", "village"))
        matches = list(db.execute("SELECT id FROM locations WHERE identity_key=?", (key,)))
        if len(matches) > 1:
            raise DomainError("Ambiguous location identity: select a reviewed location_id")
        if matches:
            return str(matches[0]["id"])
        location_id = "LOC-" + hashlib.sha256(key.encode()).hexdigest()[:20]
        db.execute("INSERT INTO locations(id,state_region,district,township,village,identity_key,flags) VALUES(?,?,?,?,?,?,?)",
                   (location_id, data["state_region"], data.get("district"), data["township"], data["village"], key, '["registry_unconfirmed"]'))
        return location_id

    def _source(self, db: sqlite3.Connection, data: dict[str, Any]) -> str:
        ref = data.get("source_reference") or "unspecified imported source"
        group = data.get("independence_group") or ref
        source_id = "SRC-" + hashlib.sha256((ref + "|" + group).encode()).hexdigest()[:20]
        db.execute("INSERT OR IGNORE INTO sources VALUES(?,?,?,?)", (source_id, ref, group, dump({"type": data.get("source_type", "reported")})))
        return source_id

    def _version(self, db: sqlite3.Connection, report_id: str, version: int, data: dict, flags: list, actor: str, reason: str) -> None:
        fields=COUNTS | set(ENUMS) | {"latitude","longitude"}
        data["field_observed_at"]={**{field:data.get("observed_at") for field in fields if data.get(field) is not None and data.get("observed_at")},**data.get("field_observed_at",{})}
        db.execute("INSERT INTO assessment_versions VALUES(?,?,?,?,?,?,?)", (report_id, version, dump(data), dump(flags), actor, reason, now()))
        source_id = self._source(db, data)
        for field in sorted(COUNTS | set(ENUMS) | {"latitude", "longitude"}):
            value = data.get(field)
            missing = None if value is not None else data.get("missingness", {}).get(field, "not_assessed")
            db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?)", (uid("OBS"), report_id, version, field,
                       dump(value) if value is not None else None, missing, data.get("field_observed_at",{}).get(field,data.get("observed_at")), data.get("reported_at") or now(), source_id))

    def _retain(self, payload, raw, actor, role, key, channel, digest=None):
        permit(role, {"contributor", "reviewer", "coordinator"})
        if not isinstance(key, str) or not 8 <= len(key) <= 200:
            raise DomainError("An idempotency key of 8–200 characters is required")
        if not isinstance(raw, str) or len(raw.encode()) > 65536:
            raise DomainError("Raw submission must be text within 64 KiB")
        scoped = actor + ":" + key
        digest = digest or hashlib.sha256(dump({"payload":payload,"raw":raw}).encode()).hexdigest()
        with self.transaction() as db:
            old = db.execute("SELECT * FROM submissions WHERE idempotency_key=?", (scoped,)).fetchone()
            if old and old["sha256"] != digest:
                raise DomainError("Idempotency key reused with different content",409)
            if not old:
                submission_id = uid("SUB")
                db.execute("INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?)",(submission_id,scoped,actor,channel,now(),raw,digest,"parser-1.0"))
            else:
                submission_id = old["id"]
            record = db.execute("SELECT id FROM assessments WHERE submission_id=?",(submission_id,)).fetchone()
            rejected = db.execute("SELECT 1 FROM audit_events WHERE entity=? AND action='ValidationRejected'",(scoped,)).fetchone()
            if rejected and not record:
                raise DomainError("This submission was rejected; correct it and use a new key",409)
        return submission_id, digest, record["id"] if record else None

    def _reject(self, actor, key, exc):
        with self.transaction() as db:
            entity = actor+":"+key
            if not db.execute("SELECT 1 FROM audit_events WHERE entity=? AND action='ValidationRejected'",(entity,)).fetchone():
                self.audit(db,actor,"ValidationRejected",entity,None,{"error":str(exc)},"Original raw retained; no canonical values written")

    def ingest(self, payload, raw, actor, role, key, channel="web"):
        original = raw if isinstance(raw,str) else dump(payload)
        _, digest, existing = self._retain(payload,original,actor,role,key,channel)
        if existing:
            return self.report(existing,actor,role)
        try:
            parsed = (parse_compact(raw) if raw.startswith("FR|") else parse_structured(raw)) if isinstance(raw,str) and payload is None else payload
        except DomainError as exc:
            self._reject(actor,key,exc)
            raise
        return self.submit(parsed,original,actor,role,key,channel,_digest=digest)

    def submit(self, payload: dict, raw: str, actor: str, role: str, key: str, channel: str = "web", *, imported: bool = False, _digest=None) -> dict:
        submission_id, digest, replay_id = self._retain(payload,raw,actor,role,key,channel,_digest)
        if replay_id:
            return self.report(replay_id,actor,role)
        try:
            data, flags = validate(payload,imported=imported)
            with self.transaction() as db:
                # The raw input already exists; canonical creation rechecks under a write lock.
                record = db.execute("SELECT id FROM assessments WHERE submission_id=?",(submission_id,)).fetchone()
                if record:
                    report_id = record["id"]
                else:
                    location_id = self._location(db,data)
                    data["location_id"] = location_id
                    recent = db.execute("SELECT a.id,v.payload FROM assessments a JOIN assessment_versions v ON v.report_id=a.id AND v.version=a.current_version WHERE a.location_id=? AND a.status NOT IN ('rejected','superseded')",(location_id,)).fetchall()
                    for row in recent:
                        previous = json.loads(row["payload"])
                        if previous.get("observed_at") == data.get("observed_at"):
                            flags.append("possible_duplicate_same_location_time")
                            if any(previous.get(field) is not None and data.get(field) is not None and previous[field] != data[field] for field in COUNTS | set(ENUMS)):
                                flags.append("conflicting_observation_same_location_time")
                    flags = sorted(set(flags))
                    report_id, time = uid("RPT"), now()
                    db.execute("INSERT INTO assessments VALUES(?,?,?,?,?,?,?,?)",(report_id,location_id,submission_id,actor,"needs_review" if flags or imported else "submitted",1,time,time))
                    self._version(db,report_id,1,data,flags,actor,"Imported provisional source" if imported else "New observation")
                    self.audit(db,actor,"NeedReported",report_id,None,data,"Received; not verified")
                    self._feedback(db,actor,report_id,"received","Submission received; review pending.")
        except DomainError as exc:
            self._reject(actor,key,exc)
            raise
        return self.report(report_id,actor,role)

    def _feedback(self, db, actor, report_id, event, message):
        if db.execute("SELECT 1 FROM users WHERE id=? AND active=1",(actor,)).fetchone():
            db.execute("INSERT INTO feedback(id,actor,report_id,event,message,created_at) VALUES(?,?,?,?,?,?)",(uid("FDB"),actor,report_id,event,message,now()))

    def feedback_for(self, actor, role):
        return self.rows("SELECT id,report_id,event,message,created_at,sent_at FROM feedback WHERE actor=? ORDER BY created_at DESC LIMIT 100",(actor,))

    def _location_feedback(self, db, location_id, event, message):
        for row in db.execute("SELECT DISTINCT owner,id FROM assessments WHERE location_id=?",(location_id,)).fetchall():
            self._feedback(db,row["owner"],row["id"],event,message)

    def add_evidence(self, report_id, data, actor, role):
        permit(role,{"contributor","reviewer"})
        self.report(report_id,actor,role) # Includes contributor ownership restriction.
        reference, kind = data.get("reference"), data.get("evidence_type","source_reference")
        if not isinstance(reference,str) or not reference.strip() or len(reference)>2000 or kind not in {"source_reference","photo_reference","document_reference","field_confirmation","correction"}:
            raise DomainError("Provide a bounded evidence reference and supported evidence type")
        eid = uid("EVD")
        with self.transaction() as db:
            source_id = self._source(db,{"source_reference":reference})
            db.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?)",(eid,report_id,source_id,reference,kind,None))
            self.audit(db,actor,"EvidenceSubmitted",report_id,None,{"id":eid,"reference":reference,"type":kind},"Evidence requires human review")
        return eid

    def reports(self, actor: str, role: str, filters: dict | None = None, *, restricted: bool = False) -> list[dict]:
        filters = filters or {}
        rows = self.rows("SELECT a.*,v.payload,v.flags,l.village,l.township,l.state_region FROM assessments a JOIN assessment_versions v ON v.report_id=a.id AND v.version=a.current_version JOIN locations l ON l.id=a.location_id ORDER BY a.received_at DESC,a.id")
        result = []
        for row in rows:
            if role == "contributor" and row["owner"] != actor:
                continue
            if filters.get("status") and row["status"] != filters["status"]:
                continue
            if filters.get("township") and row["township"] != filters["township"]:
                continue
            if filters.get("q") and identity(filters["q"]) not in identity(" ".join(str(row[k]) for k in ("village", "township", "id", "location_id"))):
                continue
            payload = json.loads(row.pop("payload"))
            observed = payload.get("observed_at")
            if filters.get("from") and (not observed or observed[:10] < filters["from"]):
                continue
            if filters.get("to") and (not observed or observed[:10] > filters["to"]):
                continue
            row["flags"] = json.loads(row["flags"])
            row["data"] = payload if restricted and role in {"reviewer", "administrator"} else public_report(payload)
            row.pop("owner", None)
            result.append(row)
        return result

    def report(self, report_id: str, actor: str, role: str) -> dict:
        rows = [r for r in self.reports(actor, role, restricted=True) if r["id"] == report_id]
        if not rows:
            raise DomainError("Report not found", 404)
        row = rows[0]
        versions = self.rows("SELECT version,payload,flags,actor,reason,created_at FROM assessment_versions WHERE report_id=? ORDER BY version", (report_id,))
        for v in versions:
            data = json.loads(v.pop("payload"))
            v["data"] = data if role in {"reviewer", "administrator"} else public_report(data)
            v["flags"] = json.loads(v["flags"])
        row["history"] = versions
        row["duplicate_resolutions"] = self.rows("SELECT source_report,target_report,reason,created_at FROM report_links WHERE source_report=? OR target_report=?",(report_id,report_id))
        verification=self.rows("SELECT MAX(created_at) AS verified_at FROM verifications WHERE report_id=? AND version=? AND decision='verified'",(report_id,row["current_version"]))
        row["review_history"]=self.rows("SELECT version,decision,reason,created_at FROM verifications WHERE report_id=? ORDER BY created_at",(report_id,))
        row["verified_at"]=verification[0]["verified_at"] if row["status"]=="verified" else None
        if role in {"reviewer", "administrator"}:
            row["raw_claims"] = self.rows("SELECT * FROM claims WHERE report_id=?", (report_id,))
            row["evidence"] = self.rows("SELECT * FROM evidence WHERE report_id=?",(report_id,))
            row["claim_resolutions"] = self.rows("SELECT * FROM claim_resolutions WHERE report_id=?",(report_id,))
            row["raw_submission"] = self.rows("SELECT id,raw,sha256,channel,received_at FROM submissions WHERE id=?", (row["submission_id"],))[0]
        return row

    def update(self, report_id: str, patch: dict, actor: str, role: str, reason: str, expected_version: int, raw: str | None = None) -> dict:
        permit(role, {"contributor", "reviewer"})
        if not reason.strip():
            raise DomainError("Correction reason is required")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM assessments WHERE id=?", (report_id,)).fetchone()
            if not row:
                raise DomainError("Report not found", 404)
            if role == "contributor" and row["owner"] != actor:
                raise DomainError("Cannot update another contributor's report", 403)
            if row["current_version"] != expected_version:
                raise DomainError("Report changed; reload before editing", 409)
            old = json.loads(db.execute("SELECT payload FROM assessment_versions WHERE report_id=? AND version=?", (report_id, expected_version)).fetchone()[0])
            combined = {**old, **patch}
            # A known replacement clears the prior missingness state for that field.
            missingness = {**old.get("missingness", {}), **patch.get("missingness", {})}
            for field, value in patch.items():
                if field != "missingness" and value is not None:
                    missingness.pop(field, None)
            combined["missingness"] = missingness
            field_times = {**old.get("field_observed_at",{}),**patch.get("field_observed_at",{})}
            for field in COUNTS|set(ENUMS)|{"latitude","longitude"}:
                if field in patch and field not in patch.get("field_observed_at",{}) and combined.get("observed_at"):
                    field_times[field]=combined["observed_at"]
            combined["field_observed_at"]=field_times
            data, flags = validate(combined)
            if data.get("location_id") != old["location_id"]:
                raise DomainError("Location reassignment requires a separate identity resolution")
            self._location(db, data)
            version = expected_version + 1
            self._version(db, report_id, version, data, flags, actor, reason)
            original_edit = raw if raw is not None else dump(patch)
            db.execute("INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?)", (uid("SUB"), actor+":correction:"+report_id+":"+str(version), actor, "correction", now(), original_edit, hashlib.sha256(original_edit.encode()).hexdigest(), "parser-1.0"))
            db.execute("UPDATE assessments SET current_version=?,status='needs_review',updated_at=? WHERE id=?", (version, now(), report_id))
            self.audit(db, actor, "ObservationCorrected", report_id, old, data, reason)
            self._feedback(db,row["owner"],report_id,"correction_accepted","Correction accepted as a new version; review pending.")
            if row["status"] == "verified":
                db.execute("INSERT INTO outbox(id,kind,payload,created_at) VALUES(?,?,?,?)", (uid("JOB"), "sheets_projection", dump({"report_id": report_id, "version": version, "action": "review_reopened"}), now()))
        return self.report(report_id, actor, role)

    def review(self, report_id: str, decision: str, actor: str, role: str, reason: str, evidence: str, version: int) -> dict:
        permit(role, {"reviewer"})
        if decision not in {"verified", "rejected", "needs_review", "superseded"} or not reason.strip():
            raise DomainError("Choose a review decision and provide a reason")
        if decision == "verified" and not evidence.strip():
            raise DomainError("Verification requires selected evidence")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM assessments WHERE id=?", (report_id,)).fetchone()
            if not row:
                raise DomainError("Report not found", 404)
            if row["current_version"] != version:
                raise DomainError("Report changed; review the current version", 409)
            flags = json.loads(db.execute("SELECT flags FROM assessment_versions WHERE report_id=? AND version=?", (report_id, version)).fetchone()[0])
            data = json.loads(db.execute("SELECT payload FROM assessment_versions WHERE report_id=? AND version=?", (report_id, version)).fetchone()[0])
            if decision == "verified" and not data.get("observed_at"):
                raise DomainError("Verification requires an evidence-supported observation time")
            unresolved = db.execute("SELECT COUNT(*) FROM claims WHERE report_id=?", (report_id,)).fetchone()[0]
            if decision == "verified" and unresolved and version == 1:
                raise DomainError("Quarantined source columns require a corrected report version before verification")
            db.execute("INSERT INTO verifications VALUES(?,?,?,?,?,?,?,?)", (uid("VER"), report_id, version, decision, actor, reason, evidence, now()))
            db.execute("UPDATE assessments SET status=?,updated_at=? WHERE id=?", (decision, now(), report_id))
            self.audit(db, actor, "Report" + decision.title(), report_id, {"status": row["status"]}, {"status": decision, "flags": flags}, reason)
            self._feedback(db,row["owner"],report_id,decision,"Report "+decision.replace("_"," ")+". Use /status for the current version.")
            if decision == "verified":
                data = json.loads(db.execute("SELECT payload FROM assessment_versions WHERE report_id=? AND version=?", (report_id, version)).fetchone()[0])
                if data.get("latitude") is not None:
                    db.execute("UPDATE locations SET latitude=?,longitude=?,coordinate_source=?,coordinate_status='reviewer_verified' WHERE id=?", (data["latitude"], data["longitude"], data["coordinate_source"], row["location_id"]))
            if decision == "verified" or row["status"] == "verified":
                db.execute("INSERT INTO outbox(id,kind,payload,created_at) VALUES(?,?,?,?)", (uid("JOB"), "sheets_projection", dump({"report_id": report_id, "version": version, "action": decision}), now()))
        return self.report(report_id, actor, role)

    def resolve_duplicate(self, source_id, target_id, actor, role, reason):
        permit(role,{"reviewer"})
        if source_id==target_id or not isinstance(reason,str) or not reason.strip():
            raise DomainError("Select a different retained report and explain the resolution")
        with self.transaction() as db:
            source=db.execute("SELECT * FROM assessments WHERE id=?",(source_id,)).fetchone()
            target=db.execute("SELECT * FROM assessments WHERE id=?",(target_id,)).fetchone()
            if not source or not target: raise DomainError("Report not found",404)
            if source["location_id"]!=target["location_id"] or target["status"] in {"rejected","superseded"}:
                raise DomainError("Duplicate resolution requires the same reviewed location and an active retained report")
            if source["status"]=="superseded": raise DomainError("Report already resolved",409)
            db.execute("INSERT INTO report_links VALUES(?,?,?,?,?,?)",(uid("LNK"),source_id,target_id,actor,reason,now()))
            db.execute("UPDATE assessments SET status='superseded',updated_at=? WHERE id=?",(now(),source_id))
            self.audit(db,actor,"DuplicateResolved",source_id,{"status":source["status"]},{"status":"superseded","retained_report":target_id},reason)
            self._feedback(db,source["owner"],source_id,"superseded","A reviewer resolved this duplicate; all prior observations remain retained.")
            db.execute("INSERT INTO outbox(id,kind,payload,created_at) VALUES(?,?,?,?)",(uid("JOB"),"sheets_projection",dump({"report_id":source_id,"action":"superseded"}),now()))
        return self.report(source_id,actor,role)

    def resolve_claim(self, claim_id, actor, role, resolution, reason):
        permit(role,{"reviewer"})
        if resolution not in {"corrected_in_version","unable_to_verify","rejected_claim"} or not isinstance(reason,str) or not reason.strip():
            raise DomainError("Select a claim resolution and provide its evidence/version reason")
        with self.transaction() as db:
            row=db.execute("SELECT * FROM claims WHERE id=?",(claim_id,)).fetchone()
            if not row: raise DomainError("Claim not found",404)
            if resolution=="corrected_in_version" and db.execute("SELECT current_version FROM assessments WHERE id=?",(row["report_id"],)).fetchone()[0]<=1:
                raise DomainError("A corrected version is required")
            db.execute("INSERT INTO claim_resolutions VALUES(?,?,?,?,?,?,?)",(uid("CLR"),claim_id,row["report_id"],actor,resolution,reason,now()))
            self.audit(db,actor,"ClaimResolved",claim_id,None,{"resolution":resolution},reason)
        return {"claim_id":claim_id,"resolution":resolution}

    def request_feedback(self, report_id, actor, role, event, message):
        permit(role,{"reviewer","coordinator"})
        if event not in {"clarification_requested","follow_up_requested"} or not isinstance(message,str) or not message.strip() or len(message)>1000:
            raise DomainError("Provide a bounded clarification/follow-up request")
        with self.transaction() as db:
            report=db.execute("SELECT * FROM assessments WHERE id=?",(report_id,)).fetchone()
            if not report: raise DomainError("Report not found",404)
            if not db.execute("SELECT 1 FROM users WHERE id=? AND active=1",(report["owner"],)).fetchone():
                raise DomainError("Imported source has no linked contributor account; collect a field report or contact the source through an approved channel")
            self._feedback(db,report["owner"],report_id,event,message)
            self.audit(db,actor,"FeedbackRequested",report_id,None,{"event":event,"message":message},"Request to report owner only")
        return {"queued":True}

    def import_snapshot(self, snapshot: dict, profile: dict) -> dict:
        source_hash = profile["sha256"]
        if self.rows("SELECT key FROM metadata WHERE key=?", ("import:"+source_hash,)):
            return {"already_imported": True}
        field_rows = snapshot["ကွင်းဆင်းမှတ်တမ်းများ"][1:]
        for item in field_rows:
            c = item["cells"]
            if self.rows("SELECT id FROM locations WHERE id=?", (c["A"],)):
                continue
            key = "|".join(identity(x) for x in ("တနင်္သာရီတိုင်း", c["D"], c["E"]))
            with self.transaction() as db:
                existing = db.execute("SELECT id FROM locations WHERE identity_key=?", (key,)).fetchall()
                flags = ["partial_worklist", "not_assessed"]
                if existing:
                    flags.append("duplicate_location_identity")
                    for old in existing:
                        prior = json.loads(db.execute("SELECT flags FROM locations WHERE id=?", (old[0],)).fetchone()[0])
                        db.execute("UPDATE locations SET flags=? WHERE id=?", (dump(sorted(set(prior+["duplicate_location_identity"]))), old[0]))
                db.execute("INSERT OR IGNORE INTO locations(id,state_region,township,village,identity_key,flags) VALUES(?,?,?,?,?,?)", (c["A"], "တနင်္သာရီတိုင်း", c["D"], c["E"], key, dump(flags)))
        for item in snapshot["ဘေးသင့်ဒေသစာရင်း"][1:]:
            c = item["cells"]
            if c.get("F") == "အချက်အလက်ဖြည့်စွက်ရန်":
                continue
            payload = {"state_region": c["B"], "district": c["C"], "township": c["D"], "village": c["E"],
                       "source_reference": c.get("Q", profile["source_url"]), "source_type": "public_reporting",
                       "notes": f"Source tab ဘေးသင့်ဒေသစာရင်း row {item['row']}. Event period: {c.get('G')}. H:O require review.",
                       "missingness": {"observed_at": "unknown"}}
            key = "|".join(identity(payload[k]) for k in ("state_region", "township", "village"))
            matches = self.rows("SELECT id FROM locations WHERE identity_key=?", (key,))
            if len(matches) > 1:
                # Retain ambiguous report as a separate provisional identity; no arbitrary selection.
                payload["village"] += " [source identity pending]"
            record = self.submit(payload, dump(item), "source-import", "administrator", f"sheet:{source_hash}:{item['row']}", "google_sheet_snapshot", imported=True)
            with self.transaction() as db:
                for col in "HIJKLMNO":
                    if col in c:
                        db.execute("INSERT OR IGNORE INTO claims VALUES(?,?,?,?,?,?)", (uid("CLM"), record["id"], "quarantined_column_"+col, dump(c[col]), f"ဘေးသင့်ဒေသစာရင်း!{col}{item['row']}", "unresolved"))
        with self.transaction() as db:
            db.execute("INSERT INTO metadata VALUES(?,?)", ("import:"+source_hash, dump(profile)))
            db.execute("INSERT OR REPLACE INTO metadata VALUES('source_profile',?)", (dump(profile),))
            self.audit(db, "source-import", "SourceSnapshotImported", source_hash, None, profile, "Read-only source, H:O quarantined")
        return {"imported": True, "reports": len(self.reports("source-import", "administrator")), "locations": len(self.locations())}

    def requirements(self) -> list[dict]:
        return self.rows("SELECT * FROM requirements ORDER BY observed_at DESC")

    def create_requirement(self, data: dict, actor: str, role: str) -> str:
        permit(role, {"coordinator"})
        from .domain import timestamp
        for k in ("location_id", "resource", "unit", "period", "source", "observed_at"):
            if not isinstance(data.get(k), str) or not data[k].strip():
                raise DomainError("Required: " + k)
        if timestamp(data["observed_at"]) > datetime.now(timezone.utc):
            raise DomainError("Requirement observation cannot be future-dated")
        if data["unit"] not in {"liters", "kg", "food_kits", "household_kits", "shelter_kits", "medical_kits", "people", "households"}:
            raise DomainError("Use an explicit supported resource unit")
        quantity = finite_nonnegative(data.get("quantity"), "quantity")
        stock = None if data.get("usable_stock") is None else finite_nonnegative(data["usable_stock"], "usable_stock")
        requirement_id = uid("REQ")
        with self.transaction() as db:
            if not db.execute("SELECT 1 FROM locations WHERE id=?", (data["location_id"],)).fetchone():
                raise DomainError("Unknown location", 404)
            db.execute("INSERT INTO requirements VALUES(?,?,?,?,?,?,?,?,?,?)", (requirement_id, data["location_id"], data["resource"], data["unit"], data["period"], quantity, stock, data["source"], data["observed_at"], actor))
            self.audit(db, actor, "RequirementRecorded", requirement_id, None, data, data["source"])
        return requirement_id

    def pledge(self, requirement_id: str, organization: str, quantity: Any, source: str, actor: str, role: str, eta: str | None = None, expires_at: str | None = None) -> str:
        permit(role, {"coordinator"})
        quantity = finite_nonnegative(quantity, "quantity")
        if not organization.strip() or not source.strip():
            raise DomainError("Organization and source are required")
        from .domain import timestamp
        for value in (eta,expires_at):
            if value: timestamp(value)
        if expires_at and timestamp(expires_at) <= datetime.now(timezone.utc):
            raise DomainError("Pledge expiry must be in the future")
        commitment_id = uid("COM")
        with self.transaction() as db:
            if not db.execute("SELECT 1 FROM requirements WHERE id=?", (requirement_id,)).fetchone():
                raise DomainError("Unknown requirement", 404)
            db.execute("INSERT INTO commitments VALUES(?,?,?,?,?,?,?)", (commitment_id, requirement_id, organization, quantity, "pledged", now(), now()))
            db.execute("INSERT INTO commitment_terms VALUES(?,?,?,?)",(commitment_id,eta,expires_at,source))
            db.execute("INSERT INTO assistance_events VALUES(?,?,?,?,?,?,?)", (uid("AST"), commitment_id, "pledged", quantity, source, actor, now()))
            location_id=db.execute("SELECT location_id FROM requirements WHERE id=?",(requirement_id,)).fetchone()[0]
            self._location_feedback(db,location_id,"assistance_pledged","Assistance pledged for this village. A pledge does not confirm delivery.")
            self.audit(db, actor, "AssistancePledged", commitment_id, None, {"quantity": quantity}, source)
        return commitment_id

    def assistance_event(self, commitment_id: str, status: str, quantity: Any, source: str, actor: str, role: str) -> None:
        permit(role, {"coordinator", "reviewer"})
        transitions = {"pledged": {"dispatched", "cancelled"}, "dispatched": {"delivered", "unable_to_deliver"}, "delivered": {"receipt_confirmed"}, "receipt_confirmed": set(), "cancelled": set(), "unable_to_deliver": set()}
        if not source.strip():
            raise DomainError("Event evidence/source is required")
        with self.transaction() as db:
            old = db.execute("SELECT * FROM commitments WHERE id=?", (commitment_id,)).fetchone()
            if not old:
                raise DomainError("Commitment not found", 404)
            if status not in transitions.get(old["status"], set()):
                raise DomainError("Invalid assistance status transition", 409)
            terms=db.execute("SELECT expires_at FROM commitment_terms WHERE commitment_id=?",(commitment_id,)).fetchone()
            from .domain import timestamp
            if status=="dispatched" and terms and terms["expires_at"] and timestamp(terms["expires_at"])<=datetime.now(timezone.utc):
                raise DomainError("Pledge expired; cancel it and record a current commitment",409)
            amount = finite_nonnegative(quantity, "quantity") if status in {"delivered", "receipt_confirmed"} else None
            if amount is not None and amount > old["quantity"]:
                raise DomainError("Delivered/received quantity exceeds commitment; record a separate corrected commitment")
            if status == "receipt_confirmed":
                delivered = db.execute("SELECT quantity FROM assistance_events WHERE commitment_id=? AND status='delivered'", (commitment_id,)).fetchone()[0]
                if amount > delivered:
                    raise DomainError("Receipt cannot exceed delivered quantity")
            db.execute("INSERT INTO assistance_events VALUES(?,?,?,?,?,?,?)", (uid("AST"), commitment_id, status, amount, source, actor, now()))
            db.execute("UPDATE commitments SET status=?,updated_at=? WHERE id=?", (status, now(), commitment_id))
            location_id=db.execute("SELECT location_id FROM requirements WHERE id=?",(old["requirement_id"],)).fetchone()[0]
            self._location_feedback(db,location_id,"assistance_"+status,"Village assistance status: "+status.replace("_"," ")+". Follow-up observations are welcome.")
            self.audit(db, actor, "Assistance"+status.title(), commitment_id, {"status": old["status"]}, {"status": status, "quantity": amount}, source)

    def outcome(self, data: dict, actor: str, role: str) -> str:
        permit(role, {"coordinator", "reviewer"})
        from .domain import timestamp
        if not data.get("source") or not isinstance(data.get("payload"), dict):
            raise DomainError("Outcome source and observation payload are required")
        if timestamp(data.get("observed_at")) > datetime.now(timezone.utc):
            raise DomainError("Future outcome observation")
        oid = uid("OUT")
        with self.transaction() as db:
            req = db.execute("SELECT * FROM requirements WHERE id=?", (data.get("requirement_id"),)).fetchone()
            if not req:
                raise DomainError("Outcome requires a valid requirement")
            db.execute("INSERT INTO outcomes VALUES(?,?,?,?,?,?,?,?)", (oid, req["location_id"], req["id"], data["observed_at"], dump(data["payload"]), data["source"], actor, now()))
            self.audit(db, actor, "OutcomeAssessed", oid, None, data, data["source"])
        return oid

def finite_nonnegative(value: Any, field: str) -> float:
    import math
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise DomainError(field + " must be finite and nonnegative")
    return float(value)
