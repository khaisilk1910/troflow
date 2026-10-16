"""Zalo Bot connection diagnostics and one-time recipient welcome regression tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from fastapi.testclient import TestClient
from app import main, db, notify


class ZaloConnectionWelcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / 'troflow.db'
        db.init_db()
        self.client = TestClient(main.app)
        response = self.client.post('/api/auth/setup', json={
            'username':'admin', 'full_name':'Chủ nhà', 'password':'test-password-strong-123'})
        self.assertEqual(response.status_code,200,response.text)
        self.head = {'x-csrf-token': response.json()['csrf']}

    def tearDown(self):
        self.client.close()
        db.DB_PATH = self.old_db
        self.tmp.cleanup()

    def config(self, enabled=1, password='bot-secret-123'):
        return {'bot_url':'http://host.docker.internal:3000',
                'media_url':'http://host.docker.internal:8001',
                'account_selection':'123456789', 'username':'admin',
                'password':password, 'enabled':enabled,
                'invoice_enabled':1,'payment_enabled':1,'ticket_enabled':1}

    def dest(self, enabled=1):
        return {'name':'Nơi nhận chủ nhà','thread_id':'12345678901234',
                'kind':'group','enabled':enabled,'on_invoice':1,
                'on_payment':1,'on_ticket':1}

    def call(self, method, path, data=None, status=200):
        resp=self.client.request(method,'/api/v6/zalo/'+path,headers=self.head,json=data)
        self.assertEqual(resp.status_code,status,resp.text)
        return resp.json()

    def test_connection_probe_only_claims_bot_login_verified(self):
        with patch.object(notify,'_http_json',return_value={'success':True}) as login:
            result=self.call('PUT','settings',self.config())
            self.assertTrue(result['connection']['connected'])
            self.assertEqual(result['connection']['status'],'connected')
            self.assertIn('Chưa kiểm chứng gửi',result['connection']['message'])
            self.assertEqual(login.call_args.args[1],self.config()['bot_url']+'/api/login')
            status=self.call('GET','connection')
            self.assertEqual(status['status'],'connected')
            self.assertNotIn('password',str(status))
        setting=self.call('GET','settings')
        self.assertNotIn('password',setting)
        self.assertTrue(setting['credentials_configured'])

    def test_reachable_but_bad_login_and_unreachable_are_distinct(self):
        with patch.object(notify,'_http_json',return_value={'success':False}):
            self.call('PUT','settings',self.config())
            result=self.call('GET','connection')
            self.assertEqual(result['status'],'auth_failed')
        with patch.object(notify,'_http_json',side_effect=URLError('connect refused')):
            result=self.call('GET','connection')
            self.assertEqual(result['status'],'unreachable')
            self.assertFalse(result['connected'])
            self.assertNotIn('connect refused',result['message'])

    def test_new_recipient_receives_exactly_one_confirmation(self):
        with patch.object(notify,'_http_json',return_value={'success':True}):
            self.call('PUT','settings',self.config())
        with patch.object(notify,'_bot_send',return_value={'success':True}) as sender:
            result=self.call('POST','destinations',self.dest())
            self.assertEqual(result['welcome_status'],'pending')
            ident=result['welcome_notification_id']
            self.assertEqual(self.call('GET',f'outbox/{ident}/status')['status'],'sent')
            self.assertEqual(sender.call_count,1)
            args=sender.call_args.args
            self.assertEqual(args[1]['thread_id'],self.dest()['thread_id'])
            self.assertEqual(args[1]['kind'],'group')
            self.assertIn('đã được thêm vào danh sách nơi nhận',args[2])
            self.assertIn('Yêu cầu sửa chữa',args[2])
            self.call('PUT',f'destinations/{result["id"]}',self.dest())
            self.assertEqual(sender.call_count,1)
            self.assertEqual(notify.process_outbox(),0)
        recipient=self.call('GET','destinations')[0]
        self.assertEqual(recipient['welcome_status'],'sent')
        logs=[x for x in self.call('GET','outbox') if x['event']=='destination_welcome']
        self.assertEqual(len(logs),1)
        self.assertEqual(logs[0]['attempts'],1)

    def test_delivery_failure_does_not_discard_recipient(self):
        with patch.object(notify,'_http_json',return_value={'success':True}):
            self.call('PUT','settings',self.config())
        with patch.object(notify,'_bot_send',side_effect=RuntimeError('Không tìm thấy nhóm Zalo')):
            result=self.call('POST','destinations',self.dest())
        status=self.call('GET',f'outbox/{result["welcome_notification_id"]}/status')
        self.assertEqual(status['status'],'failed')
        self.assertIn('Không tìm thấy nhóm',status['error'])
        self.assertEqual(self.call('GET','destinations')[0]['id'],result['id'])
        with patch.object(notify,'_bot_send',return_value={'success':True}) as sender:
            self.call('POST',f'outbox/{result["welcome_notification_id"]}/retry',{})
            notify.process_outbox()
            self.assertEqual(sender.call_count,1)
        self.assertEqual(self.call('GET',f'outbox/{result["welcome_notification_id"]}/status')['status'],'sent')

    def test_channel_disabled_and_inactive_recipient_do_not_send(self):
        with patch.object(notify,'_http_json',return_value={'success':True}):
            self.call('PUT','settings',self.config(enabled=0))
        with patch.object(notify,'_bot_send') as sender:
            first=self.call('POST','destinations',self.dest())
            self.assertEqual(first['welcome_status'],'failed')
            status=self.call('GET',f'outbox/{first["welcome_notification_id"]}/status')
            self.assertIn('Chưa bật kênh',status['error'])
            second=self.call('POST','destinations',{**self.dest(enabled=0),'thread_id':'23456789012345'})
            self.assertEqual(second['welcome_status'],'skipped')
            self.assertIsNone(second['welcome_notification_id'])
            sender.assert_not_called()

    def test_new_status_apis_are_admin_only(self):
        r=self.client.post('/api/users',json={'username':'staff', 'full_name':'Nhân viên',
            'password':'strong-password-123','role':'staff'},headers=self.head)
        self.assertEqual(r.status_code,200,r.text)
        staff=TestClient(main.app)
        staff.post('/api/auth/login',json={'username':'staff','password':'strong-password-123'})
        self.assertEqual(staff.get('/api/v6/zalo/connection').status_code,403)
        self.assertEqual(staff.get('/api/v6/zalo/outbox/1/status').status_code,403)
        staff.close()


if __name__=='__main__': unittest.main()
