from http.cookiejar import CookieJar
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import build_opener,HTTPCookieProcessor,Request
from flood.auth import create_user
from flood.repository import Repository
from flood.server import FloodServer

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.repo=Repository(Path(self.tmp.name)/"test.sqlite3")
        create_user(self.repo,"field","contributor","private-test-password")
        self.server=FloodServer(("127.0.0.1",0),self.repo)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=self.server.origin;self.client=build_opener(HTTPCookieProcessor(CookieJar()));self.csrf=None
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,data=None,headers=None,method=None):
        hdr={"Content-Type":"application/json","Origin":self.base,**(headers or {})}
        if self.csrf:hdr.setdefault("X-CSRF-Token",self.csrf)
        req=Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers=hdr,method=method)
        try:
            with self.client.open(req) as response:return response.status,json.load(response),response.headers
        except HTTPError as exc:return exc.code,json.load(exc),exc.headers
    def signin(self):
        status,user,_=self.request('/api/v1/login',{"username":"field","password":"private-test-password"});self.assertEqual(status,200);self.csrf=user["csrf"]
    def test_unauthorized_and_source_file_not_served(self):
        self.assertEqual(self.request('/api/v1/reports')[0],401)
        self.assertEqual(self.request('/data/source_snapshot.json')[0],404)
    def test_origin_and_csrf(self):
        self.assertEqual(self.request('/api/v1/login',{"username":"field","password":"private-test-password"},{"Origin":"https://attacker.example"})[0],403)
        self.signin();self.csrf=None
        self.assertEqual(self.request('/api/v1/reports',{})[0],403)
    def test_create_own_report_and_role_enforcement(self):
        self.signin()
        payload={"state_region":"TNI","township":"Town","village":"Village","observed_at":"2026-09-28T13:00:00Z","source_reference":"field"}
        status,record,_=self.request('/api/v1/reports',{"payload":payload},{"Idempotency-Key":"api-test-key"});self.assertEqual(status,201)
        self.assertEqual(self.request('/api/v1/verification/'+record["id"],{"decision":"verified","reason":"bad","evidence":"x","version":1})[0],403)
        self.assertEqual(self.request('/api/v1/audit')[0],403)
        self.assertEqual(self.request('/api/v1/health')[0],403)
        self.assertEqual(self.request('/api/v1/export?format=json')[0],403)
        self.assertEqual(len(self.request('/api/v1/reports')[1]),1)
    def test_preview_rejects_mutations(self):
        self.server.preview=True
        self.assertEqual(self.request('/api/v1/reports',{})[0],403)
        self.assertEqual(self.request('/api/v1/login',{})[0],403)
        status,data,headers=self.request('/api/v1/analytics/overview');self.assertEqual(status,200)
        self.assertEqual(headers["Cache-Control"],"no-store")

if __name__=="__main__":unittest.main()
