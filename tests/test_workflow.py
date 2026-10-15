"""End-to-end API smoke tests without running Docker."""
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        from app import db
        db.DB_PATH=Path(self.tmp.name)/'test.sqlite3'
        db.init_db()
        from app.main import app
        self.client=TestClient(app)
        self.today=date.today()
        self.period=self.today.strftime('%Y-%m')
        self.user=self.client.post('/api/auth/setup',json={'username':'admin','full_name':'Chủ Nhà','password':'supersecurepass123'})
        assert self.user.status_code==200,self.user.text
        self.csrf=self.user.json()['csrf']
        self.headers={'x-csrf-token':self.csrf}

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def get(self,path):
        r=self.client.get('/api/'+path)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def post(self,path,data,expected=200):
        r=self.client.post('/api/'+path,json=data,headers=self.headers)
        self.assertEqual(r.status_code,expected,r.text)
        return r.json()

    def put(self,path,data,expected=200):
        r=self.client.put('/api/'+path,json=data,headers=self.headers)
        self.assertEqual(r.status_code,expected,r.text)
        return r.json()

    def test_real_management_workflow(self):
        p=self.post('properties',{'name':'Nhà trọ An Phú','address':'Bình Thạnh','electric_rate':3500,'water_rate':20000,'service_fee':100000})['id']
        r=self.post('rooms',{'property_id':p,'code':'A101','rent':3000000,'deposit':3000000,'area':23})['id']
        t=self.post('tenants',{'full_name':'Nguyễn Minh Anh','phone':'0900000000','id_number':'012345678901'})['id']
        self.assertEqual(len(self.get('properties')),1)
        today=self.today.isoformat()
        next_year=self.today.replace(year=self.today.year+1).isoformat()
        contract_data={'room_id':r,'tenant_id':t,'start_date':today,'end_date':next_year,'monthly_rent':3000000,'deposit':3000000,'due_day':5,'occupants':2}
        c=self.post('contracts',contract_data)['id']
        self.post('contracts',contract_data,400)
        self.assertEqual(self.get('rooms')[0]['status'],'occupied')
        self.post('readings',{'room_id':r,'period':self.period,'electric_old':100,'electric_new':125,'water_old':8,'water_new':12})
        created=self.post('invoices/generate',{'period':self.period})
        self.assertEqual(created['created'],1)
        i=self.get('invoices')[0]
        self.assertEqual(i['electricity'],25*3500)
        self.assertEqual(i['water'],4*20000)
        self.assertEqual(i['total'],3267500)
        self.assertEqual(i['balance'],3267500)
        self.assertEqual(self.post('invoices/generate',{'period':self.period})['created'],0)
        self.post('readings',{'room_id':r,'period':self.period,'electric_old':100,'electric_new':130,'water_old':8,'water_new':12},409)
        self.post('payments',{'invoice_id':i['id'],'amount':1000000,'paid_at':today,'method':'transfer'})
        self.assertEqual(self.get('invoices')[0]['balance'],2267500)
        self.post('payments',{'invoice_id':i['id'],'amount':2267501,'paid_at':today,'method':'cash'},400)
        self.post('payments',{'invoice_id':i['id'],'amount':2267500,'paid_at':today,'method':'cash'})
        self.assertEqual(self.get('invoices')[0]['balance'],0)
        self.post('expenses',{'property_id':p,'amount':500000,'category':'repair','spent_on':today,'description':'Sửa ống nước'})
        self.post('tickets',{'room_id':r,'title':'Hỏng máy lạnh','category':'other','priority':'high','reported_at':today,'status':'new'})
        dash=self.get('dashboard')
        self.assertEqual(dash['rooms_total'],1)
        self.assertEqual(dash['occupied'],1)
        self.assertEqual(dash['cash_in'],3267500)
        self.assertEqual(dash['cash_out'],500000)
        self.assertEqual(dash['open_tickets'],1)
        report=self.get('reports?period='+self.period)
        self.assertEqual(report['net_cashflow'],2767500)
        self.assertEqual(report['remaining'],0)
        backup=self.client.get('/api/backup');self.assertEqual(backup.status_code,200)
        self.assertTrue(backup.content.startswith(b'SQLite format 3'))
        csv=self.client.get('/api/export/tenants');self.assertEqual(csv.status_code,200)
        self.assertIn('Nguy',csv.text)
        self.post(f'contracts/{c}/end',{})
        self.assertEqual(self.get('rooms')[0]['status'],'ready')
        self.assertGreater(len(self.get('audit')),0)

    def test_roles_and_security(self):
        self.post('users',{'full_name':'Quản lý','username':'staff','password':'strongpassword123','role':'staff'})
        other=TestClient(self.client.app)
        r=other.post('/api/auth/login',json={'username':'staff','password':'strongpassword123'})
        self.assertEqual(r.status_code,200,r.text)
        token=r.json()['csrf']
        forbidden=other.post('/api/properties',json={'name':'Forbidden'},headers={'x-csrf-token':token})
        self.assertEqual(forbidden.status_code,403,forbidden.text)
        self.assertEqual(other.get('/api/backup').status_code,403)
        self.assertEqual(other.get('/api/users').status_code,403)
        denied=other.post('/api/tenants',json={'full_name':'A','phone':'123'},headers={})
        self.assertEqual(denied.status_code,403)
        okay=other.post('/api/tenants',json={'full_name':'A','phone':'123'},headers={'x-csrf-token':token})
        self.assertEqual(okay.status_code,200,okay.text)
        other.close()

if __name__=='__main__': unittest.main()
