import calendar
import csv
import hashlib
import hmac
import io
import json
import math
import os
import re
import secrets
import sqlite3
import tempfile
import time
from contextlib import asynccontextmanager
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from .db import init_db, connect, tx, one, rows, DB_PATH

@asynccontextmanager
async def lifespan(app):
    init_db()
    # Never blindly resend a message potentially delivered just before a crash.
    with tx() as con:
        con.execute("UPDATE zalo_outbox SET status='failed', error='Tiến trình gián đoạn; kiểm tra bên Zalo trước khi gửi lại.' WHERE status='sending'")
        con.execute("DELETE FROM notification_media WHERE expires_at < ?",(datetime.now(timezone.utc).isoformat(),))
    from .scheduler import start, stop
    start()
    try:
        yield
    finally:
        stop()


app = FastAPI(title='TrọFlow API', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
# Restrict DNS rebinding / forged Host header in Internet-facing mode.
if os.getenv('TROFLOW_PUBLIC_MODE','0')=='1':
    allowed=[host.strip() for host in os.getenv('TROFLOW_ALLOWED_HOSTS','').split(',') if host.strip()]
    if not allowed:
        raise RuntimeError('TROFLOW_ALLOWED_HOSTS must be configured in public mode.')
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=allowed+['localhost','127.0.0.1'])
STATIC = Path(__file__).parent / 'static'
PUBLIC_MODE = os.getenv('TROFLOW_PUBLIC_MODE', '0') == '1'
COOKIE_NAME = '__Host-troflow_session' if PUBLIC_MODE else 'troflow_session'
COOKIE_SECURE = PUBLIC_MODE or os.getenv('COOKIE_SECURE', '0') == '1'
# Persistent login throttling uses SQLite so container restarts cannot reset it.
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_USERNAME_LIMIT = 10
LOGIN_IP_LIMIT = 100

@app.middleware('http')
async def security_headers(request: Request, call_next):
    # Proxy should enforce a hard streaming request-body limit as well.
    declared_length=request.headers.get('content-length')
    if declared_length:
        try:
            if int(declared_length)<0:
                return JSONResponse({'detail':'Content-Length không hợp lệ.'},status_code=400)
            # Up to five normalized repair photos (3 MB each) need a larger
            # multipart envelope. Keep the previous strict cap elsewhere.
            path=request.url.path
            limit=(18*1024*1024 if path.startswith(('/api/tenant/tickets','/api/v8/tickets'))
                   else 7*1024*1024 if path=='/api/tenant/readings/submit'
                   else 5*1024*1024)
            if int(declared_length)>limit:
                return JSONResponse({'detail':'Yêu cầu quá lớn.'},status_code=413)
        except ValueError:
            return JSONResponse({'detail':'Content-Length không hợp lệ.'},status_code=400)
    if request.method in ('POST','PUT','PATCH','DELETE'):
        # Block cross-site requests, including unauthenticated setup/login calls.
        origin = request.headers.get('origin')
        if origin:
            from urllib.parse import urlsplit
            o = urlsplit(origin)
            host = request.headers.get('host','')
            if not o.hostname or o.netloc.lower() != host.lower() or o.scheme not in (('https',) if PUBLIC_MODE else ('http','https')):
                return JSONResponse({'detail':'Yêu cầu khác nguồn bị từ chối.'}, status_code=403)
        elif request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail':'Yêu cầu khác nguồn bị từ chối.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    # Both /advanced and /integrations are embedded by the parent app.
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data: https://img.vietqr.io; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=()'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
    if PUBLIC_MODE:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    if request.url.path.startswith('/api/') or request.url.path in ('/','/advanced','/integrations'):
        response.headers['Cache-Control'] = 'no-store'
    return response

def fail(message, status=400):
    raise HTTPException(status_code=status, detail=message)


def trim(v, field, max_length=250, required=False):
    value = str(v if v is not None else '').strip()
    if required and not value:
        fail(f'Vui lòng nhập {field}.')
    if len(value)>max_length:
        fail(f'{field} tối đa {max_length} ký tự.')
    return value


def positive(v, field, min_value=0, max_value=10_000_000_000):
    try:
        n = int(v)
    except (ValueError, TypeError):
        fail(f'{field} phải là số nguyên.')
    if n < min_value or n > max_value:
        fail(f'{field} phải trong khoảng {min_value} – {max_value}.')
    return n


def decimal(v, field):
    try:
        n = round(float(v), 3)
    except (ValueError, TypeError):
        fail(f'{field} phải là số.')
    if not math.isfinite(n) or n < 0 or n > 10_000_000:
        fail(f'{field} không hợp lệ.')
    return n


def date_str(v, field):
    s = trim(v, field, 10, True)
    try:
        if date.fromisoformat(s).isoformat()!=s:
            fail(f'{field} không hợp lệ.')
    except ValueError:
        fail(f'{field} phải theo định dạng YYYY-MM-DD.')
    return s


def period_str(v):
    s = trim(v, 'kỳ', 7, True)
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', s):
        fail('Kỳ phải theo định dạng YYYY-MM.')
    return s


def enum(v, field, allowed):
    s = trim(v, field, 50, True)
    if s not in allowed:
        fail(f'{field} không hợp lệ.')
    return s


PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2,
                                 hash_len=32, salt_len=16)
# An argon2id dummy record is used for non-existent accounts to reduce timing leakage.
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash('dummy-never-an-account-password')

def password_hash(password):
    return PASSWORD_HASHER.hash(password)

def check_password(password, stored):
    try:
        if stored.startswith('$argon2id$'):
            return PASSWORD_HASHER.verify(stored,password)
        alg, iterations, salt, digest = stored.split('$')
        if alg != 'pbkdf2_sha256':
            return False
        count=int(iterations)
        if count < 100000 or count>1_000_000:
            return False
        dk=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),count)
        return hmac.compare_digest(dk,bytes.fromhex(digest))
    except (VerifyMismatchError,VerificationError,ValueError,TypeError):
        return False


def strong_password(p):
    minimum=15 if PUBLIC_MODE else 10
    if not isinstance(p,str) or len(p)<minimum or len(p)>128:
        fail(f'Mật khẩu cần từ {minimum} đến 128 ký tự.')


def audit(con, user, action, entity, ident=None, details=''):
    con.execute('INSERT INTO audit_logs(user_id,action,entity,entity_id,details) VALUES (?,?,?,?,?)',
                (user['id'] if user else None,action,entity,ident,details[:300]))


def scope_records(user, records, tenant_list=False):
    grants=user.get('grant_ids',[])
    if user['role']=='admin' or not grants:
        return records
    if tenant_list:
        with connect() as con:
            allowed={r['tenant_id'] for r in rows(con,
                 "SELECT DISTINCT tenant_id FROM contracts c JOIN rooms r ON r.id=c.room_id WHERE r.property_id IN ("+
                 ','.join('?' for _ in grants)+")",grants)}
        return [r for r in records if r.get('id') in allowed]
    return [r for r in records if r.get('property_id',r.get('id')) in grants]


