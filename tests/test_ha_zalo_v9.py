"""V9: HA imports, encrypted credentials, scoped Zalo events, and migration safety."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date, timedelta
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from PIL import Image
from app import main, db, home_assistant as ha, notify, tenant_portal

class UpgradeV9(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_db=db.DB_PATH
        self.old_key=os.environ.get('TROFLOW_SECRET_KEY_FILE')
        self.old_backup=os.environ.get('BACKUP_DIRECTORY')
        os.environ['TROFLOW_SECRET_KEY_FILE']=self.tmp.name+'/secret.key'
        Path(os.environ['TROFLOW_SECRET_KEY_FILE']).write_bytes(Fernet.generate_key())
        os.environ['BACKUP_DIRECTORY']=self.tmp.name+'/backups'
        db.DB_PATH=Path(self.tmp.name)/'troflow.db'
        db.init_db()
        self.client=TestClient(main.app)
        setup=self.client.post('/api/auth/setup',json={'username':'admin','full_name':'Admin','password':'password-test-123456'})
        assert setup.status_code==200,setup.text
        self.head={'x-csrf-token':setup.json()['csrf']}
        self.prop=self.api('POST','properties',{'name':'Ngõ 303'})['id']
        self.meter=self.api('POST','utility-meters',{'property_id':self.prop,'kind':'electric','meter_number':'PD05000030540','customer_code':'PD05000030540','supplier':'EVN','active':1})['id']

    def tearDown(self):
        self.client.close()
        db.DB_PATH=self.old_db
        for key,value in [('TROFLOW_SECRET_KEY_FILE',self.old_key),('BACKUP_DIRECTORY',self.old_backup)]:
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
        self.tmp.cleanup()

    def api(self,method,url,data=None,expected=200):
        response=self.client.request(method,'/api/'+url,headers=self.head,json=data)
        self.assertEqual(response.status_code,expected,response.text)
        return response.json()

    def mapping(self,auto=0):
        return {'old_entity':'sensor.chi_so_cuoi_ky_truoc',
                'new_entity':'sensor.chi_so_tam_chot',
                'usage_entity':'sensor.tieu_thu_ky_nay',
                'amount_entity':'sensor.tien_dien_ky_nay',
                'period_offset':0,'auto_sync':auto,'enabled':1}

    def test_encrypted_secret_configuration_and_private_url(self):
        saved=self.api('PUT','ha/config',{'url':'http://192.168.31.100:8123','token':'example-secret-123'})
        self.assertTrue(saved['configured'])
        self.assertNotIn('example-secret-123',str(self.api('GET','ha/config')))
        self.assertNotIn(b'example-secret-123',Path(self.tmp.name+'/home-assistant-credentials.bin').read_bytes())
        self.assertEqual((Path(self.tmp.name+'/home-assistant-credentials.bin').stat().st_mode & 0o777),0o600)
        self.api('PUT','ha/config',{'url':'http://public.example:8123','token':'secret'},expected=400)
        self.assertEqual(ha._config()['token'],'example-secret-123')

    def test_snapshot_and_manual_data_never_overwritten(self):
        self.api('PUT','ha/mappings/'+str(self.meter),self.mapping())
        measurements=iter(['4523.87','4832.42','308.55','829594'])
        with patch.object(ha,'_sensor',side_effect=lambda entity: __import__('decimal').Decimal(next(measurements))):
            result=self.api('POST','ha/sync/'+str(self.meter),{})
        self.assertEqual(result['result'],'created')
        self.assertEqual(result['bill_amount'],829594)
        self.assertEqual(result['billed_usage'],308.55)
        with db.connect() as con:
            row=db.one(con,'SELECT * FROM utility_meter_periods WHERE meter_id=?',(self.meter,))
            self.assertEqual(row['origin'],'home_assistant')
            self.assertEqual(row['paid_amount'],0)
        self.api('PUT','utility-bills/'+str(row['id']),{
            'meter_id':self.meter,'period':result['period'],'reading_old':4523.87,
            'reading_new':4832.42,'billed_usage':308.55,'bill_amount':829594,
            'paid_amount':0,'note':'Đã đối chiếu hóa đơn thật'})
        with patch.object(ha,'_sensor',return_value=__import__('decimal').Decimal('999999')):
            self.assertEqual(self.api('POST','ha/sync/'+str(self.meter),{})['result'],'skipped_manual')
        with db.connect() as con:
            row=db.one(con,'SELECT bill_amount,origin FROM utility_meter_periods WHERE meter_id=?',(self.meter,))
            self.assertEqual(row['bill_amount'],829594)
            self.assertEqual(row['origin'],'manual')

    def test_preview_sensor_unavailable_no_bill(self):
        self.api('PUT','ha/mappings/'+str(self.meter),self.mapping())
        with patch.object(ha,'_sensor',side_effect=RuntimeError('sensor unavailable')):
            result=self.api('POST','ha/preview/'+str(self.meter),{})
            self.assertFalse(result['ok'])
            self.api('POST','ha/sync/'+str(self.meter),{},expected=400)
        with db.connect() as con:
            self.assertEqual(db.one(con,'SELECT COUNT(*) n FROM utility_meter_periods')['n'],0)

    def test_sensors_validate_and_migration_idempotent(self):
        self.api('PUT','ha/mappings/'+str(self.meter),{**self.mapping(),'old_entity':'http://malicious/'},expected=400)
        db.init_db()
        with db.connect() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],10)
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            for table in ('ha_meter_mappings','utility_meter_periods','zalo_outbox'):
                self.assertTrue(db.one(con,"SELECT name FROM sqlite_master WHERE name=?",(table,)))

    def test_owner_notification_and_tenant_repair_scoping(self):
        room=self.api('POST','rooms',{'property_id':self.prop,'code':'P01','rent':3000000})['id']
        tenant=self.api('POST','tenants',{'full_name':'Trang','phone':'0982986102','id_number':'001234567890'})['id']
        with db.tx() as con:
            con.execute('UPDATE zalo_config SET enabled=1,ticket_enabled=1,reading_enabled=1')
            owner=con.execute("""INSERT INTO zalo_destinations
                (name,thread_id,kind,property_id,enabled,on_invoice,on_payment,on_ticket,on_meter_submission)
                VALUES('Chủ','123456789012','user',?,1,0,0,1,1)""",(self.prop,)).lastrowid
            renter=con.execute("""INSERT INTO zalo_destinations
                (name,thread_id,kind,property_id,tenant_id,enabled,on_invoice,on_payment,on_ticket_tenant)
                VALUES('Trang','123456789013','user',?,?,1,0,0,1)""",(self.prop,tenant)).lastrowid
            tid=con.execute("""INSERT INTO tickets
                (room_id,title,category,priority,status,description,reported_at,reported_by_tenant_id)
                VALUES(?,'Đèn hỏng','electric','medium','new','Đèn nhấp nháy',?,?)""",(room,date.today().isoformat(),tenant)).lastrowid
            notify.enqueue_ticket_event(con,tid)
            notify.enqueue_ticket_tenant(con,tid)
            submission=con.execute("""INSERT INTO tenant_meter_submissions
                (tenant_id,property_id,contract_id,room_id,period,electric_old,electric_new,water_old,water_new,electric_photo,water_photo)
                VALUES(?,?,?,?,?,10,20,1,2,'a.jpg','b.jpg')""",(tenant,self.prop,
                     con.execute("""INSERT INTO contracts(room_id,tenant_id,start_date,end_date,monthly_rent)
                                  VALUES(?,?,'2025-01-01','2028-12-31',3000000)""",(room,tenant)).lastrowid,room,
                    date.today().strftime('%Y-%m'))).lastrowid
            notify.enqueue_meter_submission(con,submission)
            out=db.rows(con,'SELECT destination_id,event FROM zalo_outbox ORDER BY id')
            self.assertEqual([(r['destination_id'],r['event']) for r in out],
                             [(owner,'ticket'),(renter,'ticket_tenant'),(owner,'meter_submission')])
            con.execute("UPDATE tickets SET status='in_progress' WHERE id=?",(tid,))
            self.assertEqual(notify.enqueue_ticket_tenant(con,tid,'new'),1)
            self.assertEqual(notify.enqueue_ticket_tenant(con,tid,'new'),1)
        with db.connect() as con:
            events=db.rows(con,"SELECT event,message FROM zalo_outbox WHERE destination_id=?",(renter,))
            self.assertEqual(len(events),3)
            self.assertTrue(all(e['event']=='ticket_tenant' for e in events))
            self.assertTrue(all('Trang' not in e['message'] for e in events))

if __name__=='__main__':unittest.main()
