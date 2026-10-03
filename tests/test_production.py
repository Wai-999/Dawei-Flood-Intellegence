import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from flood.auth import create_user, throttle, login
from flood.domain import DomainError
from flood.repository import Repository
from flood.wsgi import Application, Config


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.tmp.name)/'test.sqlite3')
        self.env = patch.dict(os.environ, {'FLOOD_SECURE_COOKIES':'1'})
        self.env.start()
        self.app = Application(self.repo, Config('https://flood.test', True, ('172.29.0.2',)))
        self.actor = create_user(self.repo,'field','contributor','test-private-password')
        create_user(self.repo,'admin','administrator','test-private-password')

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def request(self,path,body=None,method='GET',**extra):
        raw=json.dumps(body).encode() if body is not None else b''
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'HTTP_HOST':'flood.test','REMOTE_ADDR':'172.29.0.2','HTTP_X_FORWARDED_PROTO':'https','HTTP_X_FORWARDED_FOR':'192.0.2.5','wsgi.url_scheme':'http','wsgi.input':io.BytesIO(raw),'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),**extra}
        result={}
        def start(status,headers): result.update(status=int(status.split()[0]),headers=dict(headers))
        result['body']=b''.join(self.app(env,start))
        return result

    def test_probe_and_no_auth_bypass(self):
        self.assertEqual(self.request('/health/live')['status'],200)
        self.assertEqual(self.request('/health/ready')['status'],200)
        r=self.request('/api/v1/reports')
        self.assertEqual(r['status'],401)
        self.assertIn('Strict-Transport-Security',r['headers'])
        self.assertEqual(self.request('/health/live',HTTP_HOST='attacker.test')['status'],400)

    def test_proxy_spoof_and_body_framing(self):
        self.assertEqual(self.request('/api/v1/me',REMOTE_ADDR='192.0.2.8')['status'],426)
        self.assertEqual(self.request('/api/v1/me',HTTP_X_FORWARDED_FOR='1.2.3.4, 5.6.7.8')['status'],400)
        self.assertEqual(self.request('/api/v1/login',{},'POST',CONTENT_LENGTH='65537')['status'],413)
        self.assertEqual(self.request('/api/v1/login',{},'POST',CONTENT_LENGTH='')['status'],411)
        self.assertEqual(self.request('/api/v1/login',{},'POST',HTTP_TRANSFER_ENCODING='chunked')['status'],400)

    def test_cookie_and_origin(self):
        body={'username':'field','password':'test-private-password'}
        self.assertEqual(self.request('/api/v1/login',body,'POST',HTTP_ORIGIN='https://attacker.test')['status'],403)
        response=self.request('/api/v1/login',body,'POST',HTTP_ORIGIN='https://flood.test')
        self.assertEqual(response['status'],200)
        for flag in ('Secure','HttpOnly','SameSite=Strict'): self.assertIn(flag,response['headers']['Set-Cookie'])

    def test_persistent_rate_limit(self):
        for _ in range(5): throttle(self.repo,'192.0.2.1','field')
        with self.assertRaises(DomainError) as failure: throttle(Repository(self.repo.path),'192.0.2.2','field')
        self.assertEqual(failure.exception.status,429)

    def test_raw_retained_before_parse_and_geography(self):
        with self.assertRaises(DomainError): self.repo.ingest(None,'affected_population: ~20',self.actor,'contributor','raw-parse-123')
        p={'location_id':'UNKNOWN','observed_at':'2026-09-28T12:00:00Z','source_reference':'field'}
        with self.assertRaises(DomainError): self.repo.ingest(p,None,self.actor,'contributor','raw-place-123')
        self.assertEqual(len(self.repo.rows('SELECT * FROM submissions')),2)
        self.assertEqual(self.repo.rows('SELECT * FROM assessments'),[])
        self.assertEqual(len(self.repo.rows("SELECT * FROM audit_events WHERE action='ValidationRejected'")),2)

    def test_manual_text_replay(self):
        text='#FLOOD_REPORT\nstate_region: TNI\ntownship: Dawei\nvillage: Test\nobserved_at: 2026-09-28T12:00:00Z\nsource_reference: field'
        a=self.repo.ingest(None,text,self.actor,'contributor','raw-replay-123')
        b=self.repo.ingest(None,text,self.actor,'contributor','raw-replay-123')
        self.assertEqual(a['id'],b['id'])
        self.assertEqual(len(self.repo.feedback_for(self.actor,'contributor')),1)

    def test_http_throttle_and_expired_session(self):
        body={'username':'field','password':'incorrect-password'}
        for _ in range(5): self.assertEqual(self.request('/api/v1/login',body,'POST',HTTP_ORIGIN='https://flood.test')['status'],401)
        self.assertEqual(self.request('/api/v1/login',body,'POST',HTTP_ORIGIN='https://flood.test')['status'],429)
        token,_=login(self.repo,'field','test-private-password')
        with self.repo.transaction() as db: db.execute('UPDATE sessions SET expires=0')
        self.assertEqual(self.request('/api/v1/me',HTTP_COOKIE='flood_session='+token)['status'],401)

    def test_contributor_cannot_promote_or_request_follow_up(self):
        token,user=login(self.repo,'field','test-private-password')
        headers={'HTTP_COOKIE':'flood_session='+token,'HTTP_X_CSRF_TOKEN':user['csrf'],'HTTP_ORIGIN':'https://flood.test'}
        report=self.repo.ingest(None,'state_region: TNI\ntownship: Test\nvillage: Test\nobserved_at: 2026-09-28T12:00:00Z\nsource_reference: field',self.actor,'contributor','privilege-test')
        self.assertEqual(self.request('/api/v1/users')['status'],401)
        self.assertEqual(self.request('/api/v1/users',**headers)['status'],403)
        self.assertEqual(self.request('/api/v1/verification/'+report['id'],{'decision':'verified','reason':'Self promotion','evidence':'test','version':1},'POST',**headers)['status'],403)
        self.assertEqual(self.request('/api/v1/feedback/'+report['id'],{'event':'follow_up_requested','message':'test'},'POST',**headers)['status'],403)
        self.assertEqual(self.repo.report(report['id'],self.actor,'contributor')['status'],'submitted')

    def test_feedback_is_owner_filtered(self):
        text='state_region: TNI\ntownship: Test\nvillage: Test\nobserved_at: 2026-09-28T12:00:00Z\nsource_reference: field'
        report=self.repo.ingest(None,text,self.actor,'contributor','feedback-owner')
        self.repo.request_feedback(report['id'],'reviewer','reviewer','clarification_requested','Please confirm observation time')
        self.assertEqual(self.repo.feedback_for('another-field','contributor'),[])
        self.assertIn('clarification_requested',[row['event'] for row in self.repo.feedback_for(self.actor,'contributor')])


if __name__=='__main__': unittest.main()
