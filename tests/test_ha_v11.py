"""Water provider cycle, EVN finalized previous cycle, and paid historic deletion."""
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app import main, db, home_assistant as ha
from app.utility import delete_bill


class HomeAssistantV11(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old_db=db.DB_PATH
        self.old_backup=os.environ.get('BACKUP_DIRECTORY')
        os.environ['BACKUP_DIRECTORY']=self.temp.name+'/backups'
        db.DB_PATH=Path(self.temp.name)/'db.sqlite3'
        db.init_db()
        self.client=TestClient(main.app)
        r=self.client.post('/api/auth/setup',json={'username':'admin','full_name':'Admin','password':'password-test-123456'})
        assert r.status_code==200,r.text
        self.head={'x-csrf-token':r.json()['csrf']}
        self.prop=self.api('POST','properties',{'name':'Ngõ 303'})['id']
        self.electric=self.api('POST','utility-meters',{'property_id':self.prop,'kind':'electric','meter_number':'elec1','customer_code':'EVN303','active':1})['id']
        self.water=self.api('POST','utility-meters',{'property_id':self.prop,'kind':'water','meter_number':'water1','customer_code':'W303','active':1})['id']

    def tearDown(self):
        self.client.close()
        db.DB_PATH=self.old_db
        if self.old_backup is None:os.environ.pop('BACKUP_DIRECTORY',None)
        else:os.environ['BACKUP_DIRECTORY']=self.old_backup
        self.temp.cleanup()

    def api(self,verb,path,data=None,expected=200):
        r=self.client.request(verb,'/api/'+path,json=data,headers=self.head)
        self.assertEqual(r.status_code,expected,r.text)
        return r.json()

    def configure(self,meter,water=False):
        values={'old_entity':'sensor.old','new_entity':'sensor.new',
                'usage_entity':'sensor.usage','amount_entity':'sensor.amount',
                'period_offset':0,'auto_sync':1,'enabled':1}
        if water:
            values.update(paid_on_entity='sensor.paid_date',paid_amount_entity='sensor.paid_amount')
        else:
            values.update(prev_usage_entity='sensor.prev_usage',prev_amount_entity='sensor.prev_amount',
                          prev_end_entity='sensor.prev_end')
        self.api('PUT','ha/mappings/'+str(meter),values)
        return values

    def sensors(self,values,paid_date=None):
        class Read:
            def __enter__(self):
                self.a=patch.object(ha,'_sensor',side_effect=lambda key:Decimal(str(values[key])))
                self.b=patch.object(ha,'_sensor_date',return_value=paid_date)
                self.a.__enter__();self.b.__enter__()
            def __exit__(self,*args):
                self.b.__exit__(*args);self.a.__exit__(*args)
        return Read()

    def test_water_previous_cycle_only_when_changed_in_window_and_later_payment(self):
        self.configure(self.water,True)
        source={'sensor.old':120,'sensor.new':140,'sensor.usage':20,'sensor.amount':200000,
                'sensor.paid_amount':0}
        with self.sensors(source):
            self.assertEqual(ha.sync_one(self.water,date(2026,10,5))['result'],'outside_window')
            self.assertEqual(ha.sync_one(self.water,date(2026,10,6))['result'],'unchanged')
        source.update({'sensor.old':140,'sensor.new':156,'sensor.usage':16,'sensor.amount':170000})
        with self.sensors(source):
            out=ha.sync_one(self.water,date(2026,10,7))
            self.assertEqual(out['result'],'created')
            self.assertEqual(out['period'],'2026-09')
            self.assertEqual(ha.sync_one(self.water,date(2026,10,8))['result'],'unchanged')
        source['sensor.paid_amount']=170000
        with self.sensors(source,paid_date='2026-10-15'):
            self.assertEqual(ha.sync_one(self.water,date(2026,10,15))['result'],'payment_updated')
        with db.connect() as con:
            r=db.one(con,'SELECT * FROM utility_meter_periods WHERE meter_id=?',(self.water,))
            self.assertEqual((r['period'],r['reading_old'],r['reading_new'],r['billed_usage'],r['paid_amount'],r['paid_on']),
                             ('2026-09',140,156,16,170000,'2026-10-15'))
        # Sensor changes after cutoff may NOT create or alter a newer cycle.
        source.update({'sensor.old':156,'sensor.new':170,'sensor.usage':14,'sensor.amount':140000})
        with self.sensors(source,paid_date='2026-10-15'):
            self.assertEqual(ha.sync_one(self.water,date(2026,10,20))['result'],'outside_window')
        with db.connect() as con:
            self.assertEqual(db.one(con,'SELECT reading_new FROM utility_meter_periods WHERE meter_id=?',(self.water,))['reading_new'],156)

    def test_electric_previous_month_from_end_minus_usage_and_protect_manual(self):
        self.configure(self.electric)
        src={'sensor.old':4523.87,'sensor.new':4600,'sensor.usage':76.13,'sensor.amount':220000,
             'sensor.prev_usage':663.20,'sensor.prev_amount':2113344,'sensor.prev_end':4523.87}
        with self.sensors(src):
            base=ha.sync_one(self.electric,date(2026,10,1))
            self.assertEqual(base['previous_result'],'waiting_change')
        src.update({'sensor.old':4832.42,'sensor.new':4900,'sensor.usage':67.58,'sensor.amount':200000,
                    'sensor.prev_usage':308.55,'sensor.prev_amount':829594,'sensor.prev_end':4832.42})
        with self.sensors(src):
            result=ha.sync_one(self.electric,date(2026,10,2))
        self.assertEqual(result['previous_result'],'created')
        self.assertAlmostEqual(result['previous']['reading_old'],4523.87)
        with db.connect() as con:
            previous=db.one(con,'SELECT * FROM utility_meter_periods WHERE meter_id=? AND period=?',(self.electric,'2026-09'))
            current=db.one(con,'SELECT * FROM utility_meter_periods WHERE meter_id=? AND period=?',(self.electric,'2026-10'))
        self.assertEqual((previous['billed_usage'],previous['bill_amount'],previous['reading_new']), (308.55,829594,4832.42))
        self.assertEqual(current['origin'],'home_assistant')
        self.api('PUT','utility-bills/'+str(previous['id']),{
            'meter_id':self.electric,'period':'2026-09','reading_old':4523.87,'reading_new':4832.42,
            'billed_usage':308.55,'bill_amount':829594,'paid_amount':829594,'paid_on':'2026-10-03'})
        src.update({'sensor.old':4840,'sensor.prev_end':4840,'sensor.prev_usage':310,'sensor.prev_amount':845000})
        with self.sensors(src):
            self.assertEqual(ha.sync_one(self.electric,date(2026,10,3))['previous_result'],'skipped_manual')
        with db.connect() as con:
            self.assertEqual(db.one(con,'SELECT bill_amount FROM utility_meter_periods WHERE id=?',(previous['id'],))['bill_amount'],829594)
        self.api('DELETE','utility-bills/'+str(previous['id']))
        src.update({'sensor.old':4850,'sensor.prev_end':4850,'sensor.prev_usage':315,'sensor.prev_amount':850000})
        with self.sensors(src):
            self.assertEqual(ha.sync_one(self.electric,date(2026,10,4))['previous_result'],'skipped_deleted')

    def test_water_year_boundary_and_paid_deletion_by_admin(self):
        self.configure(self.water,True)
        s={'sensor.old':100,'sensor.new':110,'sensor.usage':10,'sensor.amount':100000,'sensor.paid_amount':0}
        with self.sensors(s):
            self.assertEqual(ha.sync_one(self.water,date(2027,1,6))['result'],'waiting_change')
        s.update({'sensor.old':110,'sensor.new':130,'sensor.usage':20,'sensor.amount':200000,'sensor.paid_amount':200000})
        with self.sensors(s,paid_date='2027-01-07'):
            self.assertEqual(ha.sync_one(self.water,date(2027,1,7))['period'],'2026-12')
        with db.connect() as con:
            old=db.one(con,'SELECT * FROM utility_meter_periods WHERE meter_id=?',(self.water,))
        self.assertEqual(old['paid_amount'],200000)
        with self.assertRaises(HTTPException) as forbidden:
            delete_bill(old['id'],user={'role':'staff','grant_ids':[],'id':-1})
        self.assertEqual(forbidden.exception.status_code,403)
        self.api('DELETE','utility-bills/'+str(old['id']))
        s.update({'sensor.old':130,'sensor.new':150,'sensor.usage':20,'sensor.amount':205000,'sensor.paid_amount':0})
        with self.sensors(s):
            self.assertEqual(ha.sync_one(self.water,date(2027,1,8))['result'],'skipped_deleted')
        with db.connect() as con:
            self.assertIsNone(db.one(con,'SELECT id FROM utility_meter_periods WHERE id=?',(old['id'],)))
            log=db.one(con,"SELECT details FROM audit_logs WHERE action='delete' AND entity='utility_bill' ORDER BY id DESC LIMIT 1")
        self.assertIn('paid=200000',log['details'])

    def test_invalid_water_payment_does_not_modify_db(self):
        self.configure(self.water,True)
        s={'sensor.old':10,'sensor.new':20,'sensor.usage':10,'sensor.amount':100000,'sensor.paid_amount':50000}
        with self.sensors(s):
            self.assertEqual(ha.sync_one(self.water,date(2026,10,6))['result'],'waiting_change')
        s['sensor.new']=22
        with self.sensors(s):
            with self.assertRaisesRegex(RuntimeError,'không khớp'):
                ha.sync_one(self.water,date(2026,10,7))
        with db.connect() as con:
            self.assertEqual(db.one(con,'SELECT COUNT(*) n FROM utility_meter_periods')['n'],0)

if __name__=='__main__':unittest.main()