def legacy_scope_check(con,request,user,body):
    '''Protect original v1 API routes as well as new v2 routes.

    Scoped users must never be able to bypass property permissions by using an
    older URL.  We explicitly resolve target resources from the database.
    '''
    path=request.url.path
    method=request.method
    if path.startswith('/api/auth/'):
        return  # Any authenticated user may log out/change their own password.
    if path.startswith('/api/tenant/admin/'):
        return  # Tenant review endpoints validate property scope themselves.
    if path.startswith('/api/v8/tickets'):
        return  # V8 explicitly enforces room/property scope.
    if path.startswith('/api/v2/'):
        return  # V2 endpoints apply their own property and capability checks.
    if method in ('GET','HEAD'):
        if path.startswith('/api/export/') and user['grant_ids']:
            fail('Xuất dữ liệu toàn hệ thống cần quyền quản lý.',403)
        if path=='/api/readings/previous' and user['grant_ids']:
            rid=request.query_params.get('room_id')
            found=one(con,'SELECT property_id FROM rooms WHERE id=?',(rid,))
            if not found or found['property_id'] not in user['grant_ids']:
                fail('Không có quyền xem chỉ số phòng này.',403)
        return
    grants=user['grant_ids']
    if not grants:return
    parts=path.strip('/').split('/')
    entity=parts[1] if len(parts)>1 else ''
    property_id=body.get('property_id')
    if entity=='properties':
        if len(parts)>2 and parts[2].isdigit():
            property_id=int(parts[2])
    if entity in ('rooms','expenses'):
        if len(parts)>2 and parts[2].isdigit():
            current=one(con,f'SELECT property_id FROM {entity} WHERE id=?',(int(parts[2]),))
            if not current or current['property_id'] not in grants:fail('Không có quyền cơ sở.',403)
        property_id=body.get('property_id',property_id)
    elif entity in ('readings','tickets'):
        rid=body.get('room_id')
        if entity=='readings' and len(parts)>2 and parts[2].isdigit():
            original=one(con,'SELECT room_id FROM readings WHERE id=?',(int(parts[2]),))
            if not original:fail('Không tìm thấy chỉ số.',404)
            source=one(con,'SELECT property_id FROM rooms WHERE id=?',(original['room_id'],))
            if not source or source['property_id'] not in grants:
                fail('Chỉ số không thuộc cơ sở được phân quyền.',403)
            rid=rid or original['room_id']
        if len(parts)>2 and parts[2].isdigit() and entity=='tickets':
            original=one(con,'SELECT room_id FROM tickets WHERE id=?',(int(parts[2]),))
            if not original:fail('Không tìm thấy yêu cầu.',404)
            source=one(con,'SELECT property_id FROM rooms WHERE id=?',(original['room_id'],))
            if not source or source['property_id'] not in grants:
                fail('Yêu cầu sửa chữa không thuộc cơ sở được phân quyền.',403)
            rid=rid or original['room_id']
        if rid:
            found=one(con,'SELECT property_id FROM rooms WHERE id=?',(rid,))
            property_id=found['property_id'] if found else None
    elif entity=='contracts':
        if len(parts)>2 and parts[2].isdigit():
            found=one(con,'SELECT r.property_id FROM contracts c JOIN rooms r ON r.id=c.room_id WHERE c.id=?',(int(parts[2]),))
            property_id=found['property_id'] if found else None
        elif body.get('room_id'):
            found=one(con,'SELECT property_id FROM rooms WHERE id=?',(body['room_id'],))
            property_id=found['property_id'] if found else None
    elif entity=='tenants' and len(parts)>2 and parts[2].isdigit():
        found=one(con,'''SELECT r.property_id FROM contracts c JOIN rooms r ON r.id=c.room_id
              WHERE c.tenant_id=? AND r.property_id IN ('''+','.join('?' for _ in grants)+') LIMIT 1',
              (int(parts[2]),*grants))
        property_id=found['property_id'] if found else None
    elif entity=='payments':
        iid=body.get('invoice_id')
        if not iid and len(parts)>2 and parts[2].isdigit():
            linked=one(con,'SELECT invoice_id FROM payments WHERE id=?',(int(parts[2]),))
            iid=linked['invoice_id'] if linked else None
        if iid:
            found=one(con,'SELECT r.property_id FROM invoices i JOIN rooms r ON r.id=i.room_id WHERE i.id=?',(iid,))
            property_id=found['property_id'] if found else None
    elif entity=='invoices':
        rid=body.get('room_id')
        if rid:
            found=one(con,'SELECT property_id FROM rooms WHERE id=?',(rid,))
            property_id=found['property_id'] if found else None
        elif len(parts)>2 and parts[2].isdigit():
            found=one(con,'SELECT r.property_id FROM invoices i JOIN rooms r ON r.id=i.room_id WHERE i.id=?',(int(parts[2]),))
            property_id=found['property_id'] if found else None
        # 'generate all' must not create outside the assigned property.
    if property_id is None or int(property_id) not in grants:
        fail('Thao tác cần chọn đúng cơ sở được phân quyền.',403)


async def authorized(request: Request):
    token=request.cookies.get(COOKIE_NAME,'')
    if not token or len(token)>200:fail('Vui lòng đăng nhập.',401)
    th=hashlib.sha256(token.encode()).hexdigest()
    with connect() as con:
        user=one(con,'''SELECT u.id,u.username,u.full_name,u.role,u.job_role,u.active,s.csrf_token
             FROM sessions s JOIN users u ON u.id=s.user_id
             WHERE s.token_hash=? AND s.expires_at>?''',(th,datetime.now(timezone.utc).isoformat()))
        if not user or not user['active']:fail('Phiên đăng nhập hết hạn.',401)
        user['grant_ids']=[r['property_id'] for r in rows(con,
              'SELECT property_id FROM property_grants WHERE user_id=?',(user['id'],))]
        # The legacy app treated an empty scope as all properties; fail closed online.
        if PUBLIC_MODE and user['role']!='admin' and not user['grant_ids'] and not request.url.path.startswith('/api/auth/'):
            fail('Nhân viên chưa được gán cơ sở. Liên hệ quản trị viên.',403)
        from .permissions import effective, route_permission
        user['permissions']=effective(con,user)
        if PUBLIC_MODE and user['role']!='admin' and not user['grant_ids']:
            user['permissions']={name:False for name in user['permissions']}
        capability=route_permission(request.url.path,request.method)
        if user['role']!='admin' and request.url.path.startswith('/api/') and not request.url.path.startswith('/api/auth/'):
            if capability is None or not user['permissions'].get(capability,False):
                fail('Tài khoản chưa được cấp quyền: '+str(capability or 'API'),403)
        if request.method in ('POST','PUT','PATCH','DELETE'):
            csrf=request.headers.get('x-csrf-token','')
            if not csrf or not hmac.compare_digest(csrf,user['csrf_token']):
                fail('Phiên bảo vệ không hợp lệ. Hãy tải lại trang.',403)
            try:
                data=await request.json() if request.headers.get('content-type','').startswith('application/json') else {}
            except Exception:data={}
            if not isinstance(data,dict):data={}
            if user['role']!='admin':legacy_scope_check(con,request,user,data)
        elif user['role']!='admin':legacy_scope_check(con,request,user,{})
    return user


def admin_user(user=Depends(authorized)):
    if user['role'] != 'admin':
        fail('Chỉ quản trị viên được thực hiện thao tác này.', 403)
    return user


def json_ok(**kwargs):
    return {'ok':True, **kwargs}


def insert(con, table, values):
    cols = list(values)
    q = ','.join('?' for _ in cols)
    cursor = con.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({q})", tuple(values.values()))
    return cursor.lastrowid


def update(con, table, ident, values):
    clause = ', '.join(f'{k}=?' for k in values)
    cursor = con.execute(f'UPDATE {table} SET {clause} WHERE id=?', (*values.values(),ident))
    if not cursor.rowcount:
        fail('Không tìm thấy dữ liệu.',404)


def exists(con, table, ident):
    if not one(con,f'SELECT id FROM {table} WHERE id=?',(ident,)):
        fail('Không tìm thấy dữ liệu liên quan.',404)


def integrity(exc):
    msg = str(exc).lower()
    if 'unique' in msg:
        fail('Bản ghi đã tồn tại hoặc đang bị trùng.')
    if 'foreign key' in msg:
        fail('Dữ liệu đang được sử dụng, không thể xóa.')
    if 'check constraint' in msg:
        fail('Dữ liệu không hợp lệ.')
    fail('Không thể lưu do ràng buộc dữ liệu.')

@app.get('/api/health')
def health():
    with connect() as con:
        con.execute('SELECT 1').fetchone()
    return {'status':'ok'}

@app.get('/api/auth/status')
def status():
    with connect() as con:
        return {'initialized': bool(con.execute('SELECT 1 FROM users LIMIT 1').fetchone()),'setup_via_cli':PUBLIC_MODE}

@app.post('/api/auth/setup')
def setup(data: dict, response: Response):
    if PUBLIC_MODE:
        fail('Chế độ Internet: khởi tạo Admin bằng lệnh CLI trên server.',403)
    username = trim(data.get('username'), 'tên đăng nhập', 40, True)
    fullname = trim(data.get('full_name'), 'họ tên', 100, True)
    pw = data.get('password','')
    strong_password(pw)
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',username):
        fail('Tên đăng nhập gồm 3–40 ký tự Latin, số hoặc . _ -')
    try:
        with tx() as con:
            if con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                fail('Hệ thống đã thiết lập.',403)
            uid = insert(con,'users',dict(username=username,full_name=fullname,password_hash=password_hash(pw),role='admin'))
            audit(con,{'id':uid},'create','user',uid,'Khởi tạo quản trị viên')
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return make_session(uid, response)


def make_session(uid,response):
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    expiry = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    with tx() as con:
        con.execute('DELETE FROM sessions WHERE expires_at < ?', (datetime.now(timezone.utc).isoformat(),))
        con.execute('INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES(?,?,?,?)',
                    (hashlib.sha256(token.encode()).hexdigest(),uid,csrf,expiry))
        user = one(con,'SELECT id,username,full_name,role,job_role FROM users WHERE id=?',(uid,))
        from .permissions import effective
        user['permissions']=effective(con,user)
    response.set_cookie(COOKIE_NAME,token,max_age=43200,path='/',httponly=True,secure=COOKIE_SECURE,samesite='strict')
    return {'user':user,'csrf':csrf}

