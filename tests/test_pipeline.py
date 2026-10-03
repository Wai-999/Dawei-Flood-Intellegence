import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from flood import analytics
from flood.auth import create_user,deactivate_user,login,session
from flood.domain import DomainError
from flood.exports import export,HEADERS
from flood.integrations import sync_sheets,telegram_once
from flood.recovery import bundle,inspect_bundle,restore_bundle
from flood.repository import Repository
from flood.telegram import Conversation
from flood.workers import worker_lock

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.repo=Repository(self.root/'data.sqlite3')
        self.actor=create_user(self.repo,'field','contributor','test-private-password')
        self.admin=create_user(self.repo,'admin','administrator','test-private-password')
        self.payload={'state_region':'TNI','township':'Test','village':'Synthetic village','observed_at':'2026-09-28T12:00:00Z','source_reference':'synthetic-test-only','affected_population':20,'population_total':100,'water_need':'critical','latitude':14.1,'longitude':98.2,'coordinate_source':'synthetic-test-only'}
    def tearDown(self): self.tmp.cleanup()

    def test_complete_pipeline_and_projection_removal(self):
        bot=Conversation(self.repo)
        text='#FLOOD_REPORT\n'+'\n'.join(f'{k}: {v}' for k,v in self.payload.items())
        bot.handle(self.actor,'contributor',text,1)
        self.assertEqual(len(self.repo.rows('SELECT * FROM submissions')),1)
        self.assertEqual(self.repo.rows('SELECT * FROM assessments'),[])
        bot.handle(self.actor,'contributor','/preview',2)
        reply=bot.handle(self.actor,'contributor','/confirm',3)
        self.assertEqual(reply,bot.handle(self.actor,'contributor','/confirm',3))
        report=self.repo.reports(self.actor,'contributor')[0]
        eid=self.repo.add_evidence(report['id'],{'reference':'synthetic-review-evidence'},self.actor,'contributor')
        self.repo.review(report['id'],'verified','reviewer','reviewer','Synthetic acceptance test',eid,1)
        method=analytics.save_method(self.repo,{'weights':{'water_need':1},'reason':'Synthetic test policy','approval_reference':'synthetic-test-only','half_life_hours':{'water_need':24}},'analyst','analyst')
        o=analytics.overview(self.repo,'analyst','analyst')
        self.assertEqual(o['metrics']['affected_population']['sum'],20)
        self.assertEqual(o['records'][0]['severity']['lower'],100)
        self.assertEqual(self.repo.locations()[0]['coordinate_status'],'reviewer_verified')
        requirement=self.repo.create_requirement({'location_id':report['location_id'],'resource':'water','unit':'liters','period':'synthetic-test','quantity':30,'usable_stock':5,'observed_at':self.payload['observed_at'],'source':'synthetic-test'},'coord','coordinator')
        commitment=self.repo.pledge(requirement,'Synthetic organization',3,'synthetic-test','coord','coordinator')
        self.assertEqual(analytics.gaps(self.repo)[0]['confirmed_gap'],25)
        self.repo.assistance_event(commitment,'dispatched',None,'synthetic-test','coord','coordinator')
        self.repo.assistance_event(commitment,'delivered',3,'synthetic-test','coord','coordinator')
        self.assertEqual(analytics.gaps(self.repo)[0]['confirmed_gap'],25)
        self.assertIn('delivery_unconfirmed',[x['kind'] for x in analytics.gaps(self.repo)[0]['warnings']])
        self.repo.assistance_event(commitment,'receipt_confirmed',3,'synthetic-test','coord','coordinator')
        self.assertEqual(analytics.gaps(self.repo)[0]['confirmed_gap'],22)
        writes=[]
        def sheets(url,data=None,headers=None):
            if '?fields=' in url:return {'sheets':[{'properties':{'title':'12_Dashboard_Export'}}]}
            if 'values:batchUpdate' in url:writes.append(data);return {'totalUpdatedRows':2}
            return {'values':[HEADERS]}
        with patch.dict(os.environ,{'GOOGLE_SERVICE_ACCOUNT_FILE':'synthetic-test.json','GOOGLE_SHEET_ID':'synthetic-test'}):
            self.assertEqual(sync_sheets(self.repo,sheets,lambda _:'synthetic-test')['records'],1)
            self.repo.update(report['id'],{'water_need':'low','observed_at':'2026-09-29T12:00:00Z'},self.actor,'contributor','Synthetic correction',1)
            self.assertEqual(sync_sheets(self.repo,sheets,lambda _:'synthetic-test')['records'],0)
        current=self.repo.report(report['id'],self.actor,'contributor')
        self.assertEqual(len(current['history']),2)
        self.assertEqual(current['data']['field_observed_at']['affected_population'],'2026-09-28T12:00:00+00:00')
        self.assertEqual(current['data']['field_observed_at']['water_need'],'2026-09-29T12:00:00+00:00')
        data,_,metadata=export(self.repo,'analyst','analyst',{},'json')
        self.assertEqual(metadata['record_count'],1)
        self.assertNotIn('raw_submission',json.loads(data)['records'][0])
        feedback=self.repo.feedback_for(self.actor,'contributor')
        self.assertIn('assistance_receipt_confirmed',[x['event'] for x in feedback])

    def test_guided_retry_does_not_advance_twice(self):
        conversation=Conversation(self.repo)
        conversation.handle(self.actor,'contributor','/new',1)
        record=self.repo.submit(self.payload,json.dumps(self.payload),self.actor,'contributor','guided-location')
        first=conversation.handle(self.actor,'contributor',record['location_id'],2)
        self.assertEqual(first,Conversation(self.repo).handle(self.actor,'contributor',record['location_id'],2))
        self.assertEqual(conversation.state(self.actor)['index'],1)

    def test_conflicting_duplicate_is_a_signal(self):
        self.repo.submit(self.payload,json.dumps(self.payload),self.actor,'contributor','conflict-first')
        other={**self.payload,'affected_population':21}
        r=self.repo.submit(other,json.dumps(other),self.actor,'contributor','conflict-second')
        self.assertIn('conflicting_observation_same_location_time',r['flags'])
        self.assertEqual(len(self.repo.rows('SELECT * FROM assessments')),2)

    def test_restore_and_tampering(self):
        self.repo.submit(self.payload,json.dumps(self.payload),self.actor,'contributor','backup-pipeline')
        sources=self.root/'source';sources.mkdir();(sources/'source_profile.json').write_text('{"synthetic":true}')
        key=self.root/'private.key';key.write_bytes(os.urandom(32))
        env=patch.dict(os.environ,{'FLOOD_BACKUP_SIGNING_KEY_FILE':str(key)})
        env.start();self.addCleanup(env.stop)
        output=self.root/'backup.tar.gz';bundle(self.repo,output,sources)
        restored=self.root/'restored';manifest=restore_bundle(output,restored)
        self.assertEqual(manifest['verification']['counts']['assessments'],1)
        self.assertTrue((restored/'source_profile.json').exists())
        bad=self.root/'bad.tar.gz'
        with tarfile.open(output) as archive,tarfile.open(bad,'w:gz') as changed:
            for m in archive.getmembers():
                content=archive.extractfile(m).read()
                if m.name=='source_profile.json': content=b'{"changed":true}'
                m.size=len(content);changed.addfile(m,io.BytesIO(content))
        with self.assertRaises(DomainError): inspect_bundle(bad)
        with self.assertRaises(DomainError): restore_bundle(output,restored)
        key.write_bytes(os.urandom(32))
        with self.assertRaises(DomainError): inspect_bundle(output)

    def test_failed_telegram_send_replays_committed_draft(self):
        conversation=Conversation(self.repo)
        conversation.handle(self.actor,'contributor','/new',1)
        report=self.repo.submit(self.payload,json.dumps(self.payload),self.actor,'contributor','retry-location')
        update={'update_id':2,'message':{'from':{'id':99},'chat':{'id':99,'type':'private'},'text':report['location_id']}}
        def failed(url,data=None,headers=None): return {'ok':True,'result':[update]} if url.endswith('getUpdates') else {'ok':False}
        with self.assertRaises(DomainError): telegram_once(self.repo,'synthetic-token',{'99':self.actor},failed)
        self.assertEqual(self.repo.rows("SELECT * FROM integration_state WHERE key='telegram_offset'"),[])
        self.assertEqual(conversation.state(self.actor)['index'],1)
        def succeeds(url,data=None,headers=None): return {'ok':True,'result':[update]} if url.endswith('getUpdates') else {'ok':True}
        telegram_once(self.repo,'synthetic-token',{'99':self.actor},succeeds)
        self.assertEqual(conversation.state(self.actor)['index'],1)
        self.assertEqual(json.loads(self.repo.rows("SELECT value FROM integration_state WHERE key='telegram_offset'")[0]['value']),3)

    def test_worker_lock_and_revocation(self):
        with worker_lock(self.repo,'telegram'):
            with self.assertRaises(DomainError):
                with worker_lock(self.repo,'telegram'):pass
        token,_=login(self.repo,'field','test-private-password')
        deactivate_user(self.repo,self.actor,self.admin,'administrator','Synthetic revocation')
        with self.assertRaises(DomainError):session(self.repo,token)
        with self.assertRaises(DomainError):deactivate_user(self.repo,self.admin,self.admin,'administrator','Cannot remove last admin')

if __name__=='__main__':unittest.main()
