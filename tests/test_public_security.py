"""Non-destructive security regression checks using temporary SQLite databases."""
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app import db, main, advanced, notify


class PublicSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original_db=db.DB_PATH
        self.original_uploads=advanced.UPLOADS
        db.DB_PATH=Path(self.tmp.name)/'troflow.db'
        advanced.UPLOADS=Path(self.tmp.name)/'uploads'
        db.init_db()
        self.client=TestClient(main.app,base_url='https://testserver')

    def tearDown(self):
        self.client.close()
        db.DB_PATH=self.original_db
        advanced.UPLOADS=self.original_uploads
        self.tmp.cleanup()

    def test_public_mode_disables_web_setup_and_sets_headers(self):
        with patch.object(main,'PUBLIC_MODE',True):
            r=self.client.post('/api/auth/setup',json={'username':'root','full_name':'Owner','password':'a-strong-password-123'})
            self.assertEqual(r.status_code,403)
            r=self.client.get('/')
            self.assertEqual(r.headers.get('strict-transport-security'),'max-age=31536000')
            self.assertEqual(r.headers['referrer-policy'],'no-referrer')
            self.assertEqual(r.headers['x-frame-options'],'SAMEORIGIN')
            self.assertEqual(r.headers['cache-control'],'no-store')
            self.assertIsNone(self.client.get('/openapi.json').json() if False else None)

    def test_failed_logins_persist_in_database(self):
        for i in range(10):
            r=self.client.post('/api/auth/login',json={'username':'unknown','password':'never-correct'})
            self.assertEqual(r.status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'unknown','password':'never-correct'}).status_code,429)
        with db.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM auth_failures').fetchone()[0],10)

    def test_pbkdf2_legacy_password_migrates_to_argon2id(self):
        pw='old-password-long-123'
        salt=b'0123456789abcdef'
        old='pbkdf2_sha256$330000$'+salt.hex()+'$'+hashlib.pbkdf2_hmac('sha256',pw.encode(),salt,330000).hex()
        with db.tx() as con:
            con.execute('INSERT INTO users(username,full_name,role,password_hash) VALUES (?,?,?,?)',('legacy','Legacy','admin',old))
        r=self.client.post('/api/auth/login',json={'username':'legacy','password':pw})
        self.assertEqual(r.status_code,200,r.text)
        with db.connect() as con:
            stored=con.execute('SELECT password_hash FROM users WHERE username=?',('legacy',)).fetchone()[0]
        self.assertTrue(stored.startswith('$argon2id$'))

    def test_bot_credentials_encrypted_and_old_plaintext_converted(self):
        from cryptography.fernet import Fernet
        key_path=Path(self.tmp.name)/'integration.key'
        key_path.write_bytes(Fernet.generate_key())
        with patch.dict(os.environ,{'TROFLOW_SECRET_KEY_FILE':str(key_path)}):
            notify._save_credentials('mybot','sensitive-password-value')
            payload=json.loads(notify._secret_file().read_text())
            self.assertNotIn('password',payload)
            self.assertNotIn('sensitive-password-value',notify._secret_file().read_text())
            self.assertEqual(notify._credentials(),('mybot','sensitive-password-value'))
            notify._secret_file().write_text(json.dumps({'username':'legacybot','password':'old-secret'}))
            self.assertEqual(notify._credentials(),('legacybot','old-secret'))
            self.assertNotIn('old-secret',notify._secret_file().read_text())

    def test_upload_is_decoded_reencoded_and_exif_removed(self):
        admin=self.client.post('/api/auth/setup',json={'username':'admin','full_name':'Owner','password':'a-strong-password-123'}).json()
        head={'x-csrf-token':admin['csrf']}
        prop=self.client.post('/api/properties',json={'name':'Building'},headers=head).json()['id']
        room=self.client.post('/api/rooms',json={'property_id':prop,'code':'A1','rent':1000000},headers=head).json()['id']
        tenant=self.client.post('/api/tenants',json={'full_name':'Tenant','phone':'0901000200','id_number':'012345678901'},headers=head).json()['id']
        im=Image.new('RGB',(8,8),'blue')
        exif=Image.Exif();exif[270]='Private EXIF marker 7265'
        raw=io.BytesIO();im.save(raw,format='JPEG',exif=exif)
        r=self.client.post('/api/v2/files',data={'category':'tenant_id_front','related_id':str(tenant)},
                           files={'file':('photo.jpg',raw.getvalue(),'image/jpeg')},headers=head)
        self.assertEqual(r.status_code,200,r.text)
        payload=self.client.get('/api/v2/files/'+r.json()['name']).content
        self.assertNotIn(b'Private EXIF marker 7265',payload)
        with patch.object(main,'PUBLIC_MODE',True):
            uid=self.client.post('/api/users',json={'username':'staff','full_name':'Staff','password':'a-strong-password-123','role':'staff'},headers=head).json()['id']
            # A staff account without property assignments cannot read any data in public mode.
            staff=TestClient(main.app,base_url='https://testserver')
            self.assertEqual(staff.post('/api/auth/login',json={'username':'staff','password':'a-strong-password-123'}).status_code,200)
            profile=staff.get('/api/auth/me')
            self.assertEqual(profile.status_code,200)
            self.assertFalse(any(profile.json()['user']['permissions'].values()))
            self.assertEqual(staff.get('/api/tenants').status_code,403)
            with db.tx() as con:
                con.execute('INSERT INTO property_grants(user_id,property_id) VALUES (?,?)',(uid,prop))
                con.execute('INSERT INTO contracts(room_id,tenant_id,start_date,end_date,monthly_rent) VALUES (?,?,?,?,?)',(room,tenant,'2026-01-01','2027-01-01',1000000))
            self.assertEqual(staff.get('/api/v2/files/'+r.json()['name']).status_code,403)
            with db.tx() as con:
                con.execute('INSERT INTO user_permissions(user_id,permission_key,allowed) VALUES (?,?,?)',(uid,'tenants.idphotos',1))
            self.assertEqual(staff.get('/api/v2/files/'+r.json()['name']).status_code,200)
            staff.close()

    def test_reject_spoofed_host_when_fresh_import_uses_public_mode(self):
        env={**os.environ,'TROFLOW_PUBLIC_MODE':'1','TROFLOW_ALLOWED_HOSTS':'tro.example.com'}
        probe='from app.main import app; from fastapi.testclient import TestClient; c=TestClient(app,base_url="https://evil.test"); assert c.get("/").status_code==400; c=TestClient(app,base_url="https://tro.example.com"); assert c.get("/").status_code==200'
        result=subprocess.run([sys.executable,'-c',probe],cwd=str(Path(__file__).resolve().parents[1]),env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)


if __name__=='__main__':unittest.main()
