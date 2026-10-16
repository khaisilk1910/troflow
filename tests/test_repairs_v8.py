"""V8 maintenance privacy, album, migrations, and scoped staff tests."""
import io
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
from app import db, main, tenant_portal, notify

class RepairV8(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old_db=db.DB_PATH
        self.old_uploads=tenant_portal.UPLOADS
        self.oldbackup=os.getenv('BACKUP_DIRECTORY')
        os.environ['BACKUP_DIRECTORY']=self.temp.name+'/backups'
        db.DB_PATH=Path(self.temp.name)/'data'/'troflow.db'
        tenant_portal.UPLOADS=Path(self.temp.name)/'uploads'
        db.init_db()
        self.admin=TestClient(main.app)
        setup=self.admin.post('/api/auth/setup',json={'username':'root','full_name':'Owner','password':'strong-password-123'}).json()
        self.ahead={'x-csrf-token':setup['csrf']}
        self.prop=self.admin_call('POST','properties',{'name':'Ngõ 303'})['id']
        self.room=self.admin_call('POST','rooms',{'property_id':self.prop,'code':'P01','rent':3000000})['id']
        self.tenant=self.admin_call('POST','tenants',{'full_name':'Nguyễn Thị Trang','phone':'0982986102','id_number':'001234567890','portal_enabled':True,'portal_property_id':self.prop})
        self.contract=self.admin_call('POST','contracts',{'room_id':self.room,'tenant_id':self.tenant['id'],'start_date':'2025-01-01','end_date':'2028-12-31','monthly_rent':3000000})['id']
        self.prop2=self.admin_call('POST','properties',{'name':'Ngõ 404'})['id']
        self.room2=self.admin_call('POST','rooms',{'property_id':self.prop2,'code':'P09','rent':3200000})['id']
        self.tenant2=self.admin_call('POST','tenants',{'full_name':'Hà','phone':'0982986103','id_number':'001234567891','portal_enabled':True,'portal_property_id':self.prop2})
        self.contract2=self.admin_call('POST','contracts',{'room_id':self.room2,'tenant_id':self.tenant2['id'],'start_date':'2025-01-01','end_date':'2028-12-31','monthly_rent':3200000})['id']
        self.tclient=TestClient(main.app)
        self.t2=TestClient(main.app)
        self.login(self.tclient,self.tenant)
        self.login(self.t2,self.tenant2)
    def tearDown(self):
        self.admin.close();self.tclient.close();self.t2.close()
        db.DB_PATH=self.old_db;tenant_portal.UPLOADS=self.old_uploads
        if self.oldbackup is None:os.environ.pop('BACKUP_DIRECTORY',None)
        else:os.environ['BACKUP_DIRECTORY']=self.oldbackup
        self.temp.cleanup()
    def admin_call(self,method,path,data=None,expected=200):
        r=self.admin.request(method,'/api/'+path,json=data,headers=self.ahead)
        self.assertEqual(r.status_code,expected,r.text)
        return r.json()
    def login(self,client,tenant):
        c=tenant['portal_credentials']
        r=client.post('/api/tenant/auth/login',json={'phone':c['username'],'password':c['password'],'access_code':c['access_code']})
        self.assertEqual(r.status_code,200,r.text)
        if client is self.tclient:self.th={'x-csrf-token':r.json()['csrf']}
        else:self.t2h={'x-csrf-token':r.json()['csrf']}
    def img(self):
        b=io.BytesIO();Image.new('RGB',(40,35),'green').save(b,'PNG');return b.getvalue()
    def post(self,client,headers,n=2,room_id=None):
        files=[('photos',(f'pic_{i}.png',self.img(),'image/png')) for i in range(n)]
        data={'title':'Điều hòa chảy nước','category':'water','priority':'high','description':'Nước chảy từ dàn lạnh vào phòng.'}
        if room_id:data['room_id']=str(room_id)
        return client.post('/api/tenant/tickets',data=data,files=files,headers=headers)
    def enable_zalo(self):
        with db.tx() as con:
            con.execute("UPDATE zalo_config SET enabled=1,ticket_enabled=1,account_selection='12345',bot_url='http://host.docker.internal:3000',media_url='http://127.0.0.1:8088'")
            for thread,kind in [('111222333444','user'),('999888777666','group')]:
                con.execute("INSERT INTO zalo_destinations(name,thread_id,kind,property_id,enabled,on_invoice,on_payment,on_ticket) VALUES(?,?,?,?,1,0,0,1)",('Chủ '+kind,thread,kind,self.prop))
    def test_migration_opt_in_and_keep_old_tickets(self):
        old=self.admin_call('POST','tickets',{'room_id':self.room,'title':'Trước nâng cấp','reported_at':date.today().isoformat()})['id']
        with db.connect() as con:con.execute('PRAGMA user_version=7')
        db.init_db()
        with db.connect() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],10)
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertTrue(con.execute('SELECT id FROM tickets WHERE id=?',(old,)).fetchone())
            self.assertEqual(con.execute('SELECT ticket_enabled FROM zalo_config').fetchone()[0],0)
    def test_create_auto_room_and_private_images(self):
        r=self.post(self.tclient,self.th,3,room_id=self.room2)
        self.assertEqual(r.status_code,200,r.text)
        tid=r.json()['id'];self.assertEqual(r.json()['photos'],3)
        with db.connect() as con:
            row=con.execute('SELECT room_id,reported_by_tenant_id,status FROM tickets WHERE id=?',(tid,)).fetchone()
            self.assertEqual(row['room_id'],self.room)
            self.assertEqual(row['reported_by_tenant_id'],self.tenant['id'])
            self.assertEqual(row['status'],'new')
        self.assertEqual(len(self.tclient.get('/api/tenant/tickets').json()),1)
        self.assertEqual(len(self.t2.get('/api/tenant/tickets').json()),0)
        p=self.tclient.get(f'/api/tenant/tickets/{tid}/photos').json()
        self.assertEqual(len(p),3)
        self.assertEqual(self.tclient.get(p[0]['url']).status_code,200)
        self.assertEqual(self.t2.get(p[0]['url']).status_code,404)
        self.assertEqual(self.tclient.get('/api/v8/tickets/%s/photos'%tid).status_code,401)
        self.assertEqual(self.tclient.get('/api/tenants').status_code,401)
        self.assertEqual(self.admin.get('/api/v8/tickets/%s/photos'%tid).status_code,200)
        self.assertEqual(self.admin.get('/api/v8/tickets/%s/photos/%s'%(tid,p[0]['id'])).headers['content-type'],'image/jpeg')
    def test_limit_five_and_untrusted_image(self):
        r=self.post(self.tclient,self.th,6)
        self.assertEqual(r.status_code,400,r.text)
        self.assertEqual(self.tclient.get('/api/tenant/tickets').json(),[])
        files=[('photos',('fake.png',b'<script>alert(1)</script>','image/png'))]
        r=self.tclient.post('/api/tenant/tickets',data={'title':'Ảnh giả'},files=files,headers=self.th)
        self.assertEqual(r.status_code,400,r.text)
        self.assertEqual(list(tenant_portal.UPLOADS.glob('*.jpg')),[])
    def test_zalo_queue_owner_only_and_album_5(self):
        self.enable_zalo()
        r=self.post(self.tclient,self.th,5)
        self.assertEqual(r.status_code,200,r.text)
        tid=r.json()['id']
        with db.connect() as con:
            rows=con.execute("SELECT * FROM zalo_outbox WHERE ticket_id=? ORDER BY id",(tid,)).fetchall()
            self.assertEqual(len(rows),2)
            self.assertIn('Phòng: P01',rows[0]['message'])
            self.assertIn('Khách thuê: Nguyễn Thị Trang',rows[0]['message'])
            self.assertIn('Điều hòa chảy nước',rows[0]['message'])
        captured=[]
        def stub(config,dest,msg,image_url=None,image_urls=None):
            captured.append((dest['kind'],msg,image_urls))
            for url in image_urls or []:
                response=self.admin.get(url.replace('http://127.0.0.1:8088',''))
                self.assertEqual(response.status_code,200,response.text[:150] if response.status_code!=200 else '')
        with patch.object(notify,'_bot_send',side_effect=stub):
            self.assertEqual(notify.process_outbox(),2)
        self.assertEqual(len(captured),2)
        self.assertTrue(all(len(a[2])==5 for a in captured))
        with db.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM zalo_outbox WHERE ticket_id=? AND status='sent'",(tid,)).fetchone()[0],2)
    def test_bot_native_album_payload_single_request(self):
        captured=[]
        def fake_http(opener,url,payload):
            captured.append((url,payload))
            return {'success':True,'deliveryStatus':'accepted'}
        config={'bot_url':'http://host.docker.internal:3000','account_selection':'zalo123'}
        dest={'thread_id':'111222333444','kind':'group'}
        with patch.object(notify,'_credentials',return_value=('operator','secret')),patch.object(notify,'_http_json',side_effect=fake_http):
            notify._bot_send(config,dest,'Nội dung đầy đủ',image_urls=['http://media/'+str(i) for i in range(3)])
        self.assertEqual(len(captured),2) # login and ONE send, no 3 separate sends
        self.assertEqual(captured[1][0],'http://host.docker.internal:3000/api/sendImagesByAccount')
        self.assertEqual(len(captured[1][1]['imagePaths']),3)
        self.assertEqual(captured[1][1]['message'],'Nội dung đầy đủ')
    def test_staff_property_scope_and_photo_edits(self):
        r=self.post(self.tclient,self.th,2);self.assertEqual(r.status_code,200,r.text)
        tid=r.json()['id']
        user=self.admin_call('POST','users',{'username':'staffqa','full_name':'Nhân viên QA','role':'staff','password':'strong-staff-pass-123'})
        uid=user['id']
        with db.tx() as con:
            con.execute("INSERT INTO property_grants(user_id,property_id) VALUES(?,?)",(uid,self.prop2))
        employee=TestClient(main.app)
        try:
            r=employee.post('/api/auth/login',json={'username':'staffqa','password':'strong-staff-pass-123'})
            self.assertEqual(r.status_code,200,r.text)
            h={'x-csrf-token':r.json()['csrf']}
            # Staff at Ngõ 404 cannot retrieve, mutate or move a ticket in Ngõ 303.
            self.assertIn(employee.get(f'/api/v8/tickets/{tid}/photos').status_code,(403,404))
            self.assertIn(employee.put(f'/api/tickets/{tid}',headers=h,json={'room_id':self.room2,'title':'Chuyển phòng','reported_at':date.today().isoformat()}).status_code,(403,404))
            self.assertIn(employee.delete(f'/api/tickets/{tid}',headers=h).status_code,(403,404))
            self.assertIn(employee.post('/api/v8/tickets',headers=h,data={'room_id':str(self.room),'title':'Tấn công','reported_at':date.today().isoformat()}).status_code,(403,404))
        finally:employee.close()
        # Admin can remove images of existing ticket without deleting the ticket.
        photos=self.admin.get(f'/api/v8/tickets/{tid}/photos').json()
        delete=self.admin.delete(f'/api/v8/tickets/{tid}/photos/{photos[0]["id"]}',headers=self.ahead)
        self.assertEqual(delete.status_code,200,delete.text)
        self.assertEqual(len(self.admin.get(f'/api/v8/tickets/{tid}/photos').json()),1)
        self.assertEqual(len(self.tclient.get('/api/tenant/tickets').json()),1)

    def test_single_image_text_only_and_rate_limit(self):
        with patch.object(notify,'_credentials',return_value=('admin','password')):
            calls=[]
            def fake_http(_,url,payload):
                calls.append((url,payload));return {'success':True}
            with patch.object(notify,'_http_json',side_effect=fake_http):
                notify._bot_send({'bot_url':'http://host.docker.internal:3000','account_selection':'123'},
                                {'thread_id':'1234567890','kind':'user'},'Thông báo',image_urls=['http://host/only.jpg'])
            self.assertTrue(calls[-1][0].endswith('/api/sendImageByAccount'))
            self.assertEqual(calls[-1][1]['message'],'Thông báo')
        for i in range(5):
            response=self.post(self.tclient,self.th,0)
            self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.post(self.tclient,self.th,0).status_code,429)

    def test_zalo_toggle_and_non_owner_destination(self):
        self.enable_zalo()
        with db.tx() as con:
            con.execute('INSERT INTO zalo_destinations(name,thread_id,kind,property_id,tenant_id,on_ticket) VALUES(?,?,?,?,?,0)',('khách','123456789','user',self.prop,self.tenant['id']))
        self.assertEqual(self.admin_call('POST','v6/zalo/destinations',{'name':'Leak','thread_id':'123456789','kind':'user','tenant_id':self.tenant['id'],'on_ticket':1},400)['detail'][:7],'Nơi nhậ')
        self.post(self.tclient,self.th,1)
        with db.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM zalo_outbox WHERE event='ticket'").fetchone()[0],2)
        with db.tx() as con:con.execute('UPDATE zalo_config SET ticket_enabled=0')
        self.post(self.tclient,self.th,1)
        with db.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM zalo_outbox WHERE event='ticket'").fetchone()[0],2)

if __name__=='__main__':unittest.main()