@app.post('/api/auth/login')
def login(data: dict, request: Request,response: Response):
    ip = request.client.host if request.client else 'unknown'
    uname = trim(data.get('username'), 'tên đăng nhập',40).lower()
    pw = str(data.get('password',''))
    if len(pw)>512:
        fail('Tên đăng nhập hoặc mật khẩu không đúng.',401)
    now = int(time.time())
    ip_key=hashlib.sha256(ip.encode()).hexdigest()
    user_key=hashlib.sha256(uname.encode()).hexdigest()
    with tx() as con:
        con.execute('DELETE FROM auth_failures WHERE at < ?', (now-LOGIN_WINDOW_SECONDS,))
        ip_count=one(con,'SELECT COUNT(*) n FROM auth_failures WHERE ip_hash=?',(ip_key,))['n']
        username_count=one(con,'SELECT COUNT(*) n FROM auth_failures WHERE username_hash=?',(user_key,))['n']
    if ip_count>=LOGIN_IP_LIMIT or username_count>=LOGIN_USERNAME_LIMIT:
        fail('Đăng nhập quá nhiều lần. Thử lại sau 15 phút.',429)
    with connect() as con:
        record=one(con,'SELECT * FROM users WHERE username=?',(uname,))
    # Match the duration of PBKDF2 verification for unknown accounts too.
    valid=check_password(pw,record['password_hash'] if record and record['active'] else DUMMY_PASSWORD_HASH)
    if not record or not record['active'] or not valid:
        with tx() as con:
            con.execute('INSERT INTO auth_failures(ip_hash,username_hash,at) VALUES(?,?,?)',(ip_key,user_key,now))
        fail('Tên đăng nhập hoặc mật khẩu không đúng.',401)
    with tx() as con:
        con.execute('DELETE FROM auth_failures WHERE username_hash=? AND ip_hash=?',(user_key,ip_key))
        if not record['password_hash'].startswith('$argon2id$') or PASSWORD_HASHER.check_needs_rehash(record['password_hash']):
            con.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(pw),record['id']))
    return make_session(record['id'],response)

@app.get('/api/auth/me')
def me(user=Depends(authorized)):
    return {'user':{**{k:user[k] for k in ('id','username','full_name','role','job_role')},'permissions':user['permissions']},'csrf':user['csrf_token']}

@app.post('/api/auth/logout')
def logout(request: Request,response: Response,user=Depends(authorized)):
    token = request.cookies.get(COOKIE_NAME,'')
    with tx() as con:
        con.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE_NAME,path='/')
    return json_ok()

@app.post('/api/auth/change-password')
def change_password(data: dict,request: Request,response: Response,user=Depends(authorized)):
    with connect() as con:
        record = one(con,'SELECT * FROM users WHERE id=?',(user['id'],))
    if not check_password(str(data.get('current_password','')),record['password_hash']):
        fail('Mật khẩu hiện tại không chính xác.')
    pw = data.get('new_password','')
    strong_password(pw)
    with tx() as con:
        con.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(pw),user['id']))
        con.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
        audit(con,user,'change_password','user',user['id'])
    response.delete_cookie(COOKIE_NAME,path='/')
    return json_ok(message='Đổi mật khẩu thành công. Hãy đăng nhập lại.')

@app.get('/api/properties')
def properties(user=Depends(authorized)):
    with connect() as con:
        return scope_records(user,rows(con,'''SELECT p.*,COUNT(DISTINCT r.id) room_count,
                     COUNT(DISTINCT CASE WHEN c.id IS NOT NULL THEN r.id END) occupied_count
                     FROM properties p LEFT JOIN rooms r ON r.property_id=p.id
                     LEFT JOIN contracts c ON c.room_id=r.id AND c.status='active'
                     GROUP BY p.id ORDER BY p.id DESC'''))

@app.post('/api/properties')
def add_property(data:dict,user=Depends(admin_user)):
    vals=dict(name=trim(data.get('name'),'tên cơ sở',120,True),address=trim(data.get('address'),'địa chỉ',250),
              manager_phone=trim(data.get('manager_phone'),'điện thoại',30),
              electric_rate=positive(data.get('electric_rate',3500),'Giá điện'),
              water_rate=positive(data.get('water_rate',20000),'Giá nước'),
              service_fee=positive(data.get('service_fee',100000),'Phí dịch vụ'))
    with tx() as con:
        ident=insert(con,'properties',vals)
        audit(con,user,'create','property',ident)
    return json_ok(id=ident)

@app.put('/api/properties/{ident}')
def edit_property(ident:int,data:dict,user=Depends(authorized)):
    vals=dict(name=trim(data.get('name'),'tên cơ sở',120,True),address=trim(data.get('address'),'địa chỉ',250),
              manager_phone=trim(data.get('manager_phone'),'điện thoại',30),
              electric_rate=positive(data.get('electric_rate',0),'Giá điện'),
              water_rate=positive(data.get('water_rate',0),'Giá nước'),
              service_fee=positive(data.get('service_fee',0),'Phí dịch vụ'))
    with tx() as con:
        update(con,'properties',ident,vals)
        audit(con,user,'update','property',ident)
    return json_ok()

@app.delete('/api/properties/{ident}')
def delete_property(ident:int,user=Depends(authorized)):
    try:
        with tx() as con:
            con.execute('DELETE FROM properties WHERE id=?',(ident,))
            audit(con,user,'delete','property',ident)
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return json_ok()

ROOM_SQL = '''SELECT r.*, p.name property_name, c.id contract_id, c.tenant_id,
              t.full_name tenant_name,t.phone tenant_phone,t.id_number tenant_id_number,t.photo_path tenant_photo_path, c.end_date contract_end,
              CASE WHEN c.id IS NOT NULL THEN 'occupied' ELSE r.condition END status
              FROM rooms r JOIN properties p ON p.id=r.property_id
              LEFT JOIN contracts c ON c.room_id=r.id AND c.status='active'
              LEFT JOIN tenants t ON t.id=c.tenant_id'''

@app.get('/api/rooms')
def rooms(user=Depends(authorized)):
    with connect() as con:
        return scope_records(user,rows(con,ROOM_SQL+' ORDER BY p.name,r.code'))

@app.post('/api/rooms')
def add_room(data:dict,user=Depends(authorized)):
    vals=room_values(data)
    try:
        with tx() as con:
            exists(con,'properties',vals['property_id'])
            ident=insert(con,'rooms',vals)
            audit(con,user,'create','room',ident)
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return json_ok(id=ident)


def room_values(data):
    return dict(property_id=positive(data.get('property_id'),'Cơ sở',1),
                code=trim(data.get('code'),'mã phòng',30,True),floor=trim(data.get('floor'),'tầng',30),
                area=decimal(data.get('area',0),'Diện tích'),rent=positive(data.get('rent'),'Giá thuê'),
                deposit=positive(data.get('deposit',0),'Tiền cọc'),
                condition=enum(data.get('condition','ready'),'Tình trạng',['ready','maintenance','inactive']),
                notes=trim(data.get('notes'),'ghi chú',1000))

@app.put('/api/rooms/{ident}')
def edit_room(ident:int,data:dict,user=Depends(authorized)):
    vals=room_values(data)
    try:
        with tx() as con:
            current=one(con,'SELECT * FROM rooms WHERE id=?',(ident,))
            if not current: fail('Không tìm thấy phòng.',404)
            if one(con,"SELECT id FROM contracts WHERE room_id=? AND status='active'",(ident,)):
                if vals['property_id']!=current['property_id'] or vals['condition']!='ready':
                    fail('Không thể chuyển cơ sở hoặc khóa phòng đang có hợp đồng.')
            update(con,'rooms',ident,vals)
            audit(con,user,'update','room',ident)
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return json_ok()

@app.delete('/api/rooms/{ident}')
def delete_room(ident:int,user=Depends(authorized)):
    try:
        with tx() as con:
            cur=con.execute('DELETE FROM rooms WHERE id=?',(ident,))
            if not cur.rowcount: fail('Không tìm thấy phòng.',404)
            audit(con,user,'delete','room',ident)
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return json_ok()

TENANT_SQL = '''SELECT t.*, (SELECT a.enabled FROM tenant_portal_accounts a WHERE a.tenant_id=t.id) portal_enabled, (SELECT a.property_id FROM tenant_portal_accounts a WHERE a.tenant_id=t.id) portal_property_id, COUNT(DISTINCT CASE WHEN c.status='active' THEN c.id END) active_contracts,
                GROUP_CONCAT(DISTINCT CASE WHEN c.status='active' THEN r.code END) room_codes
                FROM tenants t LEFT JOIN contracts c ON c.tenant_id=t.id
                LEFT JOIN rooms r ON r.id=c.room_id GROUP BY t.id'''
@app.get('/api/tenants')
def tenants(user=Depends(authorized)):
    with connect() as con:
        return scope_records(user,rows(con,TENANT_SQL+' ORDER BY t.id DESC'),tenant_list=True)

