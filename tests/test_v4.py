"""V4 regression: safe month changes, duplicate detection, photos, ACL and legacy migration."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import db, advanced
from app.main import app

# A valid 1 x 1 PNG upload; this endpoint validates the header and size.
PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082')

class V4IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.old_db=db.DB_PATH
  self.old_uploads=advanced.UPLOADS
  db.DB_PATH=Path(self.temp.name)/'db.sqlite3'
  advanced.UPLOADS=Path(self.temp.name)/'uploads'
  os.environ['BACKUP_DIRECTORY']=str(Path(self.temp.name)/'backups')
  db.init_db()
  self.client=TestClient(app)
  r=self.client.post('/api/auth/setup',json={'full_name':'Chủ nhà','username':'owner','password':'Test-owner-password123'})
  self.assertEqual(r.status_code,200,r.text)
  self.head={'X-CSRF-Token':r.json()['csrf']}
  self.prop=self.req('POST','properties',{'name':'Nhà 1','service_fee':100000}).json()['id']
  self.room=self.req('POST','rooms',{'property_id':self.prop,'code':'P01','rent':2000000}).json()['id']
  self.tenant=self.req('POST','tenants',{'full_name':'Người A','phone':'0912345678','id_number':'001234567890'}).json()['id']
  self.contract=self.req('POST','contracts',{'room_id':self.room,'tenant_id':self.tenant,'start_date':'2026-01-01','end_date':'2027-12-31','monthly_rent':2000000}).json()['id']
  self.reader={'room_id':self.room,'period':'2026-06','electric_old':10,'electric_new':20,'water_old':2,'water_new':4}
 def tearDown(self):
  self.client.close();db.DB_PATH=self.old_db;advanced.UPLOADS=self.old_uploads;self.temp.cleanup()
 def req(self,method,path,data=None,expected=200,client=None,headers=None):
  r=(client or self.client).request(method,'/api/'+path,json=data,headers=headers or self.head)
  self.assertEqual(r.status_code,expected,(method,path,r.text))
  return r
 def test_meter_edit_period_duplicate_and_delete(self):
  id1=self.req('POST','readings',self.reader).json()['id']
  self.req('POST','readings',self.reader,409)
  id2=self.req('POST','readings',{**self.reader,'period':'2026-07','electric_old':20,'electric_new':30}).json()['id']
  self.req('PUT',f'readings/{id1}',{**self.reader,'period':'2026-07'},409)
  self.req('PUT',f'readings/{id1}',{**self.reader,'period':'2026-08','electric_new':29})
  rows=self.req('GET','readings').json();self.assertEqual({r['period'] for r in rows},{'2026-07','2026-08'})
  self.req('DELETE',f'readings/{id2}');self.assertEqual(len(self.req('GET','readings').json()),1)
  self.req('POST','invoices/generate',{'period':'2026-08'})
  self.req('DELETE',f'readings/{id1}',expected=409)
  self.req('PUT',f'readings/{id1}',{**self.reader,'period':'2026-09'},409)
 def test_tenant_meter_photos_and_version(self):
  with db.connect() as con:
   self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],8)
   self.assertIn('photo_path',{r[1] for r in con.execute('PRAGMA table_info(tenants)')})
  id1=self.req('POST','readings',self.reader).json()['id']
  for category,ref in [('tenant',self.tenant),('electric',id1),('water',id1)]:
   r=self.client.post('/api/v2/files',data={'category':category,'related_id':str(ref)},
                      files={'file':('test.png',io.BytesIO(PNG),'image/png')},headers=self.head)
   self.assertEqual(r.status_code,200,r.text)
   file=r.json()['name']
   img=self.client.get('/api/v2/files/'+file)
   self.assertEqual(img.status_code,200,img.text)
  tenants=self.req('GET','tenants').json();self.assertTrue(tenants[0]['photo_path'])
  readings=self.req('GET','readings').json();self.assertTrue(readings[0]['electric_photo']);self.assertTrue(readings[0]['water_photo'])
 def test_admin_payment_correction_and_overpayment_guard(self):
  self.req('POST','readings',self.reader)
  self.req('POST','invoices/generate',{'period':'2026-06'})
  invoice=self.req('GET','invoices').json()[0]
  payment=self.req('POST','payments',{'invoice_id':invoice['id'],'amount':500000,'paid_at':'2026-06-20','method':'cash'}).json()['id']
  self.req('PUT',f'payments/{payment}',{'amount':400000,'paid_at':'2026-06-21','method':'transfer','note':'Điều chỉnh giao dịch'})
  after=self.req('GET','invoices').json()[0];self.assertEqual(after['paid'],400000)
  self.req('PUT',f'payments/{payment}',{'amount':invoice['total']+1,'paid_at':'2026-06-21','method':'transfer'},409)
  self.assertEqual(self.req('GET','invoices').json()[0]['paid'],400000)
  logs=self.req('GET','audit').json()
  self.assertTrue(any(x['entity']=='payment' and x['action']=='update' for x in logs))
 def test_permission_and_cross_property_scope(self):
  uid=self.req('POST','users',{'username':'employee','full_name':'Nhân viên','password':'Employee-password123','role':'staff'}).json()['id']
  newprop=self.req('POST','properties',{'name':'Cơ sở khác'}).json()['id']
  other=self.req('POST','rooms',{'property_id':newprop,'code':'P99','rent':2000000}).json()['id']
  t=self.req('POST','tenants',{'full_name':'B','phone':'0909','id_number':'001234567890'}).json()['id']
  self.req('POST','contracts',{'room_id':other,'tenant_id':t,'start_date':'2026-01-01','end_date':'2027-12-31','monthly_rent':2000000})
  other_id=self.req('POST','readings',{**self.reader,'room_id':other}).json()['id']
  from app.permissions import defaults
  perms=defaults('manager');perms.update({'readings.view':True,'readings.edit':True,'readings.delete':False,'readings.record':True})
  self.req('PUT',f'v2/access/{uid}',{'job_role':'manager','property_ids':[self.prop], 'permissions':perms})
  employee=TestClient(app)
  try:
   r=employee.post('/api/auth/login',json={'username':'employee','password':'Employee-password123'})
   self.assertEqual(r.status_code,200,r.text)
   h={'X-CSRF-Token':r.json()['csrf']}
   self.req('DELETE',f'readings/{other_id}',expected=403,client=employee,headers=h)
   self.req('PUT',f'readings/{other_id}',{**self.reader,'room_id':self.room},expected=403,client=employee,headers=h)
   self.req('POST','readings',self.reader,client=employee,headers=h)
   mine=self.req('GET','readings',client=employee).json()
   self.assertEqual(len(mine),1)
   self.req('DELETE',f'readings/{mine[0]["id"]}',expected=403,client=employee,headers=h)
  finally:employee.close()
 def test_unbilled_contract_can_delete_billed_cannot(self):
  self.req('DELETE',f'contracts/{self.contract}')
  self.assertFalse(self.req('GET','contracts').json())
  cid=self.req('POST','contracts',{'room_id':self.room,'tenant_id':self.tenant,'start_date':'2026-01-01','end_date':'2027-12-31','monthly_rent':2000000}).json()['id']
  self.req('POST','readings',self.reader)
  self.req('POST','invoices/generate',{'period':'2026-06'})
  self.req('DELETE',f'contracts/{cid}',expected=409)

if __name__=='__main__': unittest.main()
