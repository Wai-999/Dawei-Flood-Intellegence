import concurrent.futures
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from flood import analytics,auth
from flood.cli import backup,check_backup
from flood.domain import DomainError,parse_structured,parse_compact,validate
from flood.exports import csv_bytes,xlsx_bytes
from flood.repository import Repository

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.repo=Repository(Path(self.tmp.name)/"test.sqlite3")
        self.payload={"state_region":"Tanintharyi","township":"Dawei","village":"Test village",
                      "observed_at":"2026-09-28T12:00:00+06:30","source_reference":"team-observation"}
    def tearDown(self):self.tmp.cleanup()
    def submit(self,key="test-key-0001",actor="field",**values):
        data={**self.payload,**values};return self.repo.submit(data,json.dumps(data),actor,"contributor",key)
    def test_unknown_not_zero(self):
        r=self.submit(affected_population=None,water_need="unknown")
        self.assertIsNone(r["data"]["affected_population"])
        self.assertEqual(r["data"]["missingness"]["water_need"],"unknown")
        self.assertIsNone(analytics.summarize([])["sum"])
        self.assertEqual(analytics.summarize([0])["sum"],0)
    def test_count_validation_preserves_failed_raw(self):
        with self.assertRaises(DomainError):self.submit(affected_households=101,households_total=100)
        self.assertEqual(len(self.repo.rows("SELECT * FROM submissions")),1)
        self.assertEqual(len(self.repo.reports("field","contributor")),0)
    def test_baseline_dispute_is_review_flag(self):
        r=self.submit(affected_households=101,households_total=100,baseline_disputed=True,baseline_dispute_reason="Baseline predates arrivals")
        self.assertIn("baseline_conflict:affected_households>households_total",r["flags"])
    def test_strict_numbers_and_future_date(self):
        for value in [-1,1.5,True,"20"]:
            with self.assertRaises(DomainError):validate({**self.payload,"deaths":value})
        with self.assertRaises(DomainError):validate({**self.payload,"observed_at":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
        with self.assertRaises(DomainError):validate({**self.payload,"latitude":float("nan"),"longitude":98,"coordinate_source":"gps"})
    def test_unicode_parser_and_ambiguity(self):
        self.assertEqual(parse_structured("#FLOOD_REPORT\naffected_households: ၈၄")["affected_households"],84)
        for text in ["deaths: ~10","deaths: 1\ndeaths: 2","unknown_key: 3"]:
            with self.assertRaises(DomainError):validate({**self.payload,**parse_structured(text)})
        with self.assertRaises(DomainError):validate({**self.payload,"observed_at":"2026-09-28"})
    def test_compact_parser(self):
        data=parse_compact("FR|LOC-1|2026-09-28T12:00:00Z|team|AH=84|W=critical")
        self.assertEqual(data["affected_households"],84)
        self.assertEqual(data["water_need"],"critical")
    def test_replay_and_conflicting_key(self):
        a=self.submit();b=self.submit();self.assertEqual(a["id"],b["id"])
        with self.assertRaises(DomainError):self.submit(affected_population=10)
    def test_concurrent_idempotency(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            records=list(pool.map(lambda _:self.submit(),range(3)))
        self.assertEqual(len({r["id"] for r in records}),1)
        self.assertEqual(len(self.repo.rows("SELECT * FROM submissions")),1)
    def test_owner_and_export_privacy(self):
        r=self.submit(notes="private phone or medical context")
        self.assertEqual(self.repo.reports("other","contributor"),[])
        with self.assertRaises(DomainError):self.repo.update(r["id"],{},"other","contributor","reason",1)
        analyst=self.repo.report(r["id"],"analyst","analyst")
        self.assertNotIn("notes",analyst["data"])
        self.assertNotIn("raw_submission",analyst)
    def test_immutable_raw_history_audit(self):
        r=self.submit(affected_population=10)
        for table in ["submissions","assessment_versions","observations","audit_events"]:
            with self.assertRaises(sqlite3.IntegrityError):
                with self.repo.transaction() as db:db.execute(f"DELETE FROM {table}")
        updated=self.repo.update(r["id"],{"affected_population":20},"field","contributor","New count",1)
        self.assertEqual(updated["history"][0]["data"]["affected_population"],10)
        self.assertEqual(updated["data"]["affected_population"],20)
        with self.assertRaises(DomainError):self.repo.update(r["id"],{},"field","contributor","late",1)
    def test_review_role_evidence_outbox(self):
        r=self.submit()
        with self.assertRaises(DomainError):self.repo.review(r["id"],"verified","field","contributor","yes","evidence",1)
        with self.assertRaises(DomainError):self.repo.review(r["id"],"verified","reviewer","reviewer","yes","",1)
        verified=self.repo.review(r["id"],"verified","reviewer","reviewer","Compared field evidence","ref",1)
        self.assertEqual(verified["status"],"verified")
        self.assertEqual(len(self.repo.rows("SELECT * FROM outbox WHERE status='pending'")),1)
    def test_coordinates_only_approved_to_map(self):
        r=self.submit(latitude=14.1,longitude=98.2,coordinate_source="GPS reference")
        self.assertIsNone(self.repo.locations()[0]["latitude"])
        self.repo.review(r["id"],"verified","reviewer","reviewer","GPS checked","gps",1)
        self.assertEqual(self.repo.locations()[0]["latitude"],14.1)
    def test_freshness_uses_observed_time(self):
        result=analytics.freshness("2026-09-28T00:00:00Z",12,datetime(2026,9,30,tzinfo=timezone.utc))
        self.assertEqual(result["age_hours"],48)
        self.assertAlmostEqual(result["freshness"],.0625)
        self.assertIsNone(analytics.freshness(None,12)["freshness"])
    def test_severity_missing_bounds_confidence_separate(self):
        method={"id":"approved","weights":{"water_need":.5,"food_need":.5}}
        score=analytics.score({"water_need":"critical"},method)
        self.assertEqual((score["lower"],score["upper"]),(50,100))
        self.assertNotIn("confidence",score)
        self.assertIsNone(analytics.score({},None)["lower"])
    def test_method_approval_and_sensitivity(self):
        with self.assertRaises(DomainError):analytics.save_method(self.repo,{"weights":{"water_need":1}},"analyst","analyst")
        method=analytics.save_method(self.repo,{"weights":{"water_need":.6,"medical_need":.4},"reason":"Test owner approval","approval_reference":"test approval"},"analyst","analyst")
        scenarios=analytics.sensitivity({"water_need":"critical","medical_need":"none"},method)["scenarios"]
        self.assertGreater(scenarios[1]["lower"],scenarios[0]["lower"])
    def test_missing_state_cleared_by_known_correction(self):
        r=self.submit(water_need="unknown")
        corrected=self.repo.update(r["id"],{"water_need":"critical"},"field","contributor","Field reassessment",1)
        self.assertEqual(corrected["data"]["water_need"],"critical")
        self.assertNotIn("water_need",corrected["data"]["missingness"])
        self.assertEqual(len(self.repo.rows("SELECT * FROM submissions")),2)
    def test_reopened_verified_record_queues_sync_removal(self):
        r=self.submit()
        self.repo.review(r["id"],"verified","reviewer","reviewer","Checked","evidence",1)
        with self.repo.transaction() as db:db.execute("UPDATE outbox SET status='sent'")
        self.repo.update(r["id"],{"water_need":"critical"},"field","contributor","New observation",1)
        self.assertEqual(len(self.repo.rows("SELECT * FROM outbox WHERE status='pending'")),1)
        self.assertEqual(self.repo.report(r["id"],"reviewer","reviewer")["status"],"needs_review")
    def test_pledge_not_delivered_gap_and_unit_isolation(self):
        r=self.submit()
        req=self.repo.create_requirement({"location_id":r["location_id"],"resource":"water","unit":"liters","period":"2026-10-02","quantity":100,"usable_stock":0,"source":"assessment","observed_at":self.payload["observed_at"]},"coord","coordinator")
        commitment=self.repo.pledge(req,"Org A",60,"pledge-reference","coord","coordinator")
        self.assertEqual(analytics.gaps(self.repo)[0]["confirmed_gap"],100)
        self.repo.assistance_event(commitment,"dispatched",None,"dispatch","coord","coordinator")
        self.assertEqual(analytics.gaps(self.repo)[0]["projected_gap"],40)
        self.repo.assistance_event(commitment,"delivered",50,"delivery","coord","coordinator")
        self.assertEqual(analytics.gaps(self.repo)[0]["confirmed_gap"],100)
        with self.assertRaises(DomainError):self.repo.assistance_event(commitment,"receipt_confirmed",55,"receipt","coord","coordinator")
        self.repo.assistance_event(commitment,"receipt_confirmed",50,"receipt","coord","coordinator")
        self.assertEqual(analytics.gaps(self.repo)[0]["confirmed_gap"],50)
        with self.assertRaises(DomainError):self.repo.assistance_event(commitment,"receipt_confirmed",50,"replay","coord","coordinator")
        req2=self.repo.create_requirement({"location_id":r["location_id"],"resource":"water","unit":"household_kits","period":"2026-10-02","quantity":10,"source":"assessment","observed_at":self.payload["observed_at"]},"coord","coordinator")
        rows={x["id"]:x for x in analytics.gaps(self.repo)}
        self.assertIsNone(rows[req2]["confirmed_gap"])
        self.assertEqual(rows[req2]["receipt_confirmed"],0)
    def test_backup_restore_counts(self):
        self.submit()
        output=Path(self.tmp.name)/"backup.sqlite3"
        result=backup(self.repo,output)
        self.assertEqual(check_backup(output),result)
        self.assertEqual(result["counts"]["assessments"],1)
    def test_formula_safe_export(self):
        r=self.submit(village="=HYPERLINK(\"malicious\")")
        self.assertIn(b"'=HYPERLINK",csv_bytes([r]))
        import zipfile,io
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes({"Reports":[["=1+1",None,0]]}))) as z:
            text=z.read("xl/worksheets/sheet1.xml").decode()
            self.assertNotIn("<f>",text);self.assertIn('t="inlineStr"',text)
    def test_auth_session_and_revocation(self):
        uid=auth.create_user(self.repo,"user","contributor","example-private-password")
        token,user=auth.login(self.repo,"user","example-private-password")
        self.assertEqual(auth.session(self.repo,token)["id"],uid)
        with self.repo.transaction() as db:db.execute("UPDATE users SET active=0 WHERE id=?",(uid,))
        with self.assertRaises(DomainError):auth.session(self.repo,token)

if __name__=="__main__":unittest.main()