def tenant_values(data, creating=False):
    id_number=trim(data.get('id_number'),'CCCD',30,creating)
    if id_number and not re.fullmatch(r'(?:[0-9]{9}|[0-9]{12})',id_number):
        fail('CCCD/CMND phải có 9 hoặc 12 chữ số.')
    return dict(full_name=trim(data.get('full_name'),'họ tên',120,True),phone=trim(data.get('phone'),'số điện thoại',30,True),
                email=trim(data.get('email'),'email',120),id_number=id_number,
                hometown=trim(data.get('hometown'),'quê quán',250),notes=trim(data.get('notes'),'ghi chú',1000))

@app.post('/api/tenants')
def add_tenant(data:dict,user=Depends(authorized)):
    with tx() as con:
        ident=insert(con,'tenants',tenant_values(data,creating=True))
        creds=None
        if data.get('portal_enabled'):
            if user['role']!='admin':fail('Chỉ Admin có thể cấp tài khoản khách thuê.',403)
            from .tenant_portal import provision
            creds=provision(con,ident,int(data.get('portal_property_id') or 0),True,user)
        audit(con,user,'create','tenant',ident)
    return json_ok(id=ident,portal_credentials=creds)

@app.put('/api/tenants/{ident}')
def edit_tenant(ident:int,data:dict,user=Depends(authorized)):
    with tx() as con:
        update(con,'tenants',ident,tenant_values(data))
        creds=None
        if 'portal_enabled' in data:
            if user['role']!='admin':fail('Chỉ Admin có thể cấu hình tài khoản khách thuê.',403)
            from .tenant_portal import provision
            if data.get('portal_enabled'):
                creds=provision(con,ident,int(data.get('portal_property_id') or 0),True,user)
            else:
                old=one(con,'SELECT * FROM tenant_portal_accounts WHERE tenant_id=?',(ident,))
                if old:provision(con,ident,old['property_id'],False,user)
        audit(con,user,'update','tenant',ident)
    return json_ok(portal_credentials=creds)

@app.delete('/api/tenants/{ident}')
def delete_tenant(ident:int,user=Depends(authorized)):
    try:
        with tx() as con:
            cur=con.execute('DELETE FROM tenants WHERE id=?',(ident,))
            if not cur.rowcount: fail('Không tìm thấy người thuê.',404)
            audit(con,user,'delete','tenant',ident)
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return json_ok()

CONTRACT_SQL = '''SELECT c.*,r.code room_code,r.property_id,p.name property_name,
                  t.full_name tenant_name,t.phone tenant_phone,t.id_number tenant_id_number,t.photo_path tenant_photo_path FROM contracts c
                  JOIN rooms r ON r.id=c.room_id JOIN properties p ON p.id=r.property_id
                  JOIN tenants t ON t.id=c.tenant_id'''
@app.get('/api/contracts')
def contracts(user=Depends(authorized)):
    with connect() as con:
        return scope_records(user,rows(con,CONTRACT_SQL+' ORDER BY c.id DESC'))

@app.post('/api/contracts')
def add_contract(data:dict,user=Depends(authorized)):
    start=date_str(data.get('start_date'),'Ngày bắt đầu')
    end=date_str(data.get('end_date'),'Ngày kết thúc')
    if end<start: fail('Ngày kết thúc phải sau hoặc bằng ngày bắt đầu.')
    room_id=positive(data.get('room_id'),'Phòng',1)
    tenant_id=positive(data.get('tenant_id'),'Khách thuê',1)
    vals=dict(room_id=room_id,tenant_id=tenant_id,start_date=start,end_date=end,
              monthly_rent=positive(data.get('monthly_rent'),'Tiền thuê'),
              deposit=positive(data.get('deposit',0),'Tiền cọc'),
              due_day=positive(data.get('due_day',5),'Ngày thanh toán',1,28),
              occupants=positive(data.get('occupants',1),'Số người',1,50),
              notes=trim(data.get('notes'),'ghi chú',1000))
    try:
        with tx() as con:
            room=one(con,'SELECT * FROM rooms WHERE id=?',(room_id,))
            if not room or room['condition']!='ready': fail('Chỉ có thể cho thuê phòng đang sẵn sàng.')
            exists(con,'tenants',tenant_id)
            if one(con,"SELECT id FROM contracts WHERE room_id=? AND status='active'",(room_id,)):
                fail('Phòng này đang có hợp đồng hiệu lực.')
            ident=insert(con,'contracts',vals)
            tenant=one(con,'SELECT * FROM tenants WHERE id=?',(tenant_id,))
            con.execute('''INSERT INTO contract_residents(contract_id,tenant_id,full_name,phone,id_number,hometown,is_primary,moved_in)
               VALUES(?,?,?,?,?,?,1,?)''',(ident,tenant_id,tenant['full_name'],tenant['phone'],tenant['id_number'],tenant['hometown'],start))
            audit(con,user,'create','contract',ident)
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return json_ok(id=ident)

@app.put('/api/contracts/{ident}')
def edit_contract(ident:int,data:dict,user=Depends(authorized)):
    start=date_str(data.get('start_date'),'Ngày bắt đầu')
    end=date_str(data.get('end_date'),'Ngày kết thúc')
    if end<start: fail('Ngày kết thúc phải sau ngày bắt đầu.')
    vals=dict(start_date=start,end_date=end,monthly_rent=positive(data.get('monthly_rent'),'Tiền thuê'),
              deposit=positive(data.get('deposit',0),'Tiền cọc'),
              due_day=positive(data.get('due_day',5),'Ngày thanh toán',1,28),
              occupants=positive(data.get('occupants',1),'Số người',1,50),notes=trim(data.get('notes'),'ghi chú',1000))
    with tx() as con:
        current=one(con,'SELECT * FROM contracts WHERE id=?',(ident,))
        if not current: fail('Không tìm thấy hợp đồng.',404)
        if current['status']=='ended': fail('Không thể chỉnh sửa hợp đồng đã kết thúc.')
        if one(con,'SELECT id FROM invoices WHERE contract_id=? LIMIT 1',(ident,)) or one(con,'SELECT id FROM rent_coverage WHERE contract_id=? LIMIT 1',(ident,)):
            if vals['start_date']!=current['start_date'] or vals['monthly_rent']!=current['monthly_rent']:
                fail('Hợp đồng đã phát sinh hóa đơn: không thể sửa ngày bắt đầu/giá thuê.')
        update(con,'contracts',ident,vals)
        audit(con,user,'update','contract',ident)
    return json_ok()

@app.post('/api/contracts/{ident}/end')
def end_contract(ident:int,user=Depends(authorized)):
    with tx() as con:
        contract=one(con,'SELECT * FROM contracts WHERE id=?',(ident,))
        if not contract: fail('Không tìm thấy hợp đồng.',404)
        if contract['status']=='ended': fail('Hợp đồng đã kết thúc.')
        # Do not let the legacy endpoint bypass deposit/debt settlement.
        held=one(con,'''SELECT COALESCE(SUM(CASE WHEN kind='receive' THEN amount ELSE -amount END),0) n
                      FROM deposit_transactions WHERE contract_id=?''',(ident,))['n']
        unpaid=one(con,'''SELECT COALESCE(SUM(i.total-COALESCE(p.paid,0)),0) n
                     FROM invoices i LEFT JOIN (SELECT invoice_id,SUM(amount) paid FROM payments GROUP BY invoice_id) p
                     ON p.invoice_id=i.id WHERE i.contract_id=? AND i.status='published' ''',(ident,))['n']
        future=one(con,'''SELECT COUNT(*) n FROM rent_coverage WHERE contract_id=? AND period>? AND status='active' ''',(ident,date.today().strftime('%Y-%m')))['n']
        if held or unpaid or future:
            fail('Hợp đồng còn tiền cọc hoặc công nợ. Vui lòng dùng TrọFlow Nâng cao → Bàn giao phòng để quyết toán.')
        con.execute("UPDATE contracts SET status='ended' WHERE id=?",(ident,))
        con.execute('UPDATE contract_residents SET moved_out=? WHERE contract_id=? AND moved_out IS NULL',
                    (date.today().isoformat(),ident))
        audit(con,user,'end','contract',ident)
    return json_ok()

@app.delete('/api/contracts/{ident}')
def delete_contract(ident:int,user=Depends(authorized)):
    with tx() as con:
        contract=one(con,'SELECT id,room_id FROM contracts WHERE id=?',(ident,))
        if not contract:fail('Không tìm thấy hợp đồng.',404)
        # Finance must retain an immutable ledger and referential integrity.
        for table in ('invoices','deposit_transactions','rent_prepayment_batches','rent_coverage','handovers'):
            if one(con,f'SELECT 1 FROM {table} WHERE contract_id=? LIMIT 1',(ident,)):
                fail('Hợp đồng đã phát sinh hóa đơn/tiền cọc/trả trước/bàn giao. Không thể xóa lịch sử; hãy kết thúc hợp đồng.',409)
        con.execute('DELETE FROM contract_services WHERE contract_id=?',(ident,))
        con.execute('DELETE FROM contract_residents WHERE contract_id=?',(ident,))
        con.execute('DELETE FROM contracts WHERE id=?',(ident,))
        audit(con,user,'delete','contract',ident)
    return json_ok()

