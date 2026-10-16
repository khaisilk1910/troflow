"""V6 regression tests: migration, bank accounts, invoice QR, Zalo outbox, and scoped media."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import db, notify
from app.main import app


class V6Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.prev=db.DB_PATH;self.old_env=os.getenv('BACKUP_DIRECTORY')
  db.DB_PATH=Path(self.temp.name)/'data'/'troflow.db';os.environ['BACKUP_DIRECTORY']=str(Path(self.temp.name)/'backups')
  db.init_db();self.client=TestClient(app)
  resp=self.client.post('/api/auth/setup',json={'username':'root','full_name':'Quản lý','password':'secure-password-123'})
  self.assertEqual(resp.status_code,200,resp.text)
  self.head={'x-csrf-token':resp.json()['csrf']}
  self.prop=self.call('POST','properties',{'name':'Ngõ 303','electric_rate':4000,'water_rate':20000,'service_fee':0})['id']
  self.room=self.call('POST','rooms',{'property_id':self.prop,'code':'P01','rent':3000000})['id']
  self.tenant=self.call('POST','tenants',{'full_name':'Trang','phone':'0982986102','id_number':'001234567890'})['id']
  self.call('POST','contracts',{'room_id':self.room,'tenant_id':self.tenant,'start_date':'2026-01-01','end_date':'2027-12-31','monthly_rent':3000000})
  self.call('POST','readings',{'room_id':self.room,'period':'2026-09','electric_old':100,'electric_new':200,'water_old':10,'water_new':15})
 def tearDown(self):
  self.client.close();db.DB_PATH=self.prev
  if self.old_env is None:os.environ.pop('BACKUP_DIRECTORY',None)
  else:os.environ['BACKUP_DIRECTORY']=self.old_env
  self.temp.cleanup()
 def call(self,method,path,data=None,status=200):
  response=self.client.request(method,'/api/'+path,json=data,headers=self.head)
  self.assertEqual(response.status_code,status,(method,path,response.text))
  return response.json()
 def bank(self,code='970436',account='0987654321',default=1):
  return {'property_id':self.prop,'bank_code':code,'bank_name':'VCB','holder':'NGUYEN VAN A','account_number':account,'is_default':default,'active':1}
 def configure(self,enabled=1,invoice=1,payment=1):
  return {'bot_url':'http://host.docker.internal:3000','media_url':'http://host.docker.internal:8088',
          'account_selection':'0982986102','enabled':enabled,'invoice_enabled':invoice,'payment_enabled':payment,
          'username':'admin','password':'secure-bot-password'}
 def dest(self,thread='123456789012',kind='user',tenant=True,enabled=1):
  return {'name':'Khách Trang','thread_id':thread,'kind':kind,'tenant_id':self.tenant if tenant else None,
          'property_id':self.prop,'enabled':enabled,'on_invoice':1,'on_payment':1}
 def test_migration_non_destructive_and_bank_legacy(self):
  with db.connect() as con:
   con.execute("UPDATE properties SET bank_code='970436',bank_account='123456789',bank_name='NGUYEN VAN A' WHERE id=?",(self.prop,))
   con.execute('PRAGMA user_version=5')
  db.init_db()
  with db.connect() as con:
   self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],11)
   self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0],'ok')
   self.assertEqual(con.execute('SELECT COUNT(*) FROM rooms').fetchone()[0],1)
   self.assertEqual(con.execute('SELECT account_number FROM bank_accounts').fetchone()[0],'123456789')
   self.assertEqual(con.execute('SELECT COUNT(*) FROM tenants').fetchone()[0],1)
 def test_bank_crud_duplicate_default_and_vietqr(self):
  one=self.call('POST','v6/banks',self.bank())['id']
  self.call('POST','v6/banks',self.bank(),409)
  two=self.call('POST','v6/banks',self.bank('970422','567891234',1))['id']
  all_banks=self.call('GET','v6/banks')
  self.assertEqual(next(b for b in all_banks if b['id']==one)['is_default'],0)
  self.assertEqual(next(b for b in all_banks if b['id']==two)['is_default'],1)
  self.call('POST','invoices/generate',{'period':'2026-10'})
  invoice=self.call('GET','invoices')[0]
  self.assertEqual(invoice['electric_old'],100)
  self.assertEqual(invoice['electric_new'],200)
  qr=self.call('GET',f'v6/invoices/{invoice["id"]}/payment-qr')
  self.assertEqual(qr['account_number'],'567891234')
  self.assertIn('img.vietqr.io',qr['qr_url'])
  self.assertIn('HD00001',qr['content'])
  self.call('DELETE',f'v6/banks/{two}')
  self.assertEqual(self.call('GET',f'v6/invoices/{invoice["id"]}/payment-qr')['account_number'],'0987654321')
  self.call('DELETE',f'v6/banks/{one}')
  self.assertFalse(self.call('GET',f'v6/invoices/{invoice["id"]}/payment-qr')['configured'])
 def test_config_validation_credentials_masked_and_toggle(self):
  bad=self.configure();bad['bot_url']='http://example.org:3000';self.call('PUT','v6/zalo/settings',bad,400)
  self.call('PUT','v6/zalo/settings',self.configure())
  info=self.call('GET','v6/zalo/settings')
  self.assertTrue(info['credentials_configured'])
  self.assertNotIn('password',info)
  file=notify._secret_file();self.assertTrue(file.is_file());self.assertEqual(file.stat().st_mode&0o777,0o600)
  no_password=self.configure(enabled=0);no_password['password']=''
  self.call('PUT','v6/zalo/settings',no_password)
  self.assertEqual(self.call('GET','v6/zalo/settings')['enabled'],0)
 def test_recipient_crud_and_automatic_outbox_idempotency(self):
  self.call('PUT','v6/zalo/settings',self.configure())
  dest_id=self.call('POST','v6/zalo/destinations',self.dest())['id']
  self.call('POST','v6/zalo/destinations',self.dest('111222333444','group',tenant=False))
  self.call('POST','invoices/generate',{'period':'2026-10'})
  inv=self.call('GET','invoices')[0]
  with db.tx() as con:
   notify.enqueue_invoice_event(con,inv['id'],'invoice')
  logs=self.call('GET','v6/zalo/outbox')
  invoice_logs=[item for item in logs if item['event']=='invoice']
  welcome_logs=[item for item in logs if item['event']=='destination_welcome']
  self.assertEqual(len(invoice_logs),2)
  self.assertEqual(len(welcome_logs),2)
  self.assertTrue(all(x['status']=='pending' for x in invoice_logs))
  self.call('POST','payments',{'invoice_id':inv['id'],'amount':inv['total'],'method':'cash','paid_at':'2026-10-22'})
  self.assertEqual(len(self.call('GET','v6/zalo/outbox')),6)
  # The sending worker uses the uploaded bot's exact session endpoints.
  with patch('app.notify._bot_send',return_value={'success':True}) as sender:
   self.assertEqual(notify.process_outbox(),4)
   self.assertEqual(sender.call_count,4)
   endpoints=[call.args[3] for call in sender.call_args_list]
   self.assertEqual(sum(v is not None for v in endpoints),4)
  self.assertTrue(all(x['status']=='sent' for x in self.call('GET','v6/zalo/outbox') if x['event']!='destination_welcome'))
  self.call('DELETE',f'v6/zalo/destinations/{dest_id}')
  self.assertEqual(len(self.call('GET','v6/zalo/destinations')),1)
 def test_manual_log_failed_retry_and_opaque_media(self):
  self.call('PUT','v6/zalo/settings',self.configure())
  did=self.call('POST','v6/zalo/destinations',self.dest())['id']
  self.call('POST','invoices/generate',{'period':'2026-10'})
  inv=self.call('GET','invoices')[0]
  self.call('POST','v6/zalo/send',{'destination_id':did,'invoice_id':inv['id'],'message':'Nhắc thanh toán','include_image':1})
  with patch('app.notify._bot_send',side_effect=RuntimeError('Bot unavailable')):
   notify.process_outbox()
  failures=[x for x in self.call('GET','v6/zalo/outbox') if x['status']=='failed']
  self.assertTrue(failures)
  self.assertEqual(notify.process_outbox(),0)
  self.call('POST',f'v6/zalo/outbox/{failures[0]["id"]}/retry',{})
  with db.connect() as con:tokens=db.rows(con,'SELECT token FROM notification_media')
  self.assertTrue(tokens)
  self.assertEqual(self.client.get('/api/integration-media/wrong').status_code,404)
  # When the optional Pillow is present the actual PNG can be generated on the fly.
  try:import PIL
  except ImportError:return
  with patch('app.notify.urllib.request.urlopen',side_effect=OSError('offline')):
   resp=self.client.get('/api/integration-media/'+tokens[0]['token'])
  self.assertEqual(resp.status_code,200,resp.text[:100] if resp.status_code!=200 else '')
  self.assertTrue(resp.content.startswith(b'\x89PNG'))
 def test_bot_adapter_real_session_request_shapes(self):
  from http.server import HTTPServer,BaseHTTPRequestHandler
  import threading,json
  captured=[]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
    captured.append((self.path,payload,self.headers.get('Cookie','')))
    if self.path=='/api/login':
     result={'success':True};self.send_response(200);self.send_header('Set-Cookie','zalo-server.sid=simulated; Path=/')
    else:
     result={'success':True,'data':{'msgId':'ok'}};self.send_response(200)
    self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(result).encode())
  server=HTTPServer(('127.0.0.1',0),Handler)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   self.call('PUT','v6/zalo/settings',self.configure())
   setting={'bot_url':f'http://127.0.0.1:{server.server_port}','account_selection':'0982986102'}
   notify._bot_send(setting,{'thread_id':'123456789012','kind':'user'},'Nội dung')
   notify._bot_send(setting,{'thread_id':'987654321012','kind':'group'},'Hóa đơn','http://host.docker.internal:8088/api/integration-media/securetoken')
  finally:server.shutdown();server.server_close();thread.join(timeout=2)
  self.assertEqual([x[0] for x in captured],['/api/login','/api/sendMessageByAccount','/api/login','/api/sendImageByAccount'])
  self.assertEqual(captured[1][1]['type'],0)
  self.assertEqual(captured[3][1]['type'],1)
  self.assertEqual(captured[3][1]['accountSelection'],'0982986102')
  self.assertIn('zalo-server.sid',captured[1][2])
 def test_admin_only(self):
  self.call('POST','users',{'username':'nv001','full_name':'Nhân viên','password':'long-password-123','role':'staff'})
  staff=TestClient(app)
  login=staff.post('/api/auth/login',json={'username':'nv001','password':'long-password-123'})
  self.assertEqual(login.status_code,200)
  token={'x-csrf-token':login.json()['csrf']}
  self.assertEqual(staff.get('/api/v6/banks').status_code,403)
  self.assertEqual(staff.get('/api/v6/zalo/settings').status_code,403)
  self.assertEqual(staff.post('/api/v6/zalo/send',json={'destination_id':1,'message':'x'},headers=token).status_code,403)
  staff.close()

if __name__=='__main__':unittest.main()
