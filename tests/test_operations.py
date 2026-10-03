import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from flood import analytics
from flood.domain import DomainError
from flood.integrations import http_json
from flood.repository import Repository,ROOT

class OperationsTests(unittest.TestCase):
    def test_backup_health_exposes_latest_worker_failure(self):
        from flood.health import health
        from flood.integrations import state
        with tempfile.TemporaryDirectory() as folder:
            repo=Repository(Path(folder)/'health.sqlite3')
            state(repo,'last_bundle',{'status':'HEALTHY'})
            state(repo,'backup_worker',{'status':'FAILED'})
            self.assertEqual(health(repo)['backup']['status'],'FAILED')
            self.assertEqual(health(repo)['status'],'DEGRADED')
            state(repo,'last_bundle',{'status':'HEALTHY'})
            state(repo,'backup_worker',{'status':'HEALTHY'})
            self.assertEqual(health(repo)['backup']['status'],'HEALTHY')
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.repo=Repository(Path(self.tmp.name)/'test.sqlite3')
        self.payload={'state_region':'TNI','township':'Test','village':'Synthetic','observed_at':'2026-09-28T12:00:00Z','source_reference':'synthetic-test','water_need':'critical','medical_need':'low'}
    def tearDown(self):self.tmp.cleanup()

    def test_upgrade_preserves_v1_history(self):
        path=Path(self.tmp.name)/'legacy.sqlite3';db=sqlite3.connect(path)
        db.executescript((ROOT/'database/migrations/001_initial.sql').read_text());db.execute("INSERT INTO metadata VALUES('sentinel','retained')");db.commit();db.close()
        upgraded=Repository(path)
        self.assertEqual(upgraded.rows('PRAGMA user_version')[0]['user_version'],2)
        self.assertEqual(upgraded.rows("SELECT value FROM metadata WHERE key='sentinel'")[0]['value'],'retained')

    def test_duplicate_resolution_preserves_both_histories(self):
        a=self.repo.submit(self.payload,json.dumps(self.payload),'field','contributor','resolve-a')
        b=self.repo.submit(self.payload,json.dumps(self.payload),'field','contributor','resolve-b')
        with self.assertRaises(DomainError):self.repo.resolve_duplicate(a['id'],b['id'],'field','contributor','Synthetic resolution')
        resolved=self.repo.resolve_duplicate(a['id'],b['id'],'reviewer','reviewer','Synthetic resolution')
        self.assertEqual(resolved['status'],'superseded')
        self.assertEqual(len(self.repo.rows('SELECT * FROM assessment_versions')),2)
        self.assertEqual(resolved['duplicate_resolutions'][0]['target_report'],b['id'])

    def test_snapshot_and_sensitivity(self):
        record=self.repo.submit(self.payload,json.dumps(self.payload),'field','contributor','snapshot-test')
        self.repo.review(record['id'],'verified','reviewer','reviewer','Synthetic review','synthetic-test',1)
        analytics.save_method(self.repo,{'weights':{'water_need':.5,'medical_need':.5},'approval_reference':'synthetic-test','reason':'Synthetic test policy'},'analyst','analyst')
        snapshot=analytics.priority_snapshot(self.repo,'analyst','analyst')
        self.assertEqual(snapshot['sensitivity']['comparable_records'],1)
        with self.repo.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM priority_snapshots')

    def test_expired_pledge_and_unit_guard(self):
        record=self.repo.submit(self.payload,json.dumps(self.payload),'field','contributor','expiry-place')
        req=self.repo.create_requirement({'location_id':record['location_id'],'resource':'water','unit':'liters','period':'synthetic','quantity':20,'usable_stock':0,'observed_at':self.payload['observed_at'],'source':'synthetic'},'coord','coordinator')
        with self.assertRaises(DomainError):self.repo.pledge(req,'Synthetic organization',10,'synthetic','coord','coordinator',None,'2026-09-01T00:00:00Z')
        pledge=self.repo.pledge(req,'Synthetic organization',10,'synthetic','coord','coordinator','2026-09-29T00:00:00Z')
        self.assertIn('eta_passed_pledged',[w['kind'] for w in analytics.gaps(self.repo)[0]['warnings']])

    def test_provider_rejects_non_https_and_unowned_hosts(self):
        for url in ['file:///etc/passwd','http://api.telegram.org','https://attacker.test','https://api.telegram.org@attacker.test','https://sheets.googleapis.com:444']:
            with self.assertRaises(DomainError):http_json(url)

if __name__=='__main__':unittest.main()