def occupied_contract(con, room_id, period):
    """Require a real tenant with a contract overlapping the requested billing month."""
    period=period_str(period)
    last=f'{period}-{calendar.monthrange(*map(int,period.split("-")))[1]:02d}'
    return one(con,'''SELECT c.id,c.tenant_id,t.full_name tenant_name,t.phone tenant_phone
         FROM contracts c JOIN tenants t ON t.id=c.tenant_id
         WHERE c.room_id=? AND c.start_date<=? AND c.end_date>=?
         ORDER BY CASE c.status WHEN 'active' THEN 0 ELSE 1 END,c.id DESC LIMIT 1''',
         (room_id,last,period+'-01'))

READING_SQL = '''SELECT d.*,r.code room_code,r.property_id,p.name property_name,
                 (d.electric_new-d.electric_old) electric_usage,(d.water_new-d.water_old) water_usage,
                 (SELECT t.full_name FROM contracts c JOIN tenants t ON t.id=c.tenant_id
                  WHERE c.room_id=d.room_id AND c.start_date<=date(d.period||'-01','start of month','+1 month','-1 day')
                   AND c.end_date>=d.period||'-01'
                  ORDER BY CASE c.status WHEN 'active' THEN 0 ELSE 1 END,c.id DESC LIMIT 1) tenant_name,
                 (SELECT t.phone FROM contracts c JOIN tenants t ON t.id=c.tenant_id
                   WHERE c.room_id=d.room_id AND c.start_date<=date(d.period||'-01','start of month','+1 month','-1 day')
                   AND c.end_date>=d.period||'-01' ORDER BY c.id DESC LIMIT 1) tenant_phone,
                 (SELECT t.id_number FROM contracts c JOIN tenants t ON t.id=c.tenant_id
                   WHERE c.room_id=d.room_id AND c.start_date<=date(d.period||'-01','start of month','+1 month','-1 day')
                   AND c.end_date>=d.period||'-01' ORDER BY c.id DESC LIMIT 1) tenant_id_number,
                 (SELECT t.photo_path FROM contracts c JOIN tenants t ON t.id=c.tenant_id
                   WHERE c.room_id=d.room_id AND c.start_date<=date(d.period||'-01','start of month','+1 month','-1 day')
                   AND c.end_date>=d.period||'-01' ORDER BY c.id DESC LIMIT 1) tenant_photo_path
                 FROM readings d JOIN rooms r ON r.id=d.room_id
                 JOIN properties p ON p.id=r.property_id'''
@app.get('/api/readings')
def readings(user=Depends(authorized)):
    with connect() as con:
        return scope_records(user,rows(con,READING_SQL+' ORDER BY d.period DESC,p.name,r.code'))

@app.post('/api/readings')
def save_reading(data:dict,user=Depends(authorized)):
    room_id=positive(data.get('room_id'),'Phòng',1)
    period=period_str(data.get('period'))
    eo=decimal(data.get('electric_old',0),'Điện cũ')
    en=decimal(data.get('electric_new',0),'Điện mới')
    wo=decimal(data.get('water_old',0),'Nước cũ')
    wn=decimal(data.get('water_new',0),'Nước mới')
    if en<eo or wn<wo: fail('Chỉ số mới không được nhỏ hơn chỉ số cũ.')
    with tx() as con:
        exists(con,'rooms',room_id)
        if not occupied_contract(con,room_id,period):
            fail('Phòng chưa có người thuê / hợp đồng trong kỳ đã chọn; không thể ghi chỉ số.')
        record=one(con,'SELECT id FROM readings WHERE room_id=? AND period=?',(room_id,period))
        if record:
            fail('Đã có chỉ số của phòng trong tháng/năm này. Hãy chọn Sửa thay vì tạo mới.',409)
        ident=insert(con,'readings',dict(room_id=room_id,period=period,electric_old=eo,
                                         electric_new=en,water_old=wo,water_new=wn)); action='create'
        audit(con,user,action,'reading',ident)
    return json_ok(id=ident)

def _reading_values(data):
    room_id=positive(data.get('room_id'),'Phòng',1)
    period=period_str(data.get('period'))
    eo=decimal(data.get('electric_old',0),'Điện cũ')
    en=decimal(data.get('electric_new',0),'Điện mới')
    wo=decimal(data.get('water_old',0),'Nước cũ')
    wn=decimal(data.get('water_new',0),'Nước mới')
    if en<eo or wn<wo:fail('Chỉ số mới không được nhỏ hơn chỉ số cũ.')
    return dict(room_id=room_id,period=period,electric_old=eo,electric_new=en,water_old=wo,water_new=wn)

@app.put('/api/readings/{ident}')
def update_reading(ident:int,data:dict,user=Depends(authorized)):
    values=_reading_values(data)
    with tx() as con:
        existing=one(con,'SELECT * FROM readings WHERE id=?',(ident,))
        if not existing:fail('Không tìm thấy chỉ số cần sửa.',404)
        exists(con,'rooms',values['room_id'])
        if not occupied_contract(con,values['room_id'],values['period']):
            fail('Phòng chưa có hợp đồng thuê trong kỳ mới.')
        overlap=one(con,'SELECT id FROM readings WHERE room_id=? AND period=? AND id<>?',
                    (values['room_id'],values['period'],ident))
        if overlap:fail('Phòng này đã có chỉ số tháng/năm được chọn. Vui lòng kiểm tra dữ liệu trùng.',409)
        linked=one(con,'SELECT id FROM invoices WHERE room_id=? AND period=? LIMIT 1',
                   (existing['room_id'],existing['period']))
        if linked:fail('Kỳ cũ đã có hóa đơn. Cần xử lý hóa đơn trước khi đổi chỉ số.',409)
        # Protect immutable published billing periods, even when moving readings into them.
        linked=one(con,'SELECT id FROM invoices WHERE room_id=? AND period=? LIMIT 1',
                   (values['room_id'],values['period']))
        if linked:fail('Kỳ mới đã có hóa đơn. Không thể di chuyển chỉ số đến kỳ này.',409)
        before=json.dumps({k:existing[k] for k in values},ensure_ascii=False)
        update(con,'readings',ident,values)
        audit(con,user,'update','reading',ident,before[:290])
    return json_ok(id=ident)

@app.delete('/api/readings/{ident}')
def delete_reading(ident:int,user=Depends(authorized)):
    with tx() as con:
        current=one(con,'SELECT * FROM readings WHERE id=?',(ident,))
        if not current:fail('Không tìm thấy chỉ số.',404)
        if one(con,'SELECT id FROM invoices WHERE room_id=? AND period=? LIMIT 1',
               (current['room_id'],current['period'])):
            fail('Chỉ số đã dùng lập hóa đơn. Hãy xử lý hóa đơn trước khi xóa.',409)
        con.execute('DELETE FROM readings WHERE id=?',(ident,))
        audit(con,user,'delete','reading',ident,f"room={current['room_id']} period={current['period']}")
    return json_ok()

@app.get('/api/readings/previous')
def prev_reading(room_id:int,period:str,user=Depends(authorized)):
    period=period_str(period)
    with connect() as con:
        rec=one(con,'''SELECT electric_new,water_new,period FROM readings
                        WHERE room_id=? AND period<? ORDER BY period DESC LIMIT 1''',(room_id,period))
    return rec or {'electric_new':0,'water_new':0,'period':None}

INVOICE_SQL = '''SELECT i.*,rd.electric_old,rd.electric_new,rd.water_old,rd.water_new,c.tenant_id,t.full_name tenant_name,t.phone tenant_phone,
                 r.code room_code,r.property_id,p.name property_name,p.address property_address,t.id_number tenant_id_number,t.photo_path tenant_photo_path,
                 COALESCE((SELECT SUM(amount) FROM payments WHERE invoice_id=i.id),0) paid,
                 i.total-COALESCE((SELECT SUM(amount) FROM payments WHERE invoice_id=i.id),0) balance
                 FROM invoices i LEFT JOIN readings rd ON rd.room_id=i.room_id AND rd.period=i.period
                 JOIN contracts c ON c.id=i.contract_id
                 JOIN tenants t ON t.id=c.tenant_id JOIN rooms r ON r.id=i.room_id
                 JOIN properties p ON p.id=r.property_id'''
@app.get('/api/invoices')
def invoices(user=Depends(authorized)):
    with connect() as con:
        return scope_records(user,rows(con,INVOICE_SQL+' ORDER BY i.period DESC,i.id DESC'))


def generate_invoice(con,contract,period,adjustment=0,note=''):
    from .billing import create
    try:
        return create(con,contract,period,adjustment,note,status='published')
    except ValueError as exc:
        fail(str(exc))

