import io
import os
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
from app import db,main,tenant_portal

class TenantIsolationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.original=db.DB_PATH;self.uploads=tenant_portal.UPLOADS
  self.oldbackup=os.getenv('BACKUP_DIRECTORY');os.environ['BACKUP_DIRECTORY']=str(Path(self.tmp.name)/'backups')
  db.DB_PATH=Path(self.tmp.name)/'data'/'troflow.db';tenant_portal.UPLOADS=Path(self.tmp.name)/'uploads';db.init_db()
  self.admin=TestClient(main.app)
  auth=self.admin.post('/api/auth/setup',json={'username':'admin','full_name':'Chủ nhà','password':'a-strong-password-123'}).json()
  self.headers={'x-csrf-token':auth['csrf']}
  self.prop=self.call('POST','properties',{'name':'Ngõ 303'})['id']
  self.prop2=self.call('POST','properties',{'name':'Ngõ 404'})['id']
  self.room=self.call('POST','rooms',{'property_id':self.prop,'code':'P01','rent':3000000})['id']
  self.room2=self.call('POST','rooms',{'property_id':self.prop2,'code':'P09','rent':4000000})['id']
  self.tenant1=self.call('POST','tenants',{'full_name':'Nguyễn Thị Trang','phone':'0982986102','id_number':'001234567890','portal_enabled':True,'portal_property_id':self.prop})
  self.tenant2=self.call('POST','tenants',{'full_name':'Nguyễn Văn Hùng','phone':'0982986103','id_number':'001234567891','portal_enabled':True,'portal_property_id':self.prop2})
  self.cid1=self.call('POST','contracts',{'room_id':self.room,'tenant_id':self.tenant1['id'],'start_date':'2025-01-01','end_date':'2028-12-31','monthly_rent':3000000})['id']
  self.cid2=self.call('POST','contracts',{'room_id':self.room2,'tenant_id':self.tenant2['id'],'start_date':'2025-01-01','end_date':'2028-12-31','monthly_rent':4000000})['id']
  self.client1=TestClient(main.app);self.client2=TestClient(main.app)
 def tearDown(self):
  self.admin.close();self.client1.close();self.client2.close();db.DB_PATH=self.original;tenant_portal.UPLOADS=self.uploads
  if self.oldbackup is None:os.environ.pop('BACKUP_DIRECTORY',None)
  else:os.environ['BACKUP_DIRECTORY']=self.oldbackup
  self.tmp.cleanup()
 def call(self,method,path,json=None,status=200):
  r=self.admin.request(method,'/api/'+path,json=json,headers=self.headers)
  self.assertEqual(r.status_code,status,r.text);return r.json()
 def login(self,client,account,public=False):
  c=account['portal_credentials'];self.assertIsNotNone(c)
  with patch.object(tenant_portal,'PUBLIC_MODE',public):
   r=client.post('/api/tenant/auth/login',json={'phone':c['username'],'password':c['password'],'access_code':c['access_code']})
  self.assertEqual(r.status_code,200,r.text)
  return {'x-csrf-token':r.json()['csrf']}
 def pic(self):
  b=io.BytesIO();Image.new('RGB',(12,12),'blue').save(b,format='PNG');return b.getvalue()
 def baseline(self):
  prev=(date.today().replace(day=1)-timedelta(days=1)).strftime('%Y-%m')
  # Older reading preceding the target submission period.
  d=date.today().replace(day=1)-timedelta(days=32)
  past=d.strftime('%Y-%m')
  if past==prev:past=(d-timedelta(days=35)).strftime('%Y-%m')
  self.call('POST','readings',{'room_id':self.room,'period':past,'electric_old':10,'electric_new':100,'water_old':2,'water_new':10})
  return date.today().strftime('%Y-%m')
 def test_login_and_strict_scope(self):
  self.assertEqual(self.tenant1['portal_credentials']['password'],'trang_ngo303')
  self.login(self.client1,self.tenant1)
  self.login(self.client2,self.tenant2)
  a=self.client1.get('/api/tenant/home').json();b=self.client2.get('/api/tenant/home').json()
  self.assertEqual(len(a['contracts']),1);self.assertEqual(a['contracts'][0]['room_code'],'P01')
  self.assertEqual(len(b['contracts']),1);self.assertEqual(b['contracts'][0]['room_code'],'P09')
  self.assertNotIn('Hùng',str(a));self.assertNotIn('Trang',str(b))
  for endpoint in ('/api/tenants','/api/users','/api/export/tenants','/api/v6/banks','/api/backup'):
   self.assertEqual(self.client1.get(endpoint).status_code,401,endpoint)
  self.assertEqual(self.client1.get('/api/tenant/admin/submissions').status_code,401)
  self.assertEqual(self.client1.get('/api/tenant/owner/photo').status_code,404)
 def test_home_rates_prepayments_refunds_and_tenant_scope(self):
  self.call('PUT','properties/'+str(self.prop),{'name':'Ngõ 303','electric_rate':4100,'water_rate':27000,'service_fee':120000})
  first=self.call('POST','v2/prepayments',{'contract_id':self.cid1,'start_period':'2026-11','end_period':'2027-01','paid_on':'2026-10-15','method':'transfer'})
  self.assertEqual(first['months'],3)
  other=self.call('POST','v2/prepayments',{'contract_id':self.cid2,'start_period':'2026-11','end_period':'2026-11','paid_on':'2026-10-15','method':'cash'})
  self.assertNotEqual(first['id'],other['id'])
  with db.connect() as con:
   coverage=db.one(con,'SELECT id FROM rent_coverage WHERE batch_id=? AND period=?',(first['id'],'2026-12'))
  self.call('POST',f'v2/prepayments/{coverage["id"]}/refund',{'refunded_on':'2026-10-15','reason':'Đã hoàn trả kỳ tháng'})
  self.login(self.client1,self.tenant1)
  self.login(self.client2,self.tenant2)
  a=self.client1.get('/api/tenant/home').json()
  b=self.client2.get('/api/tenant/home').json()
  room=a['contracts'][0]
  self.assertEqual((room['electric_rate'],room['water_rate'],room['service_fee']),(4100,27000,120000))
  self.assertEqual(room['due_day'],5)
  self.assertEqual(len(a['prepayments']),1)
  batch=a['prepayments'][0]
  self.assertEqual(batch['total_paid'],9000000)
  self.assertEqual(batch['active_amount'],6000000)
  self.assertEqual(batch['refunded_amount'],3000000)
  self.assertEqual([p['status'] for p in batch['periods']],['active','refunded','active'])
  self.assertEqual(len(b['prepayments']),1)
  self.assertEqual(b['prepayments'][0]['room_code'],'P09')
  self.assertNotIn('P09',str(a))
  self.assertNotIn('P01',str(b))
 def test_public_requires_random_code(self):
  c=self.tenant1['portal_credentials']
  with patch.object(tenant_portal,'PUBLIC_MODE',True):
   self.assertEqual(self.client1.post('/api/tenant/auth/login',json={'phone':c['username'],'password':c['password']}).status_code,401)
   self.assertEqual(self.client1.post('/api/tenant/auth/login',json={'phone':c['username'],'password':c['password'],'access_code':c['access_code']}).status_code,200)
 def test_disable_revokes_active_session(self):
  self.login(self.client1,self.tenant1)
  data={'full_name':'Nguyễn Thị Trang','phone':'0982986102','id_number':'001234567890','portal_enabled':False}
  self.call('PUT','tenants/'+str(self.tenant1['id']),data)
  self.assertEqual(self.client1.get('/api/tenant/home').status_code,401)
 def test_owner_visibility_strict(self):
  self.call('PUT','tenant/admin/owner/'+str(self.prop),{'name':'Chủ nhà A','phone':'0900123456','email':'private@example.com','address':'Secret private address','show_name':True,'show_email':False,'show_phone':True,'show_address':False})
  self.login(self.client1,self.tenant1)
  self.login(self.client2,self.tenant2)
  a=self.client1.get('/api/tenant/home').json();b=self.client2.get('/api/tenant/home').json()
  self.assertEqual(a['owner']['name'],'Chủ nhà A');self.assertEqual(a['owner']['phone'],'0900123456')
  self.assertNotIn('private@example.com',str(a));self.assertNotIn('Secret private',str(a))
  self.assertIsNone(b['owner'])
 def test_submission_approval_images_and_cross_tenant_block(self):
  period=self.baseline();head=self.login(self.client1,self.tenant1)
  def submit(client,headers,contract):
   return client.post('/api/tenant/readings/submit',data={'contract_id':str(contract),'period':period,'electric_new':'150','water_new':'15'},files={'electric_photo':('elec.png',self.pic(),'image/png'),'water_photo':('water.png',self.pic(),'image/png')},headers=headers)
  self.assertEqual(submit(self.client1,head,self.cid2).status_code,404)
  r=submit(self.client1,head,self.cid1);self.assertEqual(r.status_code,200,r.text);sid=r.json()['id']
  self.assertEqual(submit(self.client1,head,self.cid1).status_code,409)
  self.assertEqual(self.client2.get(f'/api/tenant/submissions/{sid}/photo/electric').status_code,401)
  self.login(self.client2,self.tenant2)
  self.assertEqual(self.client2.get(f'/api/tenant/submissions/{sid}/photo/electric').status_code,404)
  self.assertEqual(self.client1.get(f'/api/tenant/submissions/{sid}/photo/electric').status_code,200)
  with db.connect() as con:self.assertIsNone(db.one(con,'SELECT id FROM readings WHERE room_id=? AND period=?',(self.room,period)))
  self.call('POST',f'tenant/admin/submissions/{sid}/review',{'decision':'approve'})
  with db.connect() as con:
   meter=db.one(con,'SELECT * FROM readings WHERE room_id=? AND period=?',(self.room,period))
   self.assertEqual(meter['electric_old'],100);self.assertEqual(meter['electric_new'],150)
  self.assertEqual(self.call('POST',f'tenant/admin/submissions/{sid}/review',{'decision':'approve'},409)['detail'],'Đề nghị đã được xử lý.')
 def test_migration_idempotent(self):
  db.init_db();db.init_db()
  with db.connect() as con:
   self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],11)
   self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0],'ok')
   self.assertEqual(con.execute('SELECT COUNT(*) FROM tenants').fetchone()[0],2)
 def test_owner_photo_requires_public_consent(self):
  self.login(self.client1,self.tenant1)
  r=self.admin.post(f'/api/tenant/admin/owner/{self.prop}/photo',files={'file':('p.png',self.pic(),'image/png')},headers=self.headers)
  self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(self.client1.get('/api/tenant/owner/photo').status_code,404)
  self.call('PUT',f'tenant/admin/owner/{self.prop}',{'name':'Chủ nhà','show_name':True,'show_photo':True})
  self.assertEqual(self.client1.get('/api/tenant/owner/photo').status_code,200)
  self.login(self.client2,self.tenant2)
  self.assertEqual(self.client2.get('/api/tenant/owner/photo').status_code,404)
 def test_admin_reset_revokes_old_access_code(self):
  head=self.login(self.client1,self.tenant1)
  old=self.tenant1['portal_credentials']
  newer=self.call('POST',f'tenant/admin/accounts/{self.tenant1["id"]}/reset',{})
  self.assertNotEqual(old['access_code'],newer['access_code'])
  self.assertEqual(self.client1.get('/api/tenant/home').status_code,401)
  with patch.object(tenant_portal,'PUBLIC_MODE',True):
   self.assertEqual(self.client1.post('/api/tenant/auth/login',json={'phone':old['username'],'password':old['password'],'access_code':old['access_code']}).status_code,401)
   self.assertEqual(self.client1.post('/api/tenant/auth/login',json={'phone':newer['username'],'password':newer['password'],'access_code':newer['access_code']}).status_code,200)
 def test_account_property_must_match_active_contract(self):
  r=self.admin.put(f'/api/tenants/{self.tenant1["id"]}',json={'full_name':'Nguyễn Thị Trang','phone':'0982986102','id_number':'001234567890','portal_enabled':True,'portal_property_id':self.prop2},headers=self.headers)
  self.assertEqual(r.status_code,409,r.text)
  with db.connect() as con:
   self.assertEqual(db.one(con,'SELECT property_id FROM tenant_portal_accounts WHERE tenant_id=?',(self.tenant1['id'],))['property_id'],self.prop)
 def test_tenant_cannot_change_password(self):
  self.login(self.client1,self.tenant1)
  self.assertEqual(self.client1.post('/api/auth/change-password',json={'current_password':'a','new_password':'1234'}).status_code,401)

if __name__=='__main__':unittest.main()
