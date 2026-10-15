"""TrọFlow v1->v2 data retention + 12 upgraded business flows."""
import io
import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app import db
from app.main import app


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.data=Path(self.tmp.name)
        db.DB_PATH=self.data/'main.sqlite3'
        # Restore and migrations use app.db.DB_PATH and env for BACKUP_DIRECTORY.
        os.environ['BACKUP_DIRECTORY']=str(self.data/'backups')
        os.environ['UPLOAD_DIRECTORY']=str(self.data/'uploads')
        import app.advanced as adv
        adv.UPLOADS=self.data/'uploads'
        adv.BACKUPS=self.data/'backups'
        db.init_db()
        self.client=TestClient(app)
        r=self.client.post('/api/auth/setup',json={'username':'admin','full_name':'Quản trị','password':'password-very-secure'})
        self.assertEqual(r.status_code,200,r.text)
        self.csrf=r.json()['csrf'];self.auth={'x-csrf-token':self.csrf}
        self.month=date.today().strftime('%Y-%m')
        self.today=date.today().isoformat()
        self.first=date.today().replace(day=1).isoformat()
        self.last=(date.today()+timedelta(days=360)).isoformat()
    def tearDown(self):
        self.client.close();self.tmp.cleanup()
    def req(self,m,path,data=None,status=200,files=None):
        kwargs={'headers':self.auth}
        if files:kwargs['files']=files;kwargs['data']=data or {}
        elif data is not None:kwargs['json']=data
        r=getattr(self.client,m.lower())('/api/'+path,**kwargs)
        self.assertEqual(r.status_code,status,(path,r.text))
        return r
    def setup_contract(self,number='101',rent=3000000,service_fee=100000):
        pid=self.req('POST','properties',{'name':'Cơ sở '+number,'electric_rate':3500,'water_rate':20000,'service_fee':service_fee}) .json()['id']
        roomid=self.req('POST','rooms',{'property_id':pid,'code':number,'rent':rent,'deposit':rent}).json()['id']
        tid=self.req('POST','tenants',{'full_name':'Nguyễn Minh Anh','phone':'0900000000'}).json()['id']
        cid=self.req('POST','contracts',{'room_id':roomid,'tenant_id':tid,'start_date':self.first,'end_date':self.last,
                    'monthly_rent':rent,'deposit':rent,'occupants':2}).json()['id']
        return pid,roomid,tid,cid

    def test_upgraded_business_features(self):
        pid,rid,tid,cid=self.setup_contract()
        self.assertEqual(self.req('GET','v2/residents').json()[0]['is_primary'],1)
        rid2=self.req('POST','v2/residents',{'contract_id':cid,'full_name':'Người ở cùng','moved_in':self.first,'id_number':'0123456789'}).json()['id']
        self.req('POST',f'v2/residents/{rid2}/leave',{'moved_out':self.today})
        self.req('POST','v2/deposits',{'contract_id':cid,'kind':'receive','amount':3000000,'transacted_on':self.today})
        self.req('POST','v2/deposits',{'contract_id':cid,'kind':'refund','amount':3000001,'transacted_on':self.today},400)
        self.assertEqual(self.req('GET','v2/deposits/balances').json()[0]['held'],3000000)
        sid=self.req('POST','v2/services',{'property_id':pid,'name':'Gửi xe','charge_type':'quantity','unit_price':80000}).json()['id']
        self.req('POST','v2/contract-services',{'contract_id':cid,'service_id':sid,'quantity':2})
        self.req('PUT',f'v2/contracts/{cid}/proration',{'enabled':True})
        recorded=self.req('POST','v2/readings/batch',{'period':self.month,'entries':[{'room_id':rid,
                     'electric_old':100,'electric_new':120,'water_old':4,'water_new':6}]}).json()
        self.assertEqual(recorded['updated'],1)
        self.assertEqual(self.req('GET','v2/readings/alerts?period='+self.month).json(),[])
        preview=self.req('POST','v2/invoices/preview',{'contract_id':cid,'period':self.month,'discount':50000}).json()
        self.assertEqual(preview['electricity'],70000)
        self.assertEqual(preview['water'],40000)
        self.assertEqual(preview['services'],260000)
        inv_id=self.req('POST','v2/invoices/draft',{'contract_id':cid,'period':self.month,'discount':50000}).json()['id']
        self.assertEqual(self.req('GET','invoices').json()[0]['status'],'draft')
        self.req('POST','payments',{'invoice_id':inv_id,'amount':100000,'paid_at':self.today},400)
        self.req('PUT',f'v2/invoices/{inv_id}/draft',{'discount':100000,'surcharge':25000,'adjustment':0,'reason':'Miễn giảm'} )
        self.assertEqual(len(self.req('GET',f'v2/invoices/{inv_id}/revisions').json()),1)
        self.req('POST',f'v2/invoices/{inv_id}/publish',{})
        self.req('PUT',f'v2/invoices/{inv_id}/draft',{'discount':1,'reason':'Sai'},400)
        self.assertEqual(self.req('GET',f'v2/invoices/{inv_id}/pdf').headers['content-type'],'application/pdf')
        self.req('PUT',f'v2/properties/{pid}/bank',{'bank_code':'VCB','bank_account':'1234567890','bank_name':'CHU TRO'})
        qr=self.req('GET',f'v2/invoices/{inv_id}/vietqr').json()
        self.assertEqual(qr['transfer_note'],f'TROFLOW HD{inv_id} {self.month.replace("-","")}')
        self.assertIn('img.vietqr.io',qr['url'])
        self.req('POST','v2/handovers',{'contract_id':cid,'handover_type':'checkin','handover_on':self.today,'description':'Đầy đủ'})
        self.req('POST','v2/handovers',{'contract_id':cid,'handover_type':'checkout','handover_on':self.today,'damage_amount':200000,'refund_amount':2800000,'ack_debt':True})
        balances=self.req('GET','v2/deposits/balances').json()
        self.assertEqual(balances[0]['held'],0)
        self.assertEqual(self.req('GET','contracts').json()[0]['status'],'ended')
        hand=self.req('GET','v2/handovers').json()[0]
        self.assertTrue(self.req('GET',f'v2/handovers/{hand["id"]}/pdf').content.startswith(b'%PDF'))
        self.req('PUT',f'v2/schedules/{pid}',{'active':True,'day_of_month':5})
        self.assertEqual(self.req('GET','v2/schedules').json()[0]['active'],1)

    def test_bulk_import_preview_commit_and_upload(self):
        pid,rid,tid,cid=self.setup_contract()
        from openpyxl import Workbook
        out=io.BytesIO();w=Workbook();sheet=w.active
        sheet.append(['full_name','phone','email','id_number','hometown','notes'])
        sheet.append(['Tú Trọ','0123456789','','','',''])
        w.save(out);out.seek(0)
        files={'file':('tenants.xlsx',out.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        self.req('POST','v2/imports/tenants?dry_run=true',files=files)
        self.assertEqual(len(self.req('GET','tenants').json()),1)
        self.req('POST','v2/imports/tenants?dry_run=false',files=files)
        self.assertEqual(len(self.req('GET','tenants').json()),2)
        self.assertIn('full_name',self.req('GET','v2/imports/template/tenants').text)
        self.req('POST','readings',{'room_id':rid,'period':self.month,'electric_old':0,'electric_new':3,'water_old':0,'water_new':1})
        reading=self.req('GET','readings').json()[0]
        content=b'\x89PNG\r\n\x1a\n'+b'\0'*100
        self.req('POST','v2/files',data={'category':'electric','related_id':str(reading['id'])},files={'file':('meter.png',content,'image/png')})
        name=self.req('GET','readings').json()[0]['electric_photo']
        self.assertTrue(self.req('GET',f'v2/files/{name}').content.startswith(b'\x89PNG'))

    def test_access_scope_and_scheduler(self):
        p1,r1,t1,c1=self.setup_contract('101')
        p2,r2,t2,c2=self.setup_contract('102')
        self.req('POST','readings',{'room_id':r1,'period':self.month,'electric_old':0,'electric_new':5,'water_old':0,'water_new':1})
        self.req('PUT',f'v2/schedules/{p1}',{'active':True,'day_of_month':1})
        results=self.req('POST',f'v2/schedules/run/{p1}',{'period':self.month}).json()
        self.assertEqual(results['created'],1)
        self.assertEqual(self.req('GET','invoices').json()[0]['status'],'draft')
        uid=self.req('POST','users',{'username':'collector','full_name':'Nhân viên thu','role':'staff','password':'long-secure-password'}).json()['id']
        self.req('PUT',f'v2/access/{uid}',{'job_role':'collector','property_ids':[p1]})
        other=TestClient(app)
        response=other.post('/api/auth/login',json={'username':'collector','password':'long-secure-password'})
        self.assertEqual(response.status_code,200,response.text)
        headers={'x-csrf-token':response.json()['csrf']}
        self.assertEqual(len(other.get('/api/properties').json()),1)
        self.assertEqual(len(other.get('/api/rooms').json()),1)
        self.assertEqual(len(other.get('/api/contracts').json()),1)
        self.assertEqual(other.post('/api/rooms',headers=headers,json={'property_id':p2,'code':'HACK','rent':100}).status_code,403)
        self.assertEqual(other.post('/api/payments',headers=headers,json={'invoice_id':1,'amount':10,'paid_at':self.today}).status_code,400)
        self.assertEqual(other.post('/api/expenses',headers=headers,json={'property_id':p1,'amount':100,'spent_on':self.today,'category':'repair'}).status_code,403)
        other.close()

    def test_backup_verify_and_staged_restore(self):
        pid,_,_,_=self.setup_contract('330')
        created=self.req('POST','v2/backups/create',{}).json()['name']
        self.assertTrue((self.data/'backups'/created).exists())
        self.assertTrue(self.req('POST','v2/backups/verify',{'name':created}).json()['valid'])
        self.req('POST','v2/backups/restore',{'name':created,'confirm':'SAI'},400)
        self.req('POST','v2/backups/restore',{'name':created,'confirm':'KHOI PHUC'})
        marker=self.data/'.troflow-restore-request.json'
        self.assertTrue(marker.is_file())
        # Restore only on restart with no API connection to this database.
        from app.migrations import restore_pending
        restore_pending(db.DB_PATH)
        self.assertFalse(marker.exists())
        with db.connect() as con:
            self.assertEqual(con.execute('SELECT name FROM properties WHERE id=?',(pid,)).fetchone()[0],'Cơ sở 330')
        self.assertEqual(len(list((self.data/'backups').glob('troflow-pre-restore-*'))),1)

    def test_migration_non_destructive(self):
        # Produce v1 schema in an independent SQLite file with real legacy data.
        legacy=self.data/'legacy.sqlite3'
        with sqlite3.connect(legacy) as con:
            con.executescript(db.SCHEMA)
            con.execute("INSERT INTO properties(id,name) VALUES(1,'Cơ sở cũ')")
            con.execute("INSERT INTO rooms(id,property_id,code,rent,deposit) VALUES(1,1,'A101',2000000,2000000)")
            con.execute("INSERT INTO tenants(id,full_name,phone) VALUES(1,'Khách cũ','0901')")
            con.execute("INSERT INTO contracts(id,room_id,tenant_id,start_date,end_date,monthly_rent) VALUES(1,1,1,'2025-01-01','2027-01-01',2000000)")
            con.execute("INSERT INTO readings(room_id,period,electric_old,electric_new,water_old,water_new) VALUES(1,'2026-09',0,5,0,3)")
        db.DB_PATH=legacy
        db.init_db();db.init_db()
        with db.connect() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM contract_residents').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT name FROM properties WHERE id=1').fetchone()[0],'Cơ sở cũ')
            self.assertEqual(con.execute('SELECT prorate FROM contracts WHERE id=1').fetchone()[0],0)
        backdir=self.data/'backups'/'migrations'
        self.assertEqual(len(list(backdir.glob('troflow-v1-before-v2-*.sqlite3'))),1)

if __name__=='__main__':unittest.main()