@app.post('/api/invoices/generate')
def generate(data:dict,user=Depends(authorized)):
    period=period_str(data.get('period'))
    room_id=data.get('room_id')
    try:
        adjustment=int(data.get('adjustment',0))
    except (ValueError,TypeError):
        fail('Điều chỉnh không hợp lệ.')
    if abs(adjustment)>100_000_000: fail('Điều chỉnh vượt giới hạn.')
    note=trim(data.get('note'),'ghi chú',1000)
    ids=[]
    with tx() as con:
        selection=CONTRACT_SQL+" WHERE c.status='active' AND c.start_date<=? AND c.end_date>=?"
        last=f'{period}-{calendar.monthrange(*map(int,period.split("-")))[1]:02d}'
        params=[last,period+'-01']
        if room_id:
            selection+=' AND c.room_id=?'; params.append(positive(room_id,'Phòng',1))
        contracts=rows(con,selection,tuple(params))
        if not contracts: fail('Không có hợp đồng phù hợp trong kỳ này.')
        for contract in contracts:
            ident=generate_invoice(con,contract,period,adjustment,note)
            if ident:
                ids.append(ident)
                audit(con,user,'create','invoice',ident,period)
                from .notify import enqueue_invoice_event
                enqueue_invoice_event(con,ident,'invoice')
    return json_ok(created=len(ids),ids=ids)

@app.delete('/api/invoices/{ident}')
def delete_invoice(ident:int,user=Depends(authorized)):
    try:
        with tx() as con:
            if not one(con,'SELECT id FROM invoices WHERE id=?',(ident,)):
                fail('Không tìm thấy hóa đơn.',404)
            if one(con,'SELECT id FROM payments WHERE invoice_id=?',(ident,)):
                fail('Đã ghi nhận thanh toán, không thể xóa hóa đơn.')
            con.execute('DELETE FROM invoices WHERE id=?',(ident,))
            audit(con,user,'delete','invoice',ident)
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return json_ok()

@app.get('/api/payments')
def payments(user=Depends(authorized)):
    with connect() as con:
        return scope_records(user,rows(con,'''SELECT pay.*,i.period,i.total,r.code room_code,p.name property_name,
                           t.full_name tenant_name,r.property_id FROM payments pay
                           JOIN invoices i ON i.id=pay.invoice_id JOIN contracts c ON c.id=i.contract_id
                           JOIN tenants t ON t.id=c.tenant_id JOIN rooms r ON r.id=i.room_id
                           JOIN properties p ON p.id=r.property_id ORDER BY pay.paid_at DESC,pay.id DESC'''))

@app.post('/api/payments')
def add_payment(data:dict,user=Depends(authorized)):
    invoice_id=positive(data.get('invoice_id'),'Hóa đơn',1)
    amount=positive(data.get('amount'),'Số tiền',1)
    paid_at=date_str(data.get('paid_at'),'Ngày thu')
    method=enum(data.get('method','transfer'),'Phương thức',['transfer','cash','other'])
    note=trim(data.get('note'),'ghi chú',1000)
    with tx() as con:
        inv=one(con,'''SELECT i.total,i.status,COALESCE(SUM(p.amount),0) paid FROM invoices i
                       LEFT JOIN payments p ON i.id=p.invoice_id WHERE i.id=? GROUP BY i.id''',(invoice_id,))
        if not inv: fail('Không tìm thấy hóa đơn.',404)
        if inv['status']!='published': fail('Hóa đơn cần được chốt trước khi thu tiền.')
        if amount>inv['total']-inv['paid']: fail('Số tiền thu vượt quá số dư hóa đơn.')
        ident=insert(con,'payments',dict(invoice_id=invoice_id,amount=amount,paid_at=paid_at,method=method,note=note))
        audit(con,user,'create','payment',ident)
        from .notify import enqueue_invoice_event
        enqueue_invoice_event(con,invoice_id,'payment')
    return json_ok(id=ident)

@app.put('/api/payments/{ident}')
def edit_payment(ident:int,data:dict,user=Depends(authorized)):
    amount=positive(data.get('amount'),'Số tiền',1)
    paid_at=date_str(data.get('paid_at'),'Ngày thu')
    method=enum(data.get('method','transfer'),'Phương thức',['transfer','cash','other'])
    note=trim(data.get('note'),'ghi chú',1000)
    with tx() as con:
        old=one(con,'SELECT * FROM payments WHERE id=?',(ident,))
        if not old:fail('Không tìm thấy khoản thu.',404)
        inv=one(con,'SELECT total FROM invoices WHERE id=?',(old['invoice_id'],))
        others=one(con,'SELECT COALESCE(SUM(amount),0) n FROM payments WHERE invoice_id=? AND id<>?',
                   (old['invoice_id'],ident))['n']
        if amount+others>inv['total']:fail('Số tiền chỉnh sửa vượt giá trị hóa đơn.',409)
        update(con,'payments',ident,dict(amount=amount,paid_at=paid_at,method=method,note=note))
        audit(con,user,'update','payment',ident,f"old_amount={old['amount']}; new_amount={amount}")
    return json_ok(id=ident)

@app.delete('/api/payments/{ident}')
def delete_payment(ident:int,user=Depends(authorized)):
    with tx() as con:
        cur=con.execute('DELETE FROM payments WHERE id=?',(ident,))
        if not cur.rowcount: fail('Không tìm thấy giao dịch.',404)
        audit(con,user,'delete','payment',ident)
    return json_ok()

@app.get('/api/expenses')
def expenses(user=Depends(authorized)):
    with connect() as con:
        return scope_records(user,rows(con,'''SELECT e.*,p.name property_name FROM expenses e
                         JOIN properties p ON p.id=e.property_id ORDER BY e.spent_on DESC,e.id DESC'''))

def expense_values(data):
    return dict(property_id=positive(data.get('property_id'),'Cơ sở',1),
                category=enum(data.get('category','other'),'Danh mục',
                              ['repair','utilities','supplies','operations','salary','other']),
                amount=positive(data.get('amount'),'Số tiền',1),
                spent_on=date_str(data.get('spent_on'),'Ngày chi'),
                description=trim(data.get('description'),'mô tả',1000))

@app.post('/api/expenses')
def add_expense(data:dict,user=Depends(authorized)):
    vals=expense_values(data)
    try:
        with tx() as con:
            exists(con,'properties',vals['property_id'])
            ident=insert(con,'expenses',vals)
            audit(con,user,'create','expense',ident)
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return json_ok(id=ident)

@app.put('/api/expenses/{ident}')
def edit_expense(ident:int,data:dict,user=Depends(authorized)):
    vals=expense_values(data)
    with tx() as con:
        exists(con,'properties',vals['property_id'])
        update(con,'expenses',ident,vals)
        audit(con,user,'update','expense',ident)
    return json_ok()

@app.delete('/api/expenses/{ident}')
def delete_expense(ident:int,user=Depends(authorized)):
    with tx() as con:
        cur=con.execute('DELETE FROM expenses WHERE id=?',(ident,))
        if not cur.rowcount: fail('Không tìm thấy phiếu chi.',404)
        audit(con,user,'delete','expense',ident)
    return json_ok()

@app.get('/api/tickets')
def tickets(user=Depends(authorized)):
    with connect() as con:
        return scope_records(user,rows(con,'''SELECT k.*,r.code room_code,p.name property_name,r.property_id
                           FROM tickets k JOIN rooms r ON r.id=k.room_id
                           JOIN properties p ON p.id=r.property_id ORDER BY
                           CASE k.status WHEN 'new' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END,
                           CASE k.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,k.id DESC'''))

def ticket_values(data):
    return dict(room_id=positive(data.get('room_id'),'Phòng',1),
                title=trim(data.get('title'),'tiêu đề',160,True),
                category=enum(data.get('category','other'),'Danh mục',
                              ['electric','water','internet','furniture','other']),
                priority=enum(data.get('priority','medium'),'Ưu tiên',['low','medium','high']),
                status=enum(data.get('status','new'),'Trạng thái',['new','in_progress','done']),
                description=trim(data.get('description'),'mô tả',1000),
                reported_at=date_str(data.get('reported_at'),'Ngày báo'))

@app.post('/api/tickets')
def add_ticket(data:dict,user=Depends(authorized)):
    vals=ticket_values(data)
    vals['resolved_at'] = date.today().isoformat() if vals['status']=='done' else None
    with tx() as con:
        exists(con,'rooms',vals['room_id'])
        ident=insert(con,'tickets',vals)
        audit(con,user,'create','ticket',ident)
    return json_ok(id=ident)

