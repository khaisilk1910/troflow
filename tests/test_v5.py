"""V5 regression: mandatory CCCD, private image pairs, multiple utility meters,
monthly supplier invoices, accrual vs estimated cash, and access scope."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import db,advanced
from app.main import app

PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082')

class V5Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old_db=db.DB_PATH;self.old_uploads=advanced.UPLOADS
  db.DB_PATH=Path(self.tmp.name)/'data'/'troflow.db';advanced.UPLOADS=Path(self.tmp.name)/'uploads';self.old_backup=os.environ.get('BACKUP_DIRECTORY');os.environ['BACKUP_DIRECTORY']=str(Path(self.tmp.name)/'backups')
  db.init_db();self.client=TestClient(app)
  response=self.client.post('/api/auth/setup',json={'username':'root','full_name':'Chủ cơ sở','password':'secure-password-123'})
  self.assertEqual(response.status_code,200,response.text);self.head={'x-csrf-token':response.json()['csrf']}
  self.prop=self.call('POST','properties',{'name':'Dãy A','electric_rate':3500,'water_rate':20000,'service_fee':0})['id']
 def tearDown(self):
  self.client.close();db.DB_PATH=self.old_db;advanced.UPLOADS=self.old_uploads
  if self.old_backup is None:os.environ.pop('BACKUP_DIRECTORY',None)
  else:os.environ['BACKUP_DIRECTORY']=self.old_backup
  self.tmp.cleanup()
 def call(self,method,path,payload=None,status=200,client=None,headers=None):
  res=(client or self.client).request(method,'/api/'+path,json=payload,headers=headers or self.head)
  self.assertEqual(res.status_code,status,(method,path,res.text))
  return res.json()
 def new_meter(self,kind='electric',number='E01',pid=None):
  return self.call('POST','utility-meters',{'property_id':pid or self.prop,'kind':kind,'meter_number':number,'customer_code':'KH-12345','supplier':'EVN' if kind=='electric' else 'Cấp nước','active':1})['id']
 def new_bill(self,meter,period='2026-06',bill_amount=120000,paid_amount=0,paid_on=None,old=10,new=35):
  return dict(meter_id=meter,period=period,reading_old=old,reading_new=new,billed_usage=new-old,bill_amount=bill_amount,paid_amount=paid_amount,paid_on=paid_on)
 def test_migration_v4_with_old_tenant_and_cccd_required_for_new(self):
  # Old records may lack CCCD; V5 cannot remove or rewrite them.
  with db.connect() as con:
   con.execute("INSERT INTO tenants(full_name,phone,id_number) VALUES ('Hồ sơ cũ','0123','')")
   con.execute('PRAGMA user_version=4')
  db.init_db()
  with db.connect() as con:
   self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],8)
   self.assertEqual(con.execute("SELECT id_number FROM tenants WHERE full_name='Hồ sơ cũ'").fetchone()[0],'')
   self.assertIn('id_back_path',{x[1] for x in con.execute('PRAGMA table_info(tenants)')})
   self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0],'ok')
  self.call('POST','tenants',{'full_name':'Mai','phone':'0998'},400)
  self.call('POST','tenants',{'full_name':'Mai','phone':'0998','id_number':'a1'},400)
  new=self.call('POST','tenants',{'full_name':'Mai','phone':'0998','id_number':'001234567890'})['id']
  self.assertEqual(next(t for t in self.call('GET','tenants') if t['id']==new)['id_number'],'001234567890')
 def test_cccd_front_back_and_private_view(self):
  t=self.call('POST','tenants',{'full_name':'Minh','phone':'0900000000','id_number':'001234567890'})['id']
  for cat,key in [('tenant','photo_path'),('tenant_id_front','id_front_path'),('tenant_id_back','id_back_path')]:
   r=self.client.post('/api/v2/files',data={'category':cat,'related_id':str(t)},files={'file':('x.png',io.BytesIO(PNG),'image/png')},headers=self.head)
   self.assertEqual(r.status_code,200,r.text)
   file=r.json()['name'];self.assertEqual(self.client.get('/api/v2/files/'+file).status_code,200)
   self.assertEqual(TestClient(app).get('/api/v2/files/'+file).status_code,401)
   self.assertEqual(self.call('GET','tenants')[0][key],file)
  # Replacing front must not overwrite back.
  name=self.call('GET','tenants')[0]['id_back_path']
  r=self.client.post('/api/v2/files',data={'category':'tenant_id_front','related_id':str(t)},files={'file':('x.png',PNG,'image/png')},headers=self.head)
  self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(self.call('GET','tenants')[0]['id_back_path'],name)
 def test_multi_meters_duplicates_update_delete_and_supplier_payments(self):
  first=self.new_meter();self.new_meter('electric','E02');self.new_meter('water','W01')
  self.call('POST','utility-meters',{'property_id':self.prop,'kind':'electric','meter_number':'E01','customer_code':'B'},409)
  self.assertEqual(len(self.call('GET','utility-meters')),3)
  b=self.call('POST','utility-bills',self.new_bill(first,paid_amount=100000,paid_on='2026-06-17'))['id']
  self.call('POST','utility-bills',self.new_bill(first),409)
  self.call('DELETE',f'utility-meters/{first}',status=409)
  self.call('DELETE',f'utility-bills/{b}',status=409)
  self.call('PUT',f'utility-bills/{b}',self.new_bill(first,paid_amount=0),200)
  self.call('PUT',f'utility-bills/{b}',self.new_bill(first,period='2026-07',paid_amount=0))
  self.assertEqual(self.call('GET','utility-bills?year=2026')[0]['period'],'2026-07')
  self.call('DELETE',f'utility-bills/{b}')
  self.call('DELETE',f'utility-meters/{first}')
  self.assertEqual(len(self.call('GET','utility-meters')),2)
 def test_report_tenant_accrual_and_estimated_collections(self):
  rid=self.call('POST','rooms',{'property_id':self.prop,'code':'P01','rent':1000000})['id']
  tid=self.call('POST','tenants',{'full_name':'Người A','phone':'0900000001','id_number':'001234567890'})['id']
  self.call('POST','contracts',{'room_id':rid,'tenant_id':tid,'start_date':'2026-01-01','end_date':'2027-12-01','monthly_rent':1000000})
  self.call('POST','readings',{'room_id':rid,'period':'2026-06','electric_old':100,'electric_new':200,'water_old':10,'water_new':12})
  self.call('POST','invoices/generate',{'period':'2026-06'})
  inv=self.call('GET','invoices')[0];self.assertEqual(inv['electricity'],350000);self.assertEqual(inv['water'],40000)
  self.call('POST','payments',{'invoice_id':inv['id'],'amount':695000,'paid_at':'2026-06-29','method':'transfer'})
  e=self.new_meter();w=self.new_meter('water','W01')
  self.call('POST','utility-bills',self.new_bill(e,bill_amount=200000,paid_amount=150000,paid_on='2026-07-01'))
  self.call('POST','utility-bills',self.new_bill(w,bill_amount=30000,paid_amount=30000,paid_on='2026-07-01'))
  report=self.call('GET','utility-report?year=2026')
  self.assertEqual(len(report['items']),1)
  row=report['items'][0]
  self.assertEqual(row['customer_billed'],390000)
  self.assertEqual(row['customer_collected_est'],195000)
  self.assertEqual(row['supplier_charged'],230000)
  self.assertEqual(row['supplier_paid'],180000)
  self.assertEqual(row['accrual_margin'],160000)
  self.assertEqual(row['cash_difference_est'],15000)
  self.assertFalse(row['missing_electric_bill']);self.assertFalse(row['missing_water_bill'])
 def test_scoped_permissions_and_user_menu(self):
  other=self.call('POST','properties',{'name':'Dãy B'})['id']
  e=self.new_meter(pid=other)
  uid=self.call('POST','users',{'username':'employee','full_name':'Nhân viên','password':'employee-password-123','role':'staff'})['id']
  from app.permissions import defaults
  p=defaults('manager');p.update({'utilitymeters.view':True,'utilitymeters.record':False,'utilitymeters.create':True,'utilitymeters.report':True})
  self.call('PUT',f'v2/access/{uid}',{'job_role':'manager','property_ids':[self.prop],'permissions':p})
  c=TestClient(app)
  try:
   r=c.post('/api/auth/login',json={'username':'employee','password':'employee-password-123'})
   self.assertEqual(r.status_code,200,r.text)
   head={'x-csrf-token':r.json()['csrf']}
   self.assertTrue(r.json()['user']['permissions']['utilitymeters.view'])
   self.assertFalse(r.json()['user']['permissions']['utilitymeters.record'])
   self.assertEqual(len(self.call('GET','utility-meters',client=c,headers=head)),0)
   self.call('POST','utility-bills',self.new_bill(e),403,client=c,headers=head)
   self.call('POST','utility-meters',{'property_id':other,'kind':'water','meter_number':'W01','customer_code':'B'},403,client=c,headers=head)
   self.call('GET','utility-report?year=2026&property_id='+str(other),status=403,client=c,headers=head)
  finally:c.close()

if __name__=='__main__':unittest.main()
