import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from flood.auth import create_user
from flood.domain import DomainError
from flood.integrations import sync_sheets,telegram_once
from flood.exports import HEADERS
from flood.repository import Repository
from flood.telegram import Conversation,STEPS

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.repo=Repository(Path(self.tmp.name)/"test.sqlite3")
        self.payload={"state_region":"TNI","township":"Dawei","village":"Village","observed_at":"2026-09-28T12:00:00Z","source_reference":"field"}
        self.r=self.repo.submit(self.payload,json.dumps(self.payload),"field","contributor","integration-key")
    def tearDown(self):self.tmp.cleanup()
    def test_guided_skip_back_resume_confirm_replay(self):
        conversation=Conversation(self.repo)
        conversation.handle("new-field","contributor","/new",100)
        conversation.handle("new-field","contributor",self.r["location_id"],101)
        conversation.handle("new-field","contributor","2026-09-28T13:00:00Z",102)
        for i in range(8):conversation.handle("new-field","contributor","/skip",103+i)
        conversation.handle("new-field","contributor","source-reference",104)
        conversation.handle("new-field","contributor","/save",105)
        self.assertIn("Draft",Conversation(self.repo).handle("new-field","contributor","/resume",106))
        with self.assertRaises(DomainError):conversation.handle("new-field","contributor","/confirm",107)
        conversation.handle("new-field","contributor","/preview",108)
        reply=conversation.handle("new-field","contributor","/confirm",109)
        self.assertEqual(reply,Conversation(self.repo).handle("new-field","contributor","/confirm",109))
        self.assertEqual(len(self.repo.rows("SELECT * FROM assessments")),2)
    def test_telegram_worker_replay_checkpoint_and_denied_sender(self):
        actor=create_user(self.repo,"tg-field","contributor","private-test-password")
        updates=[{"update_id":7,"message":{"from":{"id":99},"chat":{"id":99,"type":"private"},"text":"/new"}}]
        sent=[]
        def client(url,data=None,headers=None):
            if url.endswith("getUpdates"):return {"ok":True,"result":updates}
            if url.endswith("sendMessage"):sent.append(data["text"]);return {"ok":True}
            return {"ok":True}
        telegram_once(self.repo,"test-only-token",{"99":actor},client)
        self.assertIn("location_id",sent[-1]);self.assertEqual(json.loads(self.repo.rows("SELECT value FROM integration_state WHERE key='telegram_offset'")[0]["value"]),8)
        updates[0]["message"]["from"]["id"]=88
        telegram_once(self.repo,"test-only-token",{"99":actor},client)
        self.assertIn("not authorized",sent[-1])
    def test_telegram_failure_retains_checkpoint(self):
        def client(url,data=None,headers=None):
            if url.endswith("getUpdates"):return {"ok":True,"result":[{"update_id":9,"message":{"from":{"id":88},"chat":{"id":88},"text":"/new"}}]}
            return {"ok":False}
        with self.assertRaises(DomainError):telegram_once(self.repo,"test-only-token",{},client)
        self.assertEqual(self.repo.rows("SELECT * FROM integration_state WHERE key='telegram_offset'"),[])
    def test_group_chat_does_not_expose_reports(self):
        actor=create_user(self.repo,"group-field","contributor","private-test-password")
        replies=[]
        def client(url,data=None,headers=None):
            if url.endswith("getUpdates"):return {"ok":True,"result":[{"update_id":10,"message":{"from":{"id":99},"chat":{"id":-100,"type":"group"},"text":"/status "+self.r["id"]}}]}
            if url.endswith("sendMessage"):replies.append(data["text"])
            return {"ok":True}
        telegram_once(self.repo,"test-only-token",{"99":actor},client)
        self.assertIn("private chat",replies[0]);self.assertNotIn(self.r["id"],replies[0])
    def test_sheets_owned_projection_and_retry(self):
        self.repo.review(self.r["id"],"verified","reviewer","reviewer","Checked","evidence",1)
        writes=[]
        def client(url,data=None,headers=None):
            if "?fields=" in url:return {"sheets":[{"properties":{"title":"12_Dashboard_Export"}}]}
            if "values:batchUpdate" in url:writes.append(data);return {"totalUpdatedRows":2}
            return {"values":[HEADERS]}
        with patch.dict(os.environ,{"GOOGLE_SERVICE_ACCOUNT_FILE":"test-only-key.json","GOOGLE_SHEET_ID":"test-sheet"}):
            result=sync_sheets(self.repo,client,lambda _:"test-token")
        self.assertEqual(result["records"],1)
        self.assertEqual(writes[0]["valueInputOption"],"RAW")
        self.assertEqual(writes[0]["data"][0]["range"],"'12_Dashboard_Export'!A1")
        self.assertEqual(sync_sheets(self.repo,client,lambda _:"token")["status"],"no_pending_jobs")
    def test_sheets_schema_conflict_does_not_write(self):
        self.repo.review(self.r["id"],"verified","reviewer","reviewer","Checked","evidence",1)
        writes=[]
        def client(url,data=None,headers=None):
            if "?fields=" in url:return {"sheets":[{"properties":{"title":"12_Dashboard_Export"}}]}
            if data:writes.append(data)
            return {"values":[["unexpected schema"]]}
        with patch.dict(os.environ,{"GOOGLE_SERVICE_ACCOUNT_FILE":"test-only-key.json","GOOGLE_SHEET_ID":"test-sheet"}):
            with self.assertRaises(DomainError):sync_sheets(self.repo,client,lambda _:"test-token")
        self.assertEqual(writes,[])
        self.assertEqual(self.repo.rows("SELECT status FROM outbox")[0]["status"],"failed")
    def test_import_quarantine_placeholder_and_idempotence(self):
        snapshot={"ကွင်းဆင်းမှတ်တမ်းများ":[{"row":2,"cells":{"A":"ID","D":"township","E":"village"}},{"row":3,"cells":{"A":"TFUCC-1","D":"Township","E":"Village"}}],
            "ဘေးသင့်ဒေသစာရင်း":[{"row":1,"cells":{}},{"row":2,"cells":{"B":"တနင်္သာရီတိုင်း","C":"District","D":"Township","E":"Village","F":"flood","H":10,"K":"road blocked","Q":"source"}},{"row":3,"cells":{"F":"အချက်အလက်ဖြည့်စွက်ရန်"}}]}
        profile={"sha256":"test-hash","source_url":"test-source"}
        self.repo.import_snapshot(snapshot,profile)
        reports=[r for r in self.repo.reports("admin","administrator") if r["data"]["source_reference"]=="source"]
        self.assertEqual(len(reports),1);self.assertNotIn("deaths",reports[0]["data"])
        report=self.repo.report(reports[0]["id"],"reviewer","reviewer");self.assertEqual(len(report["raw_claims"]),2)
        with self.assertRaises(DomainError):self.repo.review(report["id"],"verified","reviewer","reviewer","checked","evidence",1)
        before=len(self.repo.rows("SELECT * FROM assessments"));self.repo.import_snapshot(snapshot,profile)
        self.assertEqual(len(self.repo.rows("SELECT * FROM assessments")),before)

if __name__=="__main__":unittest.main()