@app.put('/api/tickets/{ident}')
def edit_ticket(ident:int,data:dict,user=Depends(authorized)):
    vals=ticket_values(data)
    with tx() as con:
        old=one(con,'SELECT * FROM tickets WHERE id=?',(ident,))
        if not old: fail('Không tìm thấy sự cố.',404)
        if old.get('reported_by_tenant_id') and vals['room_id']!=old['room_id']:
            fail('Không thể thay đổi phòng của yêu cầu do khách thuê gửi.',409)
        vals['resolved_at']=(old['resolved_at'] or date.today().isoformat()) if vals['status']=='done' else None
        update(con,'tickets',ident,vals)
        audit(con,user,'update','ticket',ident)
        if old['status']!=vals['status']:
            from .notify import enqueue_ticket_tenant
            enqueue_ticket_tenant(con,ident,old['status'])
    return json_ok()

@app.delete('/api/tickets/{ident}')
def delete_ticket(ident:int,user=Depends(authorized)):
    from . import tenant_portal
    with tx() as con:
        attachments=rows(con,'SELECT file_name FROM ticket_photos WHERE ticket_id=?',(ident,))
        con.execute("UPDATE zalo_outbox SET status='failed',error='Yêu cầu đã được xóa' WHERE ticket_id=? AND status='pending'",(ident,))
        cur=con.execute('DELETE FROM tickets WHERE id=?',(ident,))
        if not cur.rowcount: fail('Không tìm thấy sự cố.',404)
        audit(con,user,'delete','ticket',ident)
    for a in attachments:(tenant_portal.UPLOADS/a['file_name']).unlink(missing_ok=True)
    return json_ok()

def rent_advance_cash(con,period,property_ids=None):
    # Actual cash movement on receipt/refund dates, not accrual invoice revenue.
    params=[period]
    where=''
    if property_ids is not None:
        if not property_ids:return 0
        where=' AND r.property_id IN ('+','.join('?' for _ in property_ids)+')'
        params+=list(property_ids)
    received=one(con,'''SELECT COALESCE(SUM(b.total),0) n FROM rent_prepayment_batches b
        JOIN contracts c ON c.id=b.contract_id JOIN rooms r ON r.id=c.room_id
        WHERE substr(b.paid_on,1,7)=?'''+where,tuple(params))['n']
    refunds=one(con,'''SELECT COALESCE(SUM(x.amount),0) n FROM rent_coverage x
        JOIN contracts c ON c.id=x.contract_id JOIN rooms r ON r.id=c.room_id
        WHERE x.status='refunded' AND substr(x.refunded_on,1,7)=?'''+where,tuple(params))['n']
    return received-refunds

def scoped_dashboard(user):
    grants=user['grant_ids'];q=','.join('?' for _ in grants)
    current=date.today().strftime('%Y-%m')
    with connect() as con:
        stats=one(con,f'''SELECT COUNT(*) rooms_total,
             SUM(CASE WHEN EXISTS(SELECT 1 FROM contracts c WHERE c.room_id=r.id AND c.status='active') THEN 1 ELSE 0 END) occupied
             FROM rooms r WHERE r.property_id IN ({q})''',grants)
        billed=one(con,f"SELECT COALESCE(SUM(i.total),0) n FROM invoices i JOIN rooms r ON r.id=i.room_id WHERE i.period=? AND i.status='published' AND r.property_id IN ({q})",(current,*grants))['n']
        income=one(con,f'''SELECT COALESCE(SUM(pay.amount),0) n FROM payments pay JOIN invoices i ON i.id=pay.invoice_id
            JOIN rooms r ON r.id=i.room_id WHERE substr(pay.paid_at,1,7)=? AND r.property_id IN ({q})''',(current,*grants))['n']
        income+=rent_advance_cash(con,current,grants)
        expense=one(con,f"SELECT COALESCE(SUM(amount),0) n FROM expenses WHERE substr(spent_on,1,7)=? AND property_id IN ({q})",(current,*grants))['n']
        prop=rows(con,f"SELECT p.id,p.name,COUNT(r.id) total FROM properties p LEFT JOIN rooms r ON r.property_id=p.id WHERE p.id IN ({q}) GROUP BY p.id",grants)
        return {'rooms_total':stats['rooms_total'],'occupied':stats['occupied'] or 0,'maintenance':0,
             'open_tickets':0,'expiring':0,'overdue':0,'billed':billed,'invoice_paid':income,
             'cash_in':income,'cash_out':expense,'recent_payments':[],
             'properties':prop,'alerts':[],'trends':[],'period':current}


def scoped_reports(period,grants):
    q=','.join('?' for _ in grants)
    with connect() as con:
        inv=rows(con,INVOICE_SQL+f" WHERE i.period=? AND i.status='published' AND r.property_id IN ({q})",(period,*grants))
        pay=rows(con,f'''SELECT pay.amount FROM payments pay JOIN invoices i ON i.id=pay.invoice_id
        JOIN rooms r ON r.id=i.room_id WHERE substr(pay.paid_at,1,7)=? AND r.property_id IN ({q})''',(period,*grants))
        expenses=rows(con,f'SELECT amount,category FROM expenses WHERE substr(spent_on,1,7)=? AND property_id IN ({q})',(period,*grants))
        rent_cash=rent_advance_cash(con,period,grants)
    categories=defaultdict(int)
    for item in expenses:categories[item['category']]+=item['amount']
    return {'period':period,'billed':sum(x['total'] for x in inv),'paid_for_period':sum(x['paid'] for x in inv),
         'remaining':sum(x['balance'] for x in inv),'cash_in':sum(x['amount'] for x in pay)+rent_cash,
         'cash_out':sum(x['amount'] for x in expenses),'net_cashflow':sum(x['amount'] for x in pay)+rent_cash-sum(x['amount'] for x in expenses),
         'invoice_count':len(inv),'unpaid_count':sum(x['balance']>0 for x in inv),
         'expenses_by_category':[{'category':k,'amount':v} for k,v in categories.items()],'invoices':inv}

@app.get('/api/dashboard')
def dashboard(user=Depends(authorized)):
    if user.get('grant_ids') and user['role']!='admin':
        return scoped_dashboard(user)
    current=date.today().strftime('%Y-%m')
    today=date.today().isoformat()
    with connect() as con:
        rooms_stat=one(con,'''SELECT COUNT(*) rooms_total,
            SUM(CASE WHEN EXISTS(SELECT 1 FROM contracts c WHERE c.room_id=r.id AND c.status='active') THEN 1 ELSE 0 END) occupied,
            SUM(CASE WHEN r.condition='maintenance' THEN 1 ELSE 0 END) maintenance
            FROM rooms r''')
        finance=one(con,'''SELECT COALESCE(SUM(total),0) billed,
            COALESCE(SUM((SELECT COALESCE(SUM(amount),0) FROM payments pay WHERE pay.invoice_id=i.id)),0) paid
            FROM invoices i WHERE period=? AND i.status='published' ''',(current,))
        cash=one(con,'SELECT COALESCE(SUM(amount),0) income FROM payments WHERE substr(paid_at,1,7)=?',(current,))
        cash['income']+=rent_advance_cash(con,current)
        ex=one(con,'SELECT COALESCE(SUM(amount),0) amount FROM expenses WHERE substr(spent_on,1,7)=?',(current,))
        counts=one(con,'''SELECT
             (SELECT COUNT(*) FROM tickets WHERE status!='done') open_tickets,
             (SELECT COUNT(*) FROM contracts WHERE status='active' AND end_date BETWEEN ? AND ?) expiring,
             (SELECT COUNT(*) FROM invoices i WHERE i.status='published' AND due_date<? AND total>
                  (SELECT COALESCE(SUM(amount),0) FROM payments WHERE invoice_id=i.id)) overdue''',
                (today,(date.today()+timedelta(days=30)).isoformat(),today))
        recent=rows(con,'''SELECT p.id,p.amount,p.paid_at,r.code room_code,t.full_name tenant_name,t.phone tenant_phone,t.id_number tenant_id_number,t.photo_path tenant_photo_path,prop.name property_name
                          FROM payments p JOIN invoices i ON i.id=p.invoice_id
                          JOIN contracts c ON c.id=i.contract_id JOIN rooms r ON r.id=i.room_id
                          JOIN properties prop ON prop.id=r.property_id JOIN tenants t ON t.id=c.tenant_id
                          ORDER BY p.paid_at DESC,p.id DESC LIMIT 5''')
        property_stats=rows(con,'''SELECT p.id,p.name,COUNT(r.id) total,
                  SUM(CASE WHEN EXISTS(SELECT 1 FROM contracts c WHERE c.room_id=r.id AND c.status='active') THEN 1 ELSE 0 END) occupied
                  FROM properties p LEFT JOIN rooms r ON r.property_id=p.id GROUP BY p.id ORDER BY p.id''')
        alerts=rows(con,'''SELECT c.id,c.end_date,r.code room_code,t.full_name tenant_name,t.phone tenant_phone,t.id_number tenant_id_number,t.photo_path tenant_photo_path,p.name property_name
                           FROM contracts c JOIN rooms r ON r.id=c.room_id JOIN properties p ON p.id=r.property_id
                           JOIN tenants t ON t.id=c.tenant_id
                           WHERE c.status='active' AND c.end_date<=? ORDER BY c.end_date LIMIT 5''',
                    ((date.today()+timedelta(days=30)).isoformat(),))
        trends=[]
        y,m=date.today().year,date.today().month
        for step in range(5,-1,-1):
            yy=y;mm=m-step
            while mm<=0: mm+=12; yy-=1
            key=f'{yy:04d}-{mm:02d}'
            income=one(con,'SELECT COALESCE(SUM(amount),0) s FROM payments WHERE substr(paid_at,1,7)=?',(key,))['s']
            income+=rent_advance_cash(con,key)
            spend=one(con,'SELECT COALESCE(SUM(amount),0) s FROM expenses WHERE substr(spent_on,1,7)=?',(key,))['s']
            trends.append({'period':key,'income':income,'expense':spend})
    return {**rooms_stat,**counts,'billed':finance['billed'],'invoice_paid':finance['paid'],
            'cash_in':cash['income'],'cash_out':ex['amount'],'recent_payments':recent,
            'properties':property_stats,'alerts':alerts,'trends':trends,'period':current}

