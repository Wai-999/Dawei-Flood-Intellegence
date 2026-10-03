PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS locations (
 id TEXT PRIMARY KEY, state_region TEXT NOT NULL, district TEXT, township TEXT NOT NULL,
 village TEXT NOT NULL, identity_key TEXT NOT NULL, latitude REAL, longitude REAL,
 coordinate_source TEXT, coordinate_status TEXT NOT NULL DEFAULT 'unknown', flags TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS locations_identity ON locations(identity_key);
CREATE TABLE IF NOT EXISTS location_aliases(id TEXT PRIMARY KEY,location_id TEXT REFERENCES locations(id),name TEXT,source TEXT,approved_by TEXT);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,role TEXT NOT NULL,password_hash TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,reference TEXT NOT NULL,independence_group TEXT NOT NULL,metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE NOT NULL,actor TEXT NOT NULL,channel TEXT NOT NULL,received_at TEXT NOT NULL,raw TEXT NOT NULL,sha256 TEXT NOT NULL,parser_version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments(id TEXT PRIMARY KEY,location_id TEXT NOT NULL REFERENCES locations(id),submission_id TEXT REFERENCES submissions(id),owner TEXT NOT NULL,status TEXT NOT NULL,current_version INTEGER NOT NULL,received_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessment_versions(report_id TEXT NOT NULL REFERENCES assessments(id),version INTEGER NOT NULL,payload TEXT NOT NULL,flags TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(report_id,version));
CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,report_id TEXT REFERENCES assessments(id),version INTEGER,field TEXT NOT NULL,value TEXT,missing_state TEXT,observed_at TEXT,reported_at TEXT,source_id TEXT REFERENCES sources(id),UNIQUE(report_id,version,field));
CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY,report_id TEXT REFERENCES assessments(id),field TEXT NOT NULL,raw_value TEXT NOT NULL,source_cell TEXT NOT NULL,resolution_status TEXT NOT NULL DEFAULT 'unresolved');
CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,report_id TEXT REFERENCES assessments(id),source_id TEXT REFERENCES sources(id),reference TEXT NOT NULL,evidence_type TEXT NOT NULL,sha256 TEXT);
CREATE TABLE IF NOT EXISTS verifications(id TEXT PRIMARY KEY,report_id TEXT REFERENCES assessments(id),version INTEGER,decision TEXT,actor TEXT,reason TEXT,selected_evidence TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_events(id TEXT PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,entity TEXT NOT NULL,old_state TEXT,new_state TEXT,reason TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts(actor TEXT PRIMARY KEY,state TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requirements(id TEXT PRIMARY KEY,location_id TEXT REFERENCES locations(id),resource TEXT NOT NULL,unit TEXT NOT NULL,period TEXT NOT NULL,quantity REAL NOT NULL,usable_stock REAL,source TEXT NOT NULL,observed_at TEXT NOT NULL,actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commitments(id TEXT PRIMARY KEY,requirement_id TEXT REFERENCES requirements(id),organization TEXT NOT NULL,quantity REAL NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assistance_events(id TEXT PRIMARY KEY,commitment_id TEXT REFERENCES commitments(id),status TEXT NOT NULL,quantity REAL,source TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcomes(id TEXT PRIMARY KEY,location_id TEXT REFERENCES locations(id),requirement_id TEXT REFERENCES requirements(id),observed_at TEXT NOT NULL,payload TEXT NOT NULL,source TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS methods(id TEXT PRIMARY KEY,payload TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS priority_snapshots(id TEXT PRIMARY KEY,method_id TEXT REFERENCES methods(id),record_versions TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT,created_at TEXT NOT NULL,sent_at TEXT);
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS integration_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_submission_update BEFORE UPDATE ON submissions BEGIN SELECT RAISE(ABORT,'raw submissions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_submission_delete BEFORE DELETE ON submissions BEGIN SELECT RAISE(ABORT,'raw submissions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_audit_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT,'audit is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_audit_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'audit is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_version_update BEFORE UPDATE ON assessment_versions BEGIN SELECT RAISE(ABORT,'history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_version_delete BEFORE DELETE ON assessment_versions BEGIN SELECT RAISE(ABORT,'history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_observation_update BEFORE UPDATE ON observations BEGIN SELECT RAISE(ABORT,'observations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_observation_delete BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT,'observations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_claim_update BEFORE UPDATE ON claims BEGIN SELECT RAISE(ABORT,'original claims are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_claim_delete BEFORE DELETE ON claims BEGIN SELECT RAISE(ABORT,'original claims are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_assistance_update BEFORE UPDATE ON assistance_events BEGIN SELECT RAISE(ABORT,'resource events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_assistance_delete BEFORE DELETE ON assistance_events BEGIN SELECT RAISE(ABORT,'resource events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_method_update BEFORE UPDATE ON methods BEGIN SELECT RAISE(ABORT,'methods are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_method_delete BEFORE DELETE ON methods BEGIN SELECT RAISE(ABORT,'methods are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_verification_update BEFORE UPDATE ON verifications BEGIN SELECT RAISE(ABORT,'verification is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_verification_delete BEFORE DELETE ON verifications BEGIN SELECT RAISE(ABORT,'verification is immutable'); END;
PRAGMA user_version=1;
