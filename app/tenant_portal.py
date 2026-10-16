"""Tenant-only auth boundary and meter submission review. No staff API re-use."""
import hashlib
import hmac
import io
import os
import re
import secrets
import time
import unicodedata
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse, Response as RawResponse
from PIL import Image, ImageOps

from .db import connect, tx, one, rows
from .main import (COOKIE_SECURE, PUBLIC_MODE, admin_user, authorized, audit,
                   check_password, fail, password_hash, trim, period_str)

router = APIRouter()
PORTAL_COOKIE = '__Host-troflow_tenant' if PUBLIC_MODE else 'troflow_tenant'
UPLOADS = Path(os.getenv('UPLOAD_DIRECTORY','/app/uploads'))


def slug(value):
    value = unicodedata.normalize('NFKD', str(value or '').replace('đ','d').replace('Đ','D'))
    value = ''.join(c for c in value if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+','',value)


def default_password(tenant, property_name):
    name=slug(tenant['full_name'].split()[-1] if tenant['full_name'].split() else '')
    prop=slug(property_name)
    if not name or not prop:fail('Tên người thuê và cơ sở phải có ký tự chữ/số để tạo mật khẩu.')
    return name+'_'+prop


def provision(con, tenant_id, property_id, enabled, actor):
    """Admin controlled tenant provision; creating credentials returns secrets only once."""
    t=one(con,'SELECT id,full_name,phone FROM tenants WHERE id=?',(tenant_id,))
    p=one(con,'SELECT id,name FROM properties WHERE id=?',(property_id,))
    if not t or not p:fail('Khách thuê hoặc cơ sở không tồn tại.',404)
    other=one(con,'''SELECT r.property_id FROM contracts c JOIN rooms r ON r.id=c.room_id
        WHERE c.tenant_id=? AND c.status='active' AND r.property_id<>? LIMIT 1''',(tenant_id,property_id))
    if other:fail('Cơ sở đã chọn không khớp với hợp đồng đang hiệu lực của khách thuê.',409)
    phone=re.sub(r'[^0-9+]','',t['phone'])
    if not re.fullmatch(r'\+?[0-9]{9,15}',phone):fail('Số điện thoại đăng nhập phải hợp lệ.')
    conflict=one(con,'SELECT tenant_id FROM tenant_portal_accounts WHERE username=? AND tenant_id<>?',(phone,tenant_id))
    if conflict:fail('Số điện thoại đã được dùng làm tài khoản của khách thuê khác.',409)
    old=one(con,'SELECT * FROM tenant_portal_accounts WHERE tenant_id=?',(tenant_id,))
    if old:
        con.execute('UPDATE tenant_portal_accounts SET username=?,property_id=?,enabled=? WHERE tenant_id=?',
                    (phone,property_id,int(bool(enabled)),tenant_id))
        if not enabled or old['username']!=phone or old['property_id']!=property_id:
            con.execute('DELETE FROM tenant_portal_sessions WHERE tenant_id=?',(tenant_id,))
        audit(con,actor,'update','tenant_portal',tenant_id,'Thay đổi trạng thái / phạm vi tài khoản khách thuê')
        return None
    if not enabled:return None
    password=default_password(t,p['name'])
    # Public sign-in requires a second unpredictable secret to offset predictable passwords.
    access_code=secrets.token_urlsafe(18)
    con.execute('''INSERT INTO tenant_portal_accounts(tenant_id,property_id,username,password_hash,access_code_hash,enabled)
                   VALUES(?,?,?,?,?,1)''',(tenant_id,property_id,phone,password_hash(password),password_hash(access_code)))
    audit(con,actor,'create','tenant_portal',tenant_id)
    return {'username':phone,'password':password,'access_code':access_code}


def session_tenant(request:Request):
    token=request.cookies.get(PORTAL_COOKIE,'')
    if not token or len(token)>200:fail('Vui lòng đăng nhập tài khoản khách thuê.',401)
    key=hashlib.sha256(token.encode()).hexdigest()
    with connect() as con:
        t=one(con,'''SELECT a.tenant_id,a.property_id,a.username,t.full_name,t.phone,t.email,p.name property_name,s.csrf_token
        FROM tenant_portal_sessions s JOIN tenant_portal_accounts a ON a.tenant_id=s.tenant_id
        JOIN tenants t ON t.id=a.tenant_id JOIN properties p ON p.id=a.property_id
        WHERE s.token_hash=? AND s.expires_at>? AND a.enabled=1''',(key,datetime.now(timezone.utc).isoformat()))
    if not t:fail('Phiên khách thuê không hợp lệ hoặc đã bị vô hiệu hóa.',401)
    return t


def csrf_tenant(request:Request,t=Depends(session_tenant)):
    if request.method in ('POST','PUT','PATCH','DELETE'):
        value=request.headers.get('x-csrf-token','')
        if not value or not hmac.compare_digest(value,t['csrf_token']):fail('Mã bảo vệ phiên không hợp lệ.',403)
    return t


def _client_ip(request):
    # Do not trust user-supplied X-Forwarded-For.
    return request.client.host if request.client else 'unknown'

@router.post('/api/tenant/auth/login')
def tenant_login(data:dict,request:Request,response:Response):
    phone=re.sub(r'[^0-9+]','',str(data.get('phone','')))[:25]
    passwd=str(data.get('password',''))[:200]
    second=str(data.get('access_code',''))[:200]
    username_key=hashlib.sha256(('tenant:'+phone).encode()).hexdigest()
    ip_key=hashlib.sha256(('tenant:'+_client_ip(request)).encode()).hexdigest()
    now=int(time.time())
    with tx() as con:
        con.execute('DELETE FROM auth_failures WHERE at<?',(now-900,))
        tries=one(con,'SELECT COUNT(*) n FROM auth_failures WHERE username_hash=?',(username_key,))['n']
        iptries=one(con,'SELECT COUNT(*) n FROM auth_failures WHERE ip_hash=?',(ip_key,))['n']
        if tries>=5 or iptries>=60:fail('Đăng nhập quá nhiều lần, hãy thử lại sau 15 phút.',429)
        rec=one(con,'SELECT * FROM tenant_portal_accounts WHERE username=? AND enabled=1',(phone,))
    # Hash dummy password as well, to reduce user enumeration timing.
    from .main import DUMMY_PASSWORD_HASH
    pw_ok=check_password(passwd,rec['password_hash'] if rec else DUMMY_PASSWORD_HASH)
    code_ok=(not PUBLIC_MODE or (rec is not None and check_password(second,rec['access_code_hash'])))
    if not rec or not pw_ok or not code_ok:
        with tx() as con:con.execute('INSERT INTO auth_failures(ip_hash,username_hash,at) VALUES(?,?,?)',(ip_key,username_key,now))
        fail('Thông tin đăng nhập không đúng.',401)
    token=secrets.token_urlsafe(48);csrf=secrets.token_urlsafe(32)
    expiry=(datetime.now(timezone.utc)+timedelta(hours=6)).isoformat()
    with tx() as con:
        con.execute('DELETE FROM auth_failures WHERE username_hash=? AND ip_hash=?',(username_key,ip_key))
        con.execute('DELETE FROM tenant_portal_sessions WHERE tenant_id=?',(rec['tenant_id'],))
        con.execute('INSERT INTO tenant_portal_sessions(token_hash,tenant_id,csrf_token,expires_at) VALUES(?,?,?,?)',
                    (hashlib.sha256(token.encode()).hexdigest(),rec['tenant_id'],csrf,expiry))
    response.set_cookie(PORTAL_COOKIE,token,httponly=True,samesite='strict',secure=COOKIE_SECURE,path='/',max_age=21600)
    return {'ok':True,'csrf':csrf}

@router.get('/api/tenant/auth/me')
def tenant_me(t=Depends(session_tenant)):
    return {'tenant':{'name':t['full_name'],'phone':t['phone'],'property':t['property_name']},'csrf':t['csrf_token'],
            'requires_access_code':PUBLIC_MODE}

@router.post('/api/tenant/auth/logout')
def tenant_logout(request:Request,response:Response,t=Depends(csrf_tenant)):
    with tx() as con:
        con.execute('DELETE FROM tenant_portal_sessions WHERE token_hash=?',(hashlib.sha256(request.cookies[PORTAL_COOKIE].encode()).hexdigest(),))
    response.delete_cookie(PORTAL_COOKIE,path='/')
    return {'ok':True}


def mine(con,t):
    return rows(con,'''SELECT c.id contract_id,c.room_id,c.start_date,c.end_date,c.monthly_rent,
                   c.deposit,c.due_day,p.electric_rate,p.water_rate,p.service_fee,
                   r.code room_code,p.name property_name
                   FROM contracts c JOIN rooms r ON r.id=c.room_id JOIN properties p ON p.id=r.property_id
                   WHERE c.tenant_id=? AND r.property_id=? AND c.status='active' ORDER BY c.id DESC''',
                (t['tenant_id'],t['property_id']))


def owner_public(con,prop):
    profile=one(con,'SELECT * FROM owner_profiles WHERE property_id=?',(prop,))
    if not profile:return None
    result={}
    for key in ('name','gender','age','address','phone','email'):
        if profile.get('show_'+key):result[key]=profile.get(key)
    if profile.get('show_photo') and profile.get('photo_path'):
        result['photo_url']='/api/tenant/owner/photo'
    return result

@router.get('/api/tenant/home')
def tenant_home(t=Depends(session_tenant)):
    with connect() as con:
        contracts=mine(con,t)
        ids=[x['contract_id'] for x in contracts]
        invoices=[];readings=[];prepayments=[]
        if ids:
            placeholders=','.join('?' for _ in ids)
            invoices=rows(con,f'''SELECT i.id,i.contract_id,i.period,i.total,i.rent,i.electricity,i.water,i.services,
               i.adjustment,i.electric_usage,i.water_usage,i.status,i.created_at,i.utility_period,
               COALESCE((SELECT SUM(amount) FROM payments WHERE invoice_id=i.id),0) paid
               FROM invoices i WHERE i.contract_id IN ({placeholders}) AND i.status='published' ORDER BY i.period DESC,i.id DESC LIMIT 100''',ids)
            readings=rows(con,f'''SELECT d.period,d.electric_old,d.electric_new,d.water_old,d.water_new,
               c.id contract_id,r.code room_code
               FROM readings d JOIN contracts c ON c.room_id=d.room_id
               JOIN rooms r ON r.id=d.room_id
               WHERE c.id IN ({placeholders}) AND d.period||'-01'<=c.end_date AND
                  date(d.period||'-01','+1 month','-1 day')>=c.start_date
               ORDER BY d.period DESC LIMIT 100''',ids)
            # Scope rent coverage to contracts verified by mine(). Refunded periods
            # remain visible in the receipt history but are not counted as active.
            coverage=rows(con,f'''SELECT x.contract_id,x.batch_id,x.period,x.amount,x.status,
               b.paid_on,b.method,b.total batch_total
               FROM rent_coverage x JOIN rent_prepayment_batches b ON b.id=x.batch_id
               WHERE x.contract_id IN ({placeholders})
               ORDER BY b.paid_on DESC,b.id DESC,x.period ASC''',ids)
            batches={}
            room_codes={c['contract_id']:c['room_code'] for c in contracts}
            for x in coverage:
                key=x['batch_id']
                if key not in batches:
                    batch={'batch_id':key,'contract_id':x['contract_id'],
                           'room_code':room_codes[x['contract_id']],
                           'paid_on':x['paid_on'],'method':x['method'],
                           'total_paid':x['batch_total'],'active_amount':0,
                           'refunded_amount':0,'periods':[]}
                    batches[key]=batch
                    prepayments.append(batch)
                batch=batches[key]
                batch['periods'].append({'period':x['period'],'amount':x['amount'],
                                         'status':x['status']})
                if x['status']=='active':
                    batch['active_amount']+=x['amount']
                else:
                    batch['refunded_amount']+=x['amount']
        submissions=rows(con,'''SELECT s.id,s.contract_id,s.period,s.electric_new,s.water_new,s.status,s.feedback,
                               s.created_at FROM tenant_meter_submissions s
                               WHERE s.tenant_id=? AND s.property_id=? ORDER BY s.id DESC LIMIT 50''',
                               (t['tenant_id'],t['property_id']))
        return {'tenant':{'name':t['full_name'],'phone':t['phone'],'property':t['property_name']},
                'contracts':contracts,'invoices':invoices,'readings':readings,
                'prepayments':prepayments,'submissions':submissions,
                'owner':owner_public(con,t['property_id'])}


def check_period_contract(con,t,contract_id,period):
    c=one(con,'''SELECT c.id,c.room_id,c.start_date,c.end_date,r.property_id
      FROM contracts c JOIN rooms r ON r.id=c.room_id
      WHERE c.id=? AND c.tenant_id=? AND r.property_id=? AND c.status='active' ''',
      (contract_id,t['tenant_id'],t['property_id']))
    if not c:fail('Không tìm thấy hợp đồng được phép.',404)
    first=period+'-01'
    y,m=map(int,period.split('-'));last=(date(y+(m==12),m%12+1,1)-timedelta(days=1)).isoformat()
    if first>c['end_date'] or last<c['start_date']:fail('Kỳ này nằm ngoài thời hạn thuê.',403)
    # Accept current or previous calendar month only, avoiding backdated tampering.
    current=date.today().replace(day=1)
    prev=(current-timedelta(days=1)).replace(day=1)
    if period not in (current.strftime('%Y-%m'),prev.strftime('%Y-%m')):
        fail('Chỉ được gửi kỳ hiện tại hoặc kỳ liền trước.',400)
    return c


def clean_image(file):
    contents=file.file.read(3*1024*1024+1)
    if len(contents)>3*1024*1024 or len(contents)<24:fail('Ảnh phải nhỏ hơn 3 MB.',400)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contents)) as src:
                if src.format not in ('JPEG','PNG','WEBP') or src.width*src.height>12_000_000:
                    fail('Ảnh hoặc kích thước không được hỗ trợ.')
                src.load()
                img=ImageOps.exif_transpose(src).convert('RGB')
                out=io.BytesIO();img.save(out,format='JPEG',quality=85,optimize=True)
                return out.getvalue()
    except (OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        fail('Tệp ảnh không hợp lệ.')


def previous_reading(con,room_id,period):
    return one(con,'SELECT electric_new,water_new,period FROM readings WHERE room_id=? AND period<? ORDER BY period DESC LIMIT 1',(room_id,period))

@router.post('/api/tenant/readings/submit')
async def tenant_submit(request:Request,contract_id:int=Form(...),period:str=Form(...),
                        electric_new:float=Form(...),water_new:float=Form(...),
                        electric_photo:UploadFile=File(...),water_photo:UploadFile=File(...),
                        t=Depends(csrf_tenant)):
    period=period_str(period)
    if not (0<=electric_new<=1e8 and 0<=water_new<=1e8):fail('Chỉ số không hợp lệ.')
    a=clean_image(electric_photo);b=clean_image(water_photo)
    files=[]
    try:
        with tx() as con:
            c=check_period_contract(con,t,contract_id,period)
            if one(con,'SELECT id FROM readings WHERE room_id=? AND period=?',(c['room_id'],period)):
                fail('Kỳ này đã có chỉ số chính thức.',409)
            from .billing import locked_reading
            if locked_reading(con,c['room_id'],period):
                fail('Kỳ này đã được lập hóa đơn.',409)
            prev=previous_reading(con,c['room_id'],period)
            if not prev:fail('Chưa có chỉ số kỳ trước. Vui lòng yêu cầu quản lý thiết lập số đầu kỳ.',409)
            if electric_new<prev['electric_new'] or water_new<prev['water_new']:
                fail('Chỉ số mới không được nhỏ hơn chỉ số kỳ trước.')
            existing=one(con,'SELECT id,status FROM tenant_meter_submissions WHERE contract_id=? AND period=?',(contract_id,period))
            if existing and existing['status'] in ('pending','approved'):
                fail('Đã gửi chỉ số kỳ này, hãy đợi quản lý duyệt.',409)
            UPLOADS.mkdir(parents=True,exist_ok=True)
            for content in (a,b):
                name=secrets.token_hex(20)+'.jpg';path=UPLOADS/name
                with open(path,'xb') as f:f.write(content)
                os.chmod(path,0o600);files.append(name)
            if existing:
                con.execute('''UPDATE tenant_meter_submissions SET electric_old=?,water_old=?,electric_new=?,water_new=?,
                  electric_photo=?,water_photo=?,status='pending',feedback='',created_at=CURRENT_TIMESTAMP,reviewed_by=NULL,reviewed_at=NULL
                  WHERE id=?''',(prev['electric_new'],prev['water_new'],electric_new,water_new,*files,existing['id']))
                ident=existing['id']
            else:
                ident=con.execute('''INSERT INTO tenant_meter_submissions
                   (tenant_id,property_id,contract_id,room_id,period,electric_old,electric_new,water_old,water_new,electric_photo,water_photo)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(t['tenant_id'],t['property_id'],contract_id,c['room_id'],period,
                   prev['electric_new'],electric_new,prev['water_new'],water_new,*files)).lastrowid
            from .notify import enqueue_meter_submission
            enqueue_meter_submission(con,ident)
        return {'ok':True,'id':ident,'status':'pending'}
    except Exception:
        for name in files:
            (UPLOADS/name).unlink(missing_ok=True)
        raise

@router.get('/api/tenant/admin/submissions')
def admin_submissions(user=Depends(authorized)):
    if user['role']!='admin' and not user['permissions'].get('readings.view',False):fail('Không đủ quyền.',403)
    with connect() as con:
        out=rows(con,'''SELECT s.id,s.tenant_id,s.property_id,s.contract_id,s.room_id,s.period,s.status,
          s.electric_old,s.electric_new,s.water_old,s.water_new,s.feedback,s.created_at,
          t.full_name tenant_name,t.phone,r.code room_code,p.name property_name
          FROM tenant_meter_submissions s JOIN tenants t ON t.id=s.tenant_id
          JOIN rooms r ON r.id=s.room_id JOIN properties p ON p.id=s.property_id ORDER BY s.id DESC LIMIT 500''')
        return [x for x in out if user['role']=='admin' or x['property_id'] in user['grant_ids']]

@router.post('/api/tenant/admin/submissions/{ident}/review')
def admin_review(ident:int,data:dict,user=Depends(authorized)):
    if user['role']!='admin' and not user['permissions'].get('readings.record',False):fail('Không đủ quyền duyệt.',403)
    decision=data.get('decision')
    if decision not in ('approve','reject'):fail('Quyết định không hợp lệ.')
    feedback=trim(data.get('feedback'),'Ghi chú',500)
    with tx() as con:
        s=one(con,'SELECT * FROM tenant_meter_submissions WHERE id=?',(ident,))
        if not s:fail('Không tìm thấy đề nghị.',404)
        if user['role']!='admin' and s['property_id'] not in user['grant_ids']:fail('Sai phạm vi cơ sở.',403)
        if s['status']!='pending':fail('Đề nghị đã được xử lý.',409)
        if decision=='approve':
            # Check ownership and contract dates again when approving (even if changed after submission).
            check_period_contract(con,{'tenant_id':s['tenant_id'],'property_id':s['property_id']},s['contract_id'],s['period'])
            # Check ownership remains bound to the active contract (no stale approval).
            contract=one(con,'SELECT status,tenant_id,room_id FROM contracts WHERE id=?',(s['contract_id'],))
            if not contract or contract['status']!='active' or contract['tenant_id']!=s['tenant_id'] or contract['room_id']!=s['room_id']:
                fail('Hợp đồng không còn hợp lệ.',409)
            if one(con,'SELECT id FROM readings WHERE room_id=? AND period=?',(s['room_id'],s['period'])):
                fail('Chỉ số chính thức kỳ này đã tồn tại.',409)
            from .billing import locked_reading
            if locked_reading(con,s['room_id'],s['period']):
                fail('Hóa đơn kỳ này đã lập, không thể tự duyệt.',409)
            prev=previous_reading(con,s['room_id'],s['period'])
            if not prev or s['electric_new']<prev['electric_new'] or s['water_new']<prev['water_new']:
                fail('Chỉ số trước đã thay đổi hoặc dữ liệu không hợp lệ.',409)
            con.execute('''INSERT INTO readings(room_id,period,electric_old,electric_new,water_old,water_new,electric_photo,water_photo)
              VALUES(?,?,?,?,?,?,?,?)''',(s['room_id'],s['period'],prev['electric_new'],s['electric_new'],
              prev['water_new'],s['water_new'],s['electric_photo'],s['water_photo']))
        con.execute('''UPDATE tenant_meter_submissions SET status=?,feedback=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP
                        WHERE id=?''',('approved' if decision=='approve' else 'rejected',feedback,user['id'],ident))
        audit(con,user,decision,'tenant_meter_submission',ident)
    return {'ok':True}

@router.get('/api/tenant/submissions/{ident}/photo/{kind}')
def tenant_photo(ident:int,kind:str,t=Depends(session_tenant)):
    if kind not in ('electric','water'):fail('Ảnh không tồn tại.',404)
    with connect() as con:
        s=one(con,'SELECT electric_photo,water_photo FROM tenant_meter_submissions WHERE id=? AND tenant_id=? AND property_id=?',
              (ident,t['tenant_id'],t['property_id']))
    if not s:fail('Ảnh không tồn tại.',404)
    return serve_photo(s[kind+'_photo'])

@router.get('/api/tenant/admin/submissions/{ident}/photo/{kind}')
def admin_photo(ident:int,kind:str,user=Depends(authorized)):
    if kind not in ('electric','water'):fail('Ảnh không tồn tại.',404)
    if user['role']!='admin' and not user['permissions'].get('readings.view',False):fail('Không đủ quyền.',403)
    with connect() as con:
        s=one(con,'SELECT property_id,electric_photo,water_photo FROM tenant_meter_submissions WHERE id=?',(ident,))
    if not s or (user['role']!='admin' and s['property_id'] not in user['grant_ids']):fail('Ảnh không tồn tại.',404)
    return serve_photo(s[kind+'_photo'])


def serve_photo(name):
    if not name or not re.fullmatch(r'[0-9a-f]{40}\.jpg',name):fail('Ảnh không tồn tại.',404)
    path=UPLOADS/name
    if not path.is_file():fail('Ảnh không tồn tại.',404)
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.get('/api/tenant/admin/owner/{property_id}')
def owner_detail(property_id:int,user=Depends(admin_user)):
    with connect() as con:
        if not one(con,'SELECT id FROM properties WHERE id=?',(property_id,)):fail('Cơ sở không tồn tại.',404)
        return one(con,'SELECT * FROM owner_profiles WHERE property_id=?',(property_id,)) or {'property_id':property_id}

@router.put('/api/tenant/admin/owner/{property_id}')
def owner_update(property_id:int,data:dict,user=Depends(admin_user)):
    with tx() as con:
        if not one(con,'SELECT id FROM properties WHERE id=?',(property_id,)):fail('Cơ sở không tồn tại.',404)
        values={'name':trim(data.get('name'),'Họ tên',120),
                'gender':trim(data.get('gender'),'Giới tính',24),
                'age':data.get('age'), 'address':trim(data.get('address'),'Địa chỉ',250),
                'phone':trim(data.get('phone'),'Số điện thoại',30),
                'email':trim(data.get('email'),'Email',120)}
        if values['age'] in (None,''):values['age']=None
        else:
            try:values['age']=int(values['age'])
            except (ValueError,TypeError):fail('Tuổi không hợp lệ.')
            if not 18<=values['age']<=120:fail('Tuổi không hợp lệ.')
        for k in ('name','gender','age','address','phone','email','photo'):
            values['show_'+k]=int(data.get('show_'+k,False) in (True,1,'1','true','on'))
        columns=list(values)
        con.execute('''INSERT INTO owner_profiles(property_id,'''+','.join(columns)+''') VALUES ('''+','.join('?' for _ in range(len(columns)+1))+''') ON CONFLICT(property_id)
                 DO UPDATE SET '''+','.join(k+'=excluded.'+k for k in columns),(property_id,*values.values()))
        audit(con,user,'update','owner_profile',property_id)
    return {'ok':True}

@router.post('/api/tenant/admin/owner/{property_id}/photo')
async def owner_upload(property_id:int,file:UploadFile=File(...),user=Depends(admin_user)):
    content=clean_image(file)
    with tx() as con:
        if not one(con,'SELECT id FROM properties WHERE id=?',(property_id,)):fail('Cơ sở không tồn tại.',404)
        UPLOADS.mkdir(parents=True,exist_ok=True)
        name=secrets.token_hex(20)+'.jpg'
        with open(UPLOADS/name,'xb') as fh:fh.write(content)
        os.chmod(UPLOADS/name,0o600)
        con.execute('INSERT OR IGNORE INTO owner_profiles(property_id) VALUES(?)',(property_id,))
        con.execute('UPDATE owner_profiles SET photo_path=? WHERE property_id=?',(name,property_id))
        audit(con,user,'upload','owner_photo',property_id)
    return {'ok':True}

@router.get('/api/tenant/owner/photo')
def tenant_owner_photo(t=Depends(session_tenant)):
    with connect() as con:
        rec=one(con,'SELECT photo_path FROM owner_profiles WHERE property_id=? AND show_photo=1',(t['property_id'],))
    if not rec:fail('Ảnh không tồn tại.',404)
    return serve_photo(rec['photo_path'])

@router.get('/api/tenant/admin/owner/{property_id}/photo')
def admin_owner_photo(property_id:int,user=Depends(admin_user)):
    with connect() as con:rec=one(con,'SELECT photo_path FROM owner_profiles WHERE property_id=?',(property_id,))
    if not rec:fail('Ảnh không tồn tại.',404)
    return serve_photo(rec['photo_path'])

@router.post('/api/tenant/admin/accounts/{tenant_id}/reset')
def reset_tenant(tenant_id:int,user=Depends(admin_user)):
    with tx() as con:
        a=one(con,'SELECT * FROM tenant_portal_accounts WHERE tenant_id=?',(tenant_id,))
        if not a:fail('Tài khoản chưa được cấp.',404)
        t=one(con,'SELECT full_name FROM tenants WHERE id=?',(tenant_id,))
        p=one(con,'SELECT name FROM properties WHERE id=?',(a['property_id'],))
        password=default_password(t,p['name']);code=secrets.token_urlsafe(18)
        con.execute('UPDATE tenant_portal_accounts SET password_hash=?,access_code_hash=? WHERE tenant_id=?',
                    (password_hash(password),password_hash(code),tenant_id))
        con.execute('DELETE FROM tenant_portal_sessions WHERE tenant_id=?',(tenant_id,))
        audit(con,user,'reset','tenant_portal',tenant_id)
    return {'username':a['username'],'password':password,'access_code':code}

@router.get('/tenant')
def tenant_page():
    return FileResponse(Path(__file__).parent/'static'/'tenant.html',headers={'Cache-Control':'no-store'})