@app.get('/api/reports')
def reports(period:str,property_id:int|None=None,user=Depends(authorized)):
    period=period_str(period)
    grants=user.get('grant_ids',[])
    if grants and user['role']!='admin':
        if property_id and property_id not in grants: fail('Không có quyền xem báo cáo cơ sở này.',403)
        if not property_id: return scoped_reports(period,grants)
    with connect() as con:
        invwhere=" WHERE i.period=? AND i.status='published'"
        invparams=[period]
        if property_id:
            invwhere+=' AND r.property_id=?'; invparams.append(property_id)
        invoices=rows(con,INVOICE_SQL+invwhere,tuple(invparams))
        payments_sql='''SELECT pay.* FROM payments pay JOIN invoices i ON i.id=pay.invoice_id
                         JOIN rooms r ON r.id=i.room_id WHERE substr(pay.paid_at,1,7)=?'''
        expenses_sql='SELECT * FROM expenses WHERE substr(spent_on,1,7)=?'
        params=[period]
        if property_id:
            payments_sql+=' AND r.property_id=?'; expenses_sql+=' AND property_id=?';params.append(property_id)
        pay=rows(con,payments_sql,tuple(params))
        expenses=rows(con,expenses_sql,tuple(params))
        rent_cash=rent_advance_cash(con,period,[property_id] if property_id else None)
        categories=defaultdict(int)
        for item in expenses: categories[item['category']]+=item['amount']
        due=sum(x['balance'] for x in invoices)
        return {'period':period,'billed':sum(x['total'] for x in invoices),
                'paid_for_period':sum(x['paid'] for x in invoices),
                'remaining':due,'cash_in':sum(x['amount'] for x in pay)+rent_cash,
                'cash_out':sum(x['amount'] for x in expenses),
                'net_cashflow':sum(x['amount'] for x in pay)+rent_cash-sum(x['amount'] for x in expenses),
                'invoice_count':len(invoices),'unpaid_count':sum(x['balance']>0 for x in invoices),
                'expenses_by_category':[{'category':k,'amount':v} for k,v in categories.items()],
                'invoices':invoices}

@app.get('/api/users')
def users(user=Depends(admin_user)):
    with connect() as con:
        return rows(con,'SELECT id,username,full_name,role,active,created_at FROM users ORDER BY id')

@app.post('/api/users')
def create_user(data:dict,user=Depends(admin_user)):
    username=trim(data.get('username'),'tên đăng nhập',40,True)
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',username): fail('Tên đăng nhập không hợp lệ.')
    pw=data.get('password','');strong_password(pw)
    vals=dict(username=username,full_name=trim(data.get('full_name'),'họ tên',120,True),
              password_hash=password_hash(pw),role=enum(data.get('role','staff'),'vai trò',['staff','admin']))
    try:
        with tx() as con:
            ident=insert(con,'users',vals)
            audit(con,user,'create','user',ident)
    except sqlite3.IntegrityError as exc:
        integrity(exc)
    return json_ok(id=ident)

@app.put('/api/users/{ident}')
def edit_user(ident:int,data:dict,user=Depends(admin_user)):
    role=enum(data.get('role'),'vai trò',['admin','staff'])
    active=1 if data.get('active') in (True,1,'1','true') else 0
    name=trim(data.get('full_name'),'họ tên',120,True)
    pw=data.get('password','')
    with tx() as con:
        old=one(con,'SELECT * FROM users WHERE id=?',(ident,))
        if not old: fail('Không tìm thấy người dùng.',404)
        if ident==user['id'] and (not active or role!='admin'):
            fail('Không thể tự khóa hoặc hạ quyền tài khoản đang đăng nhập.')
        if old['role']=='admin' and (not active or role!='admin'):
            count=one(con,"SELECT COUNT(*) n FROM users WHERE role='admin' AND active=1")['n']
            if count<=1: fail('Phải duy trì ít nhất một quản trị viên hoạt động.')
        values=dict(role=role,active=active,full_name=name)
        if pw:
            strong_password(pw);values['password_hash']=password_hash(pw)
        update(con,'users',ident,values)
        if pw or not active or old['role']!=role:
            con.execute('DELETE FROM sessions WHERE user_id=?',(ident,))
        audit(con,user,'update','user',ident)
    return json_ok()

@app.get('/api/audit')
def audits(user=Depends(admin_user)):
    with connect() as con:
        return rows(con,'''SELECT a.*,u.full_name actor FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id
                           ORDER BY a.id DESC LIMIT 100''')

EXPORT_QUERIES={
 'properties':'SELECT * FROM properties ORDER BY id',
 'rooms':ROOM_SQL+' ORDER BY r.id',
 'tenants':TENANT_SQL+' ORDER BY t.id',
 'contracts':CONTRACT_SQL+' ORDER BY c.id',
 'readings':READING_SQL+' ORDER BY d.id',
 'invoices':INVOICE_SQL+' ORDER BY i.id',
 'payments':'''SELECT * FROM payments ORDER BY id''',
 'expenses':'SELECT * FROM expenses ORDER BY id',
 'tickets':'SELECT * FROM tickets ORDER BY id',
}
@app.get('/api/export/{entity}')
def export_csv(entity:str,user=Depends(authorized)):
    if user['role']!='admin' and not user['permissions'].get(entity+'.view',False):
        fail('Chưa được cấp quyền xem dữ liệu để xuất.',403)
    if entity not in EXPORT_QUERIES: fail('Không hỗ trợ loại xuất này.',404)
    with connect() as con: data=rows(con,EXPORT_QUERIES[entity])
    output=io.StringIO()
    if data:
        writer=csv.DictWriter(output,fieldnames=list(data[0]),extrasaction='ignore')
        writer.writeheader()
        # Spreadsheet formula injection hardening for user-supplied text.
        for record in data:
            writer.writerow({k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v)
                             for k,v in record.items()})
    return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="troflow-{entity}-{date.today().isoformat()}.csv"'})

@app.get('/api/backup')
def backup(user=Depends(admin_user)):
    # SQLite online backup creates a consistent snapshot even while WAL is active.
    fd,path=tempfile.mkstemp(prefix='troflow-',suffix='.sqlite3');os.close(fd)
    try:
        src=connect(); dest=sqlite3.connect(path)
        try: src.backup(dest)
        finally: dest.close();src.close()
        with open(path,'rb') as f: data=f.read()
    finally:
        os.unlink(path)
    return Response(data,media_type='application/octet-stream',
           headers={'Content-Disposition':f'attachment; filename="troflow-backup-{date.today().isoformat()}.sqlite3"',
                    'Cache-Control':'no-store'})

@app.get('/integrations')
def integration_page():
    return FileResponse(STATIC/'integrations.html',headers={'Cache-Control':'no-cache'})

@app.get('/')
def root():
    return FileResponse(STATIC/'index.html',headers={'Cache-Control':'no-cache'})

app.mount('/static',StaticFiles(directory=STATIC),name='static')

from .advanced import router as advanced_router, advanced_page
app.include_router(advanced_router)
app.add_api_route("/advanced", advanced_page, methods=["GET"], include_in_schema=False)

from .prepayments import router as prepayments_router
app.include_router(prepayments_router)

from .utility import router as utility_router
app.include_router(utility_router)

from .notify import router as notify_router
app.include_router(notify_router)

# Isolated tenant session and owner portal. Tenant routes never depend on staff sessions.
from .tenant_portal import router as tenant_portal_router
app.include_router(tenant_portal_router)

from .repairs import router as repairs_router
app.include_router(repairs_router)

from .home_assistant import router as ha_router
app.include_router(ha_router)
