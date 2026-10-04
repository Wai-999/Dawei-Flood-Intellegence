import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from flood.auth import create_user
from flood.domain import DomainError
from flood.repository import Repository
from flood.integrations import telegram_once

spec = importlib.util.spec_from_file_location('telegram_pilot', Path(__file__).resolve().parents[1]/'infra/telegram_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class TelegramPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prod = Repository(Path(self.tmp.name)/'production.sqlite3')
        self.iso = Repository(Path(self.tmp.name)/'exercise.sqlite3')
        self.actor = create_user(self.prod, 'TFUCC', 'administrator', 'private-test-password')
        with self.prod.transaction() as src, self.iso.transaction() as dst:
            row = src.execute('SELECT * FROM users WHERE id=?', (self.actor,)).fetchone()
            dst.execute('INSERT INTO users VALUES('+','.join('?' for _ in row)+')', tuple(row))
            self.location = self.iso._location(dst, {'state_region':'TEST ONLY','township':'Synthetic','village':'Exercise fixture'})
        self.current = datetime(2026,10,4,9,0,tzinfo=timezone.utc)
        self.config = {'operator':'TFUCC','scope':'descriptive-only isolated technical exercise','session_seconds':3600,
                       'authorization_expires_at':(self.current+timedelta(hours=2)).isoformat()}
        self.router = pilot.PilotConversation(self.prod,self.iso,self.config,lambda:self.current)

    def handle(self, text, update):
        return self.router.handle(self.actor,'administrator',text,update)

    def test_confirm_correction_and_replay_stay_isolated(self):
        self.handle('/pilot_start',1)
        self.handle('#FLOOD_REPORT\nlocation_id: '+self.location+'\nobserved_at: 2026-10-04T09:00:00Z\naffected_population: 20\nsource_reference: TECHNICAL TEST ONLY',2)
        self.handle('/preview',3)
        response = self.handle('/confirm',4)
        self.assertIn('TECHNICAL TEST',response)
        self.assertEqual(self.handle('/confirm',4),response)
        self.assertEqual(self.prod.rows('SELECT * FROM assessments'),[])
        self.assertEqual(len(self.iso.rows('SELECT * FROM assessments')),1)
        report = self.iso.rows('SELECT id FROM assessments')[0]['id']
        self.handle('/update '+report,5)
        self.handle('#FLOOD_REPORT\naffected_population: 21\nsource_reference: TECHNICAL TEST CORRECTION',6)
        self.handle('/reason Technical correction exercise',7)
        self.handle('/preview',8)
        self.handle('/confirm',9)
        self.assertEqual(self.iso.rows('SELECT current_version FROM assessments')[0]['current_version'],2)
        self.assertEqual(self.prod.rows('SELECT * FROM assessments'),[])

    def test_expired_active_mode_never_submits_to_production(self):
        self.handle('/pilot_start',1)
        self.current += timedelta(hours=1)
        self.assertIn('No report was submitted',self.handle('/confirm',2))
        recreated = pilot.PilotConversation(self.prod,self.iso,self.config,lambda:self.current)
        self.assertIn('No report was submitted',recreated.handle(self.actor,'administrator','/new',3))
        self.assertEqual(self.prod.rows('SELECT * FROM submissions'),[])
        self.handle('/pilot_end',4)
        self.assertFalse(self.router.session()['active'])

    def test_control_send_retry_does_not_renew_session(self):
        self.handle('/pilot_start',1)
        expiry = self.router.session()['expires_at']
        self.current += timedelta(minutes=10)
        self.handle('/pilot_start',1)
        self.assertEqual(self.router.session()['expires_at'],expiry)
        response = self.handle('/pilot_end',2)
        self.assertEqual(self.handle('/pilot_end',2),response)

    def test_invalid_authority_or_same_database_rejected(self):
        with self.assertRaises(ValueError):
            pilot.PilotConversation(self.prod,self.prod,self.config)
        with self.assertRaises(DomainError):
            self.router.handle('unapproved','administrator','/pilot_start',1)
        config = dict(self.config, session_seconds=3601)
        with self.assertRaises(ValueError):
            pilot.PilotConversation(self.prod,self.iso,config)
        config = dict(self.config, scope='operational')
        with self.assertRaises(ValueError):
            pilot.PilotConversation(self.prod,self.iso,config)

    def test_single_approved_transport_checkpoint_after_failed_reply(self):
        from flood import integrations
        from unittest.mock import patch
        update={'update_id':10,'message':{'from':{'id':123},'chat':{'id':123,'type':'private'},'text':'/pilot_start'}}
        def failed(url,data=None,headers=None):
            return {'ok':True,'result':[update]} if url.endswith('getUpdates') else {'ok':False}
        with patch.object(integrations,'Conversation',lambda repo:self.router):
            with self.assertRaises(DomainError):
                telegram_once(self.prod,'test-token',{'123':self.actor},failed)
            self.assertEqual(self.prod.rows("SELECT * FROM integration_state WHERE key='telegram_offset'"),[])
            expiry = self.router.session()['expires_at']
            def success(url,data=None,headers=None):
                return {'ok':True,'result':[update]} if url.endswith('getUpdates') else {'ok':True}
            telegram_once(self.prod,'test-token',{'123':self.actor},success)
        self.assertEqual(self.router.session()['expires_at'],expiry)
        self.assertEqual(json.loads(self.prod.rows("SELECT value FROM integration_state WHERE key='telegram_offset'")[0]['value']),11)

    def test_ordinary_help_uses_existing_production_conversation(self):
        response = self.handle('/help',1)
        self.assertIn('Commands:',response)
        self.assertNotIn('TECHNICAL TEST',response)
        self.assertEqual(self.iso.rows('SELECT * FROM drafts'),[])
