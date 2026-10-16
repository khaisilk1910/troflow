"""V10: rent is billed forward, utilities in arrears, corrections preserve receipts."""
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient


class BillingV10(unittest.TestCase):
    def setUp(self):
        from app import db
        self.tmp=tempfile.TemporaryDirectory()
        db.DB_PATH=Path(self.tmp.name)/'billing.sqlite3'
        db.init_db()
        from app.main import app
        self.client=TestClient(app)
        r=self.client.post('/api/auth/setup',json={'username':'admin','full_name':'Quản trị','password':'securepassword890'})
        self.assertEqual(r.status_code,200,r.text)
        self.h={'x-csrf-token':r.json()['csrf']}
        self.pid=self.call('POST','properties',{'name':'Nhà trọ A','electric_rate':3500,'water_rate':20000,'service_fee':100000})['id']
        self.rid=self.call('POST','rooms',{'code':'P01','property_id':self.pid,'rent':3000000})['id']
        self.tid=self.call('POST','tenants',{'full_name':'Trang','phone':'0980000123','id_number':'001234567890'})['id']
        self.cid=self.call('POST','contracts',{'room_id':self.rid,'tenant_id':self.tid,'start_date':'2025-01-01','end_date':'2027-12-31','monthly_rent':3000000,'due_day':5})['id']

    def tearDown(self):
        self.client.close();self.tmp.cleanup()

    def call(self,method,path,payload=None,status=200,headers=None,client=None):
        r=(client or self.client).request(method,'/api/'+path,json=payload,headers=(headers if headers is not None else self.h))
        self.assertEqual(r.status_code,status,(path,r.text))
        return r.json()

    def sample(self,period='2026-09',eo=100,en=200,wo=10,wn=12):
        return self.call('POST','readings',{'room_id':self.rid,'period':period,'electric_old':eo,'electric_new':en,'water_old':wo,'water_new':wn})

    def test_october_rent_september_electricity_and_supplier_report(self):
        self.sample()
        self.call('POST','invoices/generate',{'period':'2026-10'})
        inv=self.call('GET','invoices')[0]
        self.assertEqual(inv['period'],'2026-10')
        self.assertEqual(inv['utility_period'],'2026-09')
        self.assertEqual(inv['due_date'],'2026-10-05')
        self.assertEqual(inv['electricity'],350000)
        self.assertEqual(inv['water'],40000)
        self.assertEqual(inv['electric_old'],100)
        self.assertEqual(inv['electric_new'],200)
        self.assertEqual(inv['total'],3490000)
        lines=self.call('GET',f'v2/invoices/{inv["id"]}/lines')
        self.assertIn('10/2026',lines[0]['label'])
        self.assertIn('09/2026',next(x['label'] for x in lines if x['code']=='electric'))
        self.assertIn('09/2026',next(x['label'] for x in lines if x['code']=='water'))
        self.call('POST','readings',{'room_id':self.rid,'period':'2026-10','electric_old':200,'electric_new':300,'water_old':12,'water_new':13})
        self.call('PUT',f'readings/{self.sample("2026-08",20,100,5,10)["id"]}',
          {'room_id':self.rid,'period':'2026-09','electric_old':100,'electric_new':201,'water_old':10,'water_new':12},409)
        report=self.call('GET','utility-report?year=2026')
        item=next(x for x in report['items'] if x['period']=='2026-09')
        self.assertEqual(item['electric_billed'],350000)
        self.assertEqual(item['water_billed'],40000)
        self.assertFalse(any(x['period']=='2026-10' and x['electric_billed'] for x in report['items']))

    def test_december_to_january_and_missing_previous(self):
        self.sample('2026-12')
        item=self.call('POST','v2/invoices/preview',{'contract_id':self.cid,'period':'2027-01'})
        self.assertEqual(item['utility_period'],'2026-12')
        self.assertEqual(item['due_date'],'2027-01-05')
        self.call('POST','invoices/generate',{'period':'2027-01'})
        self.call('POST','invoices/generate',{'period':'2026-11'},400)

    def test_new_tenant_does_not_inherit_previous_tenant_consumption(self):
        from app import db
        with db.tx() as con:
            con.execute("UPDATE contracts SET start_date='2026-10-01' WHERE id=?",(self.cid,))
            con.execute('''INSERT INTO readings(room_id,period,electric_old,electric_new,water_old,water_new)
              VALUES(?,?,?,?,?,?)''',(self.rid,'2026-09',100,500,10,30))
        self.call('POST','invoices/generate',{'period':'2026-10'})
        inv=self.call('GET','invoices')[0]
        self.assertEqual(inv['rent'],3000000)
        self.assertEqual(inv['electricity'],0)
        self.assertEqual(inv['water'],0)
        self.assertEqual(inv['total'],3100000)

    def test_paid_invoice_void_reissue_and_overpayment_guard(self):
        self.sample()
        self.call('POST','invoices/generate',{'period':'2026-10'})
        old=self.call('GET','invoices')[0]
        self.call('POST','payments',{'invoice_id':old['id'],'amount':3200000,'paid_at':'2026-10-08','method':'cash'})
        self.call('POST',f'v10/invoices/{old["id"]}/void',{'reason':'Sửa kỳ công tơ'},409)
        self.call('POST',f'v10/invoices/{old["id"]}/void',{'reason':'Sửa kỳ công tơ','acknowledge_payments':True})
        self.assertEqual(self.call('GET','invoices')[0]['status'],'void')
        self.call('POST','payments',{'invoice_id':old['id'],'amount':1,'paid_at':'2026-10-08'},400)
        reading=self.call('GET','readings')[0]
        self.call('PUT',f'readings/{reading["id"]}',{'room_id':self.rid,'period':'2026-09','electric_old':100,'electric_new':201,'water_old':10,'water_new':12})
        self.call('POST',f'v10/invoices/{old["id"]}/reissue',{'reason':'Sửa chỉ số tháng 9'})
        fresh=self.call('GET','invoices')[0]
        self.assertEqual(fresh['id'],old['id'])
        self.assertEqual(fresh['paid'],3200000)
        self.assertEqual(fresh['status'],'published')
        self.assertEqual(fresh['electricity'],353500)
        hist=self.call('GET',f'v2/invoices/{old["id"]}/revisions')
        self.assertEqual(len(hist),2)
        self.assertEqual(len(self.call('GET','payments')),1)
        self.call('POST',f'v10/invoices/{old["id"]}/reissue',{'reason':'Giảm quá số đã thu','discount':500000},409)
        self.assertEqual(self.call('GET','invoices')[0]['total'],3493500)

    def test_supplier_bill_paid_october_is_september_consumption(self):
        self.sample('2026-09')
        self.call('POST','invoices/generate',{'period':'2026-10'})
        mid=self.call('POST','utility-meters',{
            'property_id':self.pid,'kind':'electric','meter_number':'PD00003540',
            'customer_code':'PD00003540','supplier':'EVN'})['id']
        self.call('POST','utility-bills',{
            'meter_id':mid,'period':'2026-09','reading_old':3860.67,'reading_new':4523.87,
            'billed_usage':663.2,'bill_amount':2113344,'paid_amount':2113344,
            'paid_on':'2026-10-02','note':'EVN kỳ tháng 9, thanh toán tháng 10'})
        report=self.call('GET','utility-report?year=2026')
        september=next(x for x in report['items'] if x['period']=='2026-09')
        self.assertEqual(september['supplier_charged'],2113344)
        self.assertEqual(september['supplier_paid'],2113344)
        self.assertEqual(september['electric_billed'],350000)
        self.assertFalse(any(x['period']=='2026-10' for x in report['items']))

    def test_zalo_reissues_have_distinct_events_and_cancelled_invoice_is_not_exportable(self):
        from app import db
        with db.tx() as con:
            con.execute('UPDATE zalo_config SET enabled=1,invoice_enabled=1 WHERE id=1')
            con.execute('''INSERT INTO zalo_destinations(name,thread_id,kind,property_id,tenant_id)
                VALUES(?,?,?,?,?)''',('Trang Zalo','1234567890','user',self.pid,self.tid))
        self.sample()
        self.call('POST','invoices/generate',{'period':'2026-10'})
        invoice=self.call('GET','invoices')[0]
        ident=invoice['id']
        self.call('POST',f'v10/invoices/{ident}/reissue',{'reason':'Tính lại kiểm tra 1'})
        self.call('POST',f'v10/invoices/{ident}/reissue',{'reason':'Tính lại kiểm tra 2'})
        with db.connect() as con:
            events=con.execute("SELECT event_key,status,message FROM zalo_outbox WHERE invoice_id=? AND event='invoice' ORDER BY id",(ident,)).fetchall()
        self.assertEqual(len(events),3)
        self.assertEqual(len({e['event_key'] for e in events}),3)
        self.assertEqual([e['status'] for e in events],['failed','failed','pending'])
        self.assertIn('Tiền phòng: 2026-10',events[-1]['message'])
        self.assertIn('Điện/nước: 2026-09',events[-1]['message'])
        self.call('POST',f'v10/invoices/{ident}/void',{'reason':'Kiểm tra chứng từ hủy'})
        self.call('GET',f'v6/invoices/{ident}/image.png',status=409)
        self.call('GET',f'v2/invoices/{ident}/pdf',status=409)
        with db.connect() as con:
            last=con.execute('SELECT status FROM zalo_outbox WHERE invoice_id=? ORDER BY id DESC LIMIT 1',(ident,)).fetchone()
        self.assertEqual(last['status'],'failed')

    def test_invoice_legacy_month_unchanged_and_role_denied(self):
        self.sample('2026-09')
        self.call('POST','invoices/generate',{'period':'2026-10'})
        inv=self.call('GET','invoices')[0]
        from app import db
        with db.tx() as con:con.execute('UPDATE invoices SET utility_period=NULL WHERE id=?',(inv['id'],))
        db.init_db()  # idempotent migration: historic consumption month remains as it was.
        inv=self.call('GET','invoices')[0]
        self.assertIsNone(inv['utility_period'])
        self.call('POST','users',{'username':'staff','full_name':'Nhân viên','role':'staff','password':'staffsecure987'})
        client=TestClient(self.client.app)
        try:
            r=client.post('/api/auth/login',json={'username':'staff','password':'staffsecure987'})
            self.assertEqual(r.status_code,200,r.text)
            sh={'x-csrf-token':r.json()['csrf']}
            self.call('POST',f'v10/invoices/{inv["id"]}/void',{'reason':'staff','acknowledge_payments':True},403,sh,client)
            self.call('POST',f'v10/invoices/{inv["id"]}/reissue',{'reason':'staff'},403,sh,client)
        finally:client.close()


if __name__=='__main__':unittest.main()
