"""Regression tests for granular authorization, annual meter display data, and advance rent."""
import calendar
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from fastapi.testclient import TestClient
from app import db
from app.main import app


def addmonths(period,n):
    y,m=map(int,period.split('-'))
    return f'{y+(m-1+n)//12:04d}-{(m-1+n)%12+1:02d}'

class Version3Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        db.DB_PATH=Path(self.temp.name)/'db.sqlite3'
        os.environ['BACKUP_DIRECTORY']=str(Path(self.temp.name)/'backups')
        db.init_db()
        self.client=TestClient(app)
        setup=self.client.post('/api/auth/setup',json={'username':'admin','full_name':'Owner','password':'secure-password-1234'})
        assert setup.status_code==200,setup.text
        self.csrf={'X-CSRF-Token':setup.json()['csrf']}
        self.current=date.today().strftime('%Y-%m')
        self.second=addmonths(self.current,1)
        self.third=addmonths(self.current,2)
        start=self.current+'-01'
        end=addmonths(self.current,6)+'-'+str(calendar.monthrange(*map(int,addmonths(self.current,6).split('-')))[1]).zfill(2)
        self.prop=self.api('POST','properties',{'name':'Khu Nam','service_fee':90000,'electric_rate':3500,'water_rate':20000}).json()['id']
        self.room=self.api('POST','rooms',{'property_id':self.prop,'code':'A1','rent':3000000}).json()['id']
        self.empty=self.api('POST','rooms',{'property_id':self.prop,'code':'A2','rent':3000000}).json()['id']
        tenant=self.api('POST','tenants',{'full_name':'Trần Thanh Hoa','phone':'0901000000','id_number':'001234567890'}).json()['id']
        self.contract=self.api('POST','contracts',{'room_id':self.room,'tenant_id':tenant,'start_date':start,'end_date':end,
                                  'monthly_rent':3000000,'deposit':3000000}).json()['id']
    def tearDown(self):self.client.close();self.temp.cleanup()
    def api(self,m,path,data=None,expected=200,client=None,csrf=None):
        client=client or self.client
        kw={'headers':csrf or self.csrf}
        if data is not None:kw['json']=data
        out=getattr(client,m.lower())('/api/'+path,**kw)
        self.assertEqual(out.status_code,expected, (path,out.text))
        return out
    def test_meter_tenant_and_no_empty_room(self):
        data={'period':self.current,'electric_old':10,'electric_new':20,'water_old':1,'water_new':2}
        self.api('POST','readings',{**data,'room_id':self.empty},400)
        self.api('POST','v2/readings/batch',{'period':self.current,'entries':[{**data,'room_id':self.empty}]},400)
        self.api('POST','readings',{**data,'room_id':self.room})
        readings=self.api('GET','readings').json()
        self.assertEqual(len(readings),1)
        self.assertEqual(readings[0]['tenant_name'],'Trần Thanh Hoa')
        self.api('POST','v2/imports/readings?dry_run=true',expected=422) # invalid missing file
    def test_rent_quarter_and_monthly_utilities(self):
        payment=self.api('POST','v2/prepayments',{'contract_id':self.contract,'start_period':self.current,
            'end_period':self.third,'paid_on':date.today().isoformat(),'method':'transfer'}).json()
        self.assertEqual(payment['total'],9000000)
        self.assertEqual(payment['months'],3)
        self.api('POST','v2/prepayments',{'contract_id':self.contract,'start_period':self.current,
            'end_period':self.current,'paid_on':date.today().isoformat()},400)
        self.api('PUT',f'v2/contracts/{self.contract}/proration',{'enabled':True},400)
        for i,month in enumerate([self.current,self.second,self.third]):
            self.api('POST','readings',{'room_id':self.room,'period':month,
                'electric_old':100+i*20,'electric_new':120+i*20,'water_old':10+i,'water_new':11+i})
            inv=self.api('POST','v2/invoices/draft',{'contract_id':self.contract,'period':month}).json()['id']
            saved=self.api('GET','invoices').json()
            item=next(x for x in saved if x['id']==inv)
            self.assertEqual(item['rent'],0)
            self.assertEqual(item['electricity'],70000)
            self.assertEqual(item['water'],20000)
            self.assertEqual(item['services'],90000)
            self.assertEqual(item['total'],180000)
            lines=self.api('GET',f'v2/invoices/{inv}/lines').json()
            self.assertEqual(sum(x['amount'] for x in lines),item['total'])
            self.assertEqual(len([x for x in lines if x['code']=='prepaid_rent']),1)
            self.api('POST',f'v2/invoices/{inv}/publish',{})
        report=self.api('GET','reports?period='+self.current).json()
        self.assertEqual(report['cash_in'],9000000)
        self.assertEqual(report['billed'],180000)
        self.api('POST',f'v2/prepayments/{self.api("GET","v2/prepayments").json()[0]["id"]}/refund',
                 {'refunded_on':date.today().isoformat(),'reason':'Không thể hoàn khi đã lên hóa đơn'},400)
    def test_refund_unused_month_and_cash(self):
        self.api('POST','v2/prepayments',{'contract_id':self.contract,'start_period':self.second,
            'end_period':self.third,'paid_on':date.today().isoformat()})
        coverage=self.api('GET','v2/prepayments').json()
        target=next(x for x in coverage if x['period']==self.third)
        self.api('POST',f'v2/prepayments/{target["id"]}/refund',
                 {'refunded_on':date.today().isoformat(),'reason':'Khách đổi lịch'})
        report=self.api('GET','reports?period='+self.current).json()
        self.assertEqual(report['cash_in'],3000000)
        # A refunded month can be paid again; previous transaction remains auditable.
        self.api('POST','v2/prepayments',{'contract_id':self.contract,'start_period':self.third,
            'end_period':self.third,'paid_on':date.today().isoformat()})
        self.assertEqual(len(self.api('GET','v2/prepayments').json()),3)
        self.api('POST','v2/handovers',{'contract_id':self.contract,'handover_type':'checkout',
            'handover_on':date.today().isoformat(),'ack_debt':True},400)
    def test_granular_perms_are_server_enforced(self):
        from app.permissions import ALL_KEYS,defaults
        uid=self.api('POST','users',{'username':'cashier','full_name':'Kế toán 1','password':'secure-password-5678','role':'staff'}).json()['id']
        catalog=self.api('GET','v2/access/catalog').json()
        self.assertGreaterEqual(sum(len(g['actions']) for g in catalog['groups']),60)
        perms=defaults('manager')
        perms.update({'rooms.create':False,'readings.record':False,'payments.record':True,'prepayments.record':False,'reports.view':False})
        self.api('PUT',f'v2/access/{uid}',{'job_role':'manager','property_ids':[self.prop],'permissions':perms})
        other=TestClient(app)
        login=other.post('/api/auth/login',json={'username':'cashier','password':'secure-password-5678'})
        self.assertEqual(login.status_code,200,login.text)
        csrf={'X-CSRF-Token':login.json()['csrf']}
        self.api('GET','rooms',client=other,csrf=csrf)
        self.api('GET','reports?period='+self.current,expected=403,client=other,csrf=csrf)
        self.api('POST','rooms',{'property_id':self.prop,'code':'HACK','rent':1},403,client=other,csrf=csrf)
        self.api('POST','readings',{'room_id':self.room,'period':self.current,'electric_old':1,'electric_new':2,'water_old':1,'water_new':2},403,client=other,csrf=csrf)
        self.api('POST','v2/prepayments',{'contract_id':self.contract,'start_period':self.current,'end_period':self.current,'paid_on':date.today().isoformat()},403,client=other,csrf=csrf)
        self.api('GET','v2/access',expected=403,client=other,csrf=csrf)
        self.api('PUT',f'v2/access/{uid}',{'job_role':'manager','property_ids':[],'permissions':{**perms,'access.edit':True}},400)
        other.close()
    def test_login_includes_custom_permissions(self):
        from app.permissions import defaults
        uid=self.api('POST','users',{'username':'viewer2','full_name':'Người Xem','password':'secure-password-5678','role':'staff'}).json()['id']
        rights=defaults('viewer')
        rights['readings.view']=False
        rights['dashboard.view']=False
        self.api('PUT',f'v2/access/{uid}',{'job_role':'viewer','property_ids':[self.prop],'permissions':rights})
        other=TestClient(app)
        response=other.post('/api/auth/login',json={'username':'viewer2','password':'secure-password-5678'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['user']['permissions']['readings.view'])
        self.assertTrue(response.json()['user']['permissions']['rooms.view'])
        self.api('GET','readings',expected=403,client=other,csrf={'X-CSRF-Token':response.json()['csrf']})
        self.api('GET','rooms',client=other,csrf={'X-CSRF-Token':response.json()['csrf']})
        other.close()

    def test_annual_meter_list_has_all_months(self):
        for month in (self.current,self.second):
            self.api('POST','readings',{'room_id':self.room,'period':month,
                'electric_old':200,'electric_new':225,'water_old':50,'water_new':55})
        readings=self.api('GET','readings').json()
        self.assertEqual({x['period'] for x in readings},{self.current,self.second})
        self.assertTrue(all(x['tenant_name']=='Trần Thanh Hoa' for x in readings))
        self.assertEqual(len({x['room_id'] for x in readings}),1)

    def test_migrate_from_v2_preserves_records(self):
        with db.connect() as con:
            con.execute('PRAGMA user_version=2')
            con.execute('INSERT INTO audit_logs(action,entity) VALUES(?,?)',('before','migration'))
        db.init_db()
        with db.connect() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],6)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM audit_logs WHERE action='before'").fetchone()[0],1)
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(len(list((Path(self.temp.name)/'backups'/'migrations').glob('*.sqlite3'))),1)

if __name__=='__main__':unittest.main()
