"""TroFlow bank accounts + Zalo Bot Server integration (user-provided zca-js bridge).

Credentials live in an owner-readable file, not returned through API or stored in SQLite.
The sending worker runs after the transaction commits; failures are visible in the outbox.
"""
import io
import json
import os
import re
import secrets
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from .db import connect, tx, one, rows
from . import bank_catalog
from .invoice_format import transfer_reference, invoice_lines, utility_rate, service_rows
from . import db as dbmodule
from .main import authorized, admin_user, trim, positive, fail, audit

router=APIRouter()


def _admin(user):
    if user['role']!='admin':fail('Chỉ quản trị viên được cấu hình tích hợp.',403)


def _setting(con):
    item=one(con,'SELECT * FROM zalo_config WHERE id=1')
    return item or {'enabled':0,'invoice_enabled':0,'payment_enabled':0,'ticket_enabled':0,'reading_enabled':1,'bot_url':'http://host.docker.internal:3000','account_selection':'','media_url':''}


def _secret_file():
    return dbmodule.DB_PATH.parent/'zalo-integration-credentials.json'


def _credential_cipher():
    from cryptography.fernet import Fernet
    filename=os.getenv('TROFLOW_SECRET_KEY_FILE','/run/secrets/troflow_integration_key')
    path=Path(filename)
    try:
        return Fernet(path.read_bytes().strip())
    except (OSError,ValueError) as exc:
        from .main import PUBLIC_MODE
        if PUBLIC_MODE:
            raise RuntimeError('Chế độ Internet cần khóa bí mật hợp lệ tại TROFLOW_SECRET_KEY_FILE.') from exc
        return None


def _credentials():
    username=os.getenv('ZALO_BOT_USERNAME','').strip()
    password=os.getenv('ZALO_BOT_PASSWORD','')
    if username and password:return username,password
    path=_secret_file()
    if path.is_file():
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            cipher=_credential_cipher()
            if 'encrypted' in data:
                if cipher is None:
                    raise RuntimeError('Cần cung cấp khóa mã hóa để đọc mật khẩu bot.')
                from cryptography.fernet import InvalidToken
                try:
                    password=cipher.decrypt(data['encrypted'].encode()).decode('utf-8')
                except (InvalidToken,ValueError) as exc:
                    raise RuntimeError('Không thể giải mã thông tin Zalo Bot; kiểm tra khóa bí mật.') from exc
                return data.get('username',''),password
            # Migrate plaintext credentials from V5.4 without losing their contents.
            if cipher:
                _save_credentials(data.get('username',''),data.get('password',''))
            return data.get('username',''),data.get('password','')
        except (OSError,ValueError):pass
    return '', ''


def _save_credentials(username,password):
    path=_secret_file()
    cipher=_credential_cipher()
    if cipher:
        payload={'username':username,'encrypted':cipher.encrypt(password.encode('utf-8')).decode('ascii')}
    else:
        payload={'username':username,'password':password}
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name('.zalo-creds-'+secrets.token_hex(8))
    try:
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(payload,out)
        os.replace(tmp,path)
        os.chmod(path,0o600)
    finally:
        if tmp.exists():tmp.unlink()


def _network_base(url,field):
    url=trim(url,field,250,True).rstrip('/')
    u=urllib.parse.urlsplit(url)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.path not in ('','/') or u.query or u.fragment:
        fail(field+' cần là http(s)://hostname:port, không kèm đường dẫn.')
    # Restrict HTTP endpoints to local/private addresses. Do not allow arbitrary public URLs
    # as credentials are sent to /api/login.
    import ipaddress
    host=u.hostname.lower()
    private=host in ('localhost','host.docker.internal') or host.endswith('.internal') or host.endswith('.local')
    try:private=private or ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:pass
    if u.scheme!='https' and not private:
        fail(field+' chỉ được dùng HTTP trên mạng nội bộ; máy chủ công khai cần HTTPS.')
    return url


def _bank_payload(con,property_id):
    return one(con,'''SELECT * FROM bank_accounts WHERE property_id=? AND active=1 ORDER BY is_default DESC,id ASC LIMIT 1''',(property_id,))


def _qr_details(con,invoice_id):
    invoice=one(con,'''SELECT i.id,i.period,i.total,r.property_id,p.name property_name,
           t.full_name tenant_name,t.phone tenant_phone,r.code room_code
           FROM invoices i JOIN rooms r ON r.id=i.room_id
           JOIN properties p ON p.id=r.property_id JOIN contracts c ON c.id=i.contract_id
           JOIN tenants t ON t.id=c.tenant_id WHERE i.id=?''',(invoice_id,))
    if not invoice:fail('Không tìm thấy hóa đơn.',404)
    bank=_bank_payload(con,invoice['property_id'])
    if not bank:return {'configured':False,'invoice_id':invoice_id}
    paid=one(con,'SELECT COALESCE(SUM(amount),0) value FROM payments WHERE invoice_id=?',(invoice_id,))['value']
    balance=max(0,invoice['total']-paid)
    note=transfer_reference(invoice)
    query=urllib.parse.urlencode({'amount':balance,'addInfo':note,'accountName':bank['holder']})
    # The image is generated by VietQR; payment is not automatically confirmed.
    code=urllib.parse.quote(bank['bank_code'],safe='')
    account=urllib.parse.quote(bank['account_number'],safe='')
    return {'configured':True,'invoice_id':invoice_id,'bank_name':bank['bank_name'],
            'bank_code':bank['bank_code'],'account_number':bank['account_number'],'holder':bank['holder'],
            'amount':balance,'content':note,'qr_url':f'https://img.vietqr.io/image/{code}-{account}-compact2.png?{query}'}


@router.get('/api/v6/bank-catalog')
def vietqr_banks(user=Depends(admin_user)):
    return bank_catalog.get_catalog()


@router.post('/api/v6/bank-catalog/refresh')
def refresh_vietqr_banks(user=Depends(admin_user)):
    try:
        return bank_catalog.refresh_catalog()
    except (ValueError, OSError, TimeoutError) as exc:
        fail('Không thể cập nhật từ VietQR. Danh sách tích hợp sẵn vẫn dùng được. ' + str(exc), 502)


@router.get('/api/v6/banks')
def banks(user=Depends(admin_user)):
    with connect() as con:
        return rows(con,'SELECT b.*,p.name property_name FROM bank_accounts b JOIN properties p ON p.id=b.property_id ORDER BY b.property_id,b.is_default DESC,b.id')


def _bank_values(data):
    prop=positive(data.get('property_id'),'Cơ sở',1)
    bank_code=trim(data.get('bank_code'),'Mã ngân hàng',20,True).upper()
    bank_name=trim(data.get('bank_name'),'Tên ngân hàng',120,True)
    # Only newly selected catalog items require authoritative BIN/name pairing.
    # Legacy/manual records can still be edited without changing their bank details.
    chosen=trim(data.get('catalog_bin'),'Ngân hàng đã chọn',20)
    if chosen and chosen!='manual':
        match=next((b for b in bank_catalog.get_catalog()['banks'] if b['bin']==chosen),None)
        if not match or bank_code!=chosen:
            fail('Mã BIN không khớp ngân hàng đã chọn.')
        bank_name=match['shortName']
    holder=trim(data.get('holder'),'Chủ tài khoản',120,True)
    account_number=trim(data.get('account_number'),'Số tài khoản',34,True)
    if not re.fullmatch(r'[A-Z0-9]{2,20}',bank_code):fail('Mã BIN/ngân hàng chỉ có chữ và số.')
    if not re.fullmatch(r'[0-9A-Za-z]{4,34}',account_number):fail('Số tài khoản gồm 4–34 ký tự chữ/số.')
    return {'property_id':prop,'bank_code':bank_code,'bank_name':bank_name,'holder':holder,
            'account_number':account_number,'is_default':int(bool(data.get('is_default',0))),
            'active':int(bool(data.get('active',1)))}


def _save_bank(con,values,ident=None):
    if not one(con,'SELECT id FROM properties WHERE id=?',(values['property_id'],)):fail('Không tìm thấy cơ sở.',404)
    dup=one(con,'SELECT id FROM bank_accounts WHERE property_id=? AND bank_code=? AND account_number=? AND id<>?',
            (values['property_id'],values['bank_code'],values['account_number'],ident or -1))
    if dup:fail('Tài khoản ngân hàng đã tồn tại ở cơ sở này.',409)
    if values['is_default']:
        con.execute('UPDATE bank_accounts SET is_default=0 WHERE property_id=?',(values['property_id'],))
    if ident:
        cur=con.execute('''UPDATE bank_accounts SET property_id=:property_id,bank_code=:bank_code,
            bank_name=:bank_name,holder=:holder,account_number=:account_number,is_default=:is_default,
            active=:active WHERE id=:id''',{**values,'id':ident})
        if not cur.rowcount:fail('Không tìm thấy tài khoản ngân hàng.',404)
    else:
        cur=con.execute('''INSERT INTO bank_accounts(property_id,bank_code,bank_name,holder,account_number,is_default,active)
            VALUES (:property_id,:bank_code,:bank_name,:holder,:account_number,:is_default,:active)''',values)
        ident=cur.lastrowid
    if not one(con,'SELECT id FROM bank_accounts WHERE property_id=? AND active=1 AND is_default=1',(values['property_id'],)):
        con.execute('UPDATE bank_accounts SET is_default=1 WHERE id=(SELECT id FROM bank_accounts WHERE property_id=? AND active=1 ORDER BY id LIMIT 1)',(values['property_id'],))
    return ident


@router.post('/api/v6/banks')
def create_bank(data:dict,user=Depends(admin_user)):
    values=_bank_values(data)
    with tx() as con:
        ident=_save_bank(con,values);audit(con,user,'create','bank_account',ident)
    return {'id':ident}


@router.put('/api/v6/banks/{ident}')
def edit_bank(ident:int,data:dict,user=Depends(admin_user)):
    values=_bank_values(data)
    with tx() as con:
        if not one(con,'SELECT id FROM bank_accounts WHERE id=?',(ident,)):fail('Không tìm thấy tài khoản.',404)
        ident=_save_bank(con,values,ident);audit(con,user,'update','bank_account',ident)
    return {'id':ident}


@router.delete('/api/v6/banks/{ident}')
def delete_bank(ident:int,user=Depends(admin_user)):
    with tx() as con:
        old=one(con,'SELECT * FROM bank_accounts WHERE id=?',(ident,))
        if not old:fail('Không tìm thấy tài khoản.',404)
        con.execute('DELETE FROM bank_accounts WHERE id=?',(ident,))
        if old['is_default']:
            con.execute('UPDATE bank_accounts SET is_default=1 WHERE id=(SELECT id FROM bank_accounts WHERE property_id=? AND active=1 ORDER BY id LIMIT 1)',(old['property_id'],))
        audit(con,user,'delete','bank_account',ident)
    return {'ok':True}


@router.get('/api/v6/invoices/{ident}/payment-qr')
def invoice_bank(ident:int,user=Depends(authorized)):
    if user['role']!='admin' and not user['permissions'].get('invoices.view'):
        fail('Không được xem hóa đơn.',403)
    with connect() as con:
        from .main import scope_records
        records=scope_records(user,rows(con,'''SELECT i.id,r.property_id FROM invoices i JOIN rooms r ON r.id=i.room_id WHERE i.id=?''',(ident,)))
        if not records:fail('Không có quyền xem hóa đơn này.',403)
        return _qr_details(con,ident)


@router.get('/api/v6/zalo/settings')
def zalo_settings(user=Depends(admin_user)):
    with connect() as con:item=_setting(con)
    username,password=_credentials()
    return {**item,'credentials_configured':bool(username and password),'username':username,
            'environment_credentials':bool(os.getenv('ZALO_BOT_USERNAME') and os.getenv('ZALO_BOT_PASSWORD'))}


@router.put('/api/v6/zalo/settings')
def update_zalo_settings(data:dict,user=Depends(admin_user)):
    bot_url=_network_base(data.get('bot_url'),'Địa chỉ Zalo Bot Server')
    media_url=_network_base(data.get('media_url'),'Địa chỉ TrọFlow cho Zalo tải ảnh')
    selection=trim(data.get('account_selection'),'Tài khoản Zalo (ownId hoặc số điện thoại)',60,True)
    username=trim(data.get('username'),'Tài khoản quản trị bot',80)
    password=data.get('password','')
    if password and (not isinstance(password,str) or len(password)>256):fail('Mật khẩu không hợp lệ.')
    old_user,old_pass=_credentials()
    if password:
        if not username:fail('Nhập tên đăng nhập bot.')
        _save_credentials(username,password)
    elif username and username != old_user:
        fail('Khi đổi tên đăng nhập, cần nhập mật khẩu mới.')
    with tx() as con:
        con.execute('''INSERT INTO zalo_config(id,enabled,invoice_enabled,payment_enabled,ticket_enabled,reading_enabled,bot_url,account_selection,media_url)
         VALUES(1,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled,
         invoice_enabled=excluded.invoice_enabled,payment_enabled=excluded.payment_enabled,
         ticket_enabled=excluded.ticket_enabled,reading_enabled=excluded.reading_enabled,bot_url=excluded.bot_url,
         account_selection=excluded.account_selection,media_url=excluded.media_url''',
         (int(bool(data.get('enabled'))),int(bool(data.get('invoice_enabled'))),
          int(bool(data.get('payment_enabled'))),int(bool(data.get('ticket_enabled'))),int(bool(data.get('reading_enabled',_setting(con).get('reading_enabled',1)))),bot_url,selection,media_url))
        audit(con,user,'update','zalo_config',1)
    # Saving settings must not pretend the Bot API was reached. Check using a new session.
    return {'ok':True,'connection':_connection_status()}


@router.get('/api/v6/zalo/connection')
def zalo_connection(user=Depends(admin_user)):
    return _connection_status()


@router.get('/api/v6/zalo/destinations')
def destinations(user=Depends(admin_user)):
    with connect() as con:
        return rows(con,'''SELECT d.*,t.full_name tenant_name,p.name property_name
          ,(SELECT o.status FROM zalo_outbox o WHERE o.destination_id=d.id
            AND o.event='destination_welcome' ORDER BY o.id DESC LIMIT 1) welcome_status
          FROM zalo_destinations d LEFT JOIN tenants t ON t.id=d.tenant_id
          LEFT JOIN properties p ON p.id=d.property_id ORDER BY d.id DESC''')


def _destination_values(con,data):
    values={'name':trim(data.get('name'),'Tên nơi nhận',120,True),
            'thread_id':trim(data.get('thread_id'),'Zalo UserID/GroupID',60,True),
            'kind':trim(data.get('kind'),'Loại nơi nhận',10,True),
            'property_id':positive(data['property_id'],'Cơ sở',1) if data.get('property_id') else None,
            'tenant_id':positive(data['tenant_id'],'Khách thuê',1) if data.get('tenant_id') else None,
            'enabled':int(bool(data.get('enabled',1))),
            'on_invoice':int(bool(data.get('on_invoice',1))),
            'on_payment':int(bool(data.get('on_payment',1))),
            'on_ticket':int(bool(data.get('on_ticket',0))),
            'on_ticket_tenant':int(bool(data.get('on_ticket_tenant',0))),
            'on_meter_submission':int(bool(data.get('on_meter_submission',0)))}
    if values['kind'] not in ('user','group'):fail('Loại nơi nhận phải là user hoặc group.')
    if values['on_ticket_tenant'] and values['kind']=='group':
        fail('Tin sửa chữa riêng tư của khách thuê chỉ gửi tới Zalo User, không gửi nhóm.',400)
    if values['on_ticket_tenant'] and not values['tenant_id']:
        fail('Thông báo sửa chữa cho khách chỉ có thể chọn với Zalo liên kết khách thuê.',400)
    if values['on_meter_submission'] and values['tenant_id']:
        fail('Nơi nhận chỉ số của khách phải là nơi nhận chủ nhà.',400)
    if values['on_ticket'] and values['tenant_id']:
        fail('Nơi nhận thông báo sửa chữa của chủ nhà không được gắn với khách thuê.',400)
    if not re.fullmatch(r'[0-9]{5,24}',values['thread_id']):fail('ID Zalo phải là chuỗi số từ 5–24 ký tự.')
    if values['tenant_id'] and not one(con,'SELECT id FROM tenants WHERE id=?',(values['tenant_id'],)):
        fail('Khách thuê không tồn tại.',404)
    if values['property_id'] and not one(con,'SELECT id FROM properties WHERE id=?',(values['property_id'],)):
        fail('Cơ sở không tồn tại.',404)
    return values


def _welcome_message(values):
    subscribed=[]
    if values['on_invoice']:subscribed.append('Hóa đơn')
    if values['on_payment']:subscribed.append('Thanh toán')
    if values['on_ticket']:subscribed.append('Yêu cầu sửa chữa gửi chủ')
    if values['on_ticket_tenant']:subscribed.append('Tiến độ sửa chữa của tôi')
    if values['on_meter_submission']:subscribed.append('Chỉ số khách gửi chờ duyệt')
    description=', '.join(subscribed) if subscribed else 'Chưa chọn loại thông báo tự động'
    return (f'TRỌFLOW - XÁC NHẬN NƠI NHẬN\n'
            f'Xin chào {values["name"]}!\n'
            'Zalo này đã được thêm vào danh sách nơi nhận của hệ thống quản lý nhà trọ TrọFlow.\n'
            f'Loại: {"Nhóm Zalo" if values["kind"]=="group" else "Người dùng Zalo"}\n'
            f'Nhận thông báo: {description}.\n'
            'Đây là tin nhắn xác nhận tự động. Nếu không đồng ý nhận tin, '
            'vui lòng liên hệ người quản lý nhà trọ.')


@router.post('/api/v6/zalo/destinations')
def create_destination(data:dict,background_tasks:BackgroundTasks,user=Depends(admin_user)):
    with tx() as con:
        values=_destination_values(con,data)
        cur=con.execute('''INSERT INTO zalo_destinations(name,thread_id,kind,property_id,tenant_id,enabled,on_invoice,on_payment,on_ticket,on_ticket_tenant,on_meter_submission)
          VALUES(:name,:thread_id,:kind,:property_id,:tenant_id,:enabled,:on_invoice,:on_payment,:on_ticket,:on_ticket_tenant,:on_meter_submission)''',values)
        dest_id=cur.lastrowid
        notification_id=None
        welcome_status='skipped'
        if values['enabled']:
            config=_setting(con)
            welcome_status='pending' if config['enabled'] else 'failed'
            error='' if config['enabled'] else 'Chưa bật kênh Zalo. Bật kênh rồi chọn Gửi lại.'
            note=con.execute('''INSERT INTO zalo_outbox(destination_id,event,event_key,message,status,error)
                 VALUES(?,'destination_welcome',?,?,?,?)''',
                (dest_id,f'destination_welcome:{dest_id}',_welcome_message(values),welcome_status,error))
            notification_id=note.lastrowid
        audit(con,user,'create','zalo_destination',dest_id)
    # The database is already committed; a failing Zalo request never loses the new recipient.
    # BackgroundTasks immediately attempts just this one message, not the full pending queue.
    if welcome_status=='pending':
        background_tasks.add_task(process_outbox,1,[notification_id])
    return {'id':dest_id,'welcome_notification_id':notification_id,'welcome_status':welcome_status}


@router.put('/api/v6/zalo/destinations/{ident}')
def edit_destination(ident:int,data:dict,user=Depends(admin_user)):
    with tx() as con:
        values=_destination_values(con,data)
        cur=con.execute('''UPDATE zalo_destinations SET name=:name,thread_id=:thread_id,kind=:kind,
          property_id=:property_id,tenant_id=:tenant_id,enabled=:enabled,on_invoice=:on_invoice,
          on_payment=:on_payment,on_ticket=:on_ticket,on_ticket_tenant=:on_ticket_tenant,
          on_meter_submission=:on_meter_submission WHERE id=:id''',{**values,'id':ident})
        if not cur.rowcount:fail('Không có nơi nhận.',404)
        audit(con,user,'update','zalo_destination',ident)
    return {'ok':True}


@router.delete('/api/v6/zalo/destinations/{ident}')
def delete_destination(ident:int,user=Depends(admin_user)):
    with tx() as con:
        cur=con.execute('DELETE FROM zalo_destinations WHERE id=?',(ident,))
        if not cur.rowcount:fail('Không có nơi nhận.',404)
        audit(con,user,'delete','zalo_destination',ident)
    return {'ok':True}


def _invoice(con,invoice_id):
    return one(con,'''SELECT i.*,r.property_id,r.code room_code,p.name property_name,
       t.id tenant_id,t.full_name tenant_name,t.phone tenant_phone,
       d.electric_old,d.electric_new,d.water_old,d.water_new,
       COALESCE((SELECT SUM(amount) FROM payments pay WHERE pay.invoice_id=i.id),0) paid
       FROM invoices i JOIN rooms r ON r.id=i.room_id JOIN properties p ON p.id=r.property_id
       JOIN contracts c ON c.id=i.contract_id JOIN tenants t ON t.id=c.tenant_id
       LEFT JOIN readings d ON d.room_id=i.room_id AND d.period=i.period
       WHERE i.id=?''',(invoice_id,))


def enqueue_invoice_event(con,invoice_id,event):
    """Call INSIDE business transaction; outbox sends only after commit."""
    if event not in ('invoice','payment'):return
    setting=_setting(con)
    if not setting.get('enabled') or not setting.get(event+'_enabled'):return
    inv=_invoice(con,invoice_id)
    if not inv:return
    for dest in rows(con,'''SELECT * FROM zalo_destinations WHERE enabled=1 AND
      (property_id IS NULL OR property_id=?) AND (tenant_id IS NULL OR tenant_id=?) AND '''+
      ('on_invoice=1' if event=='invoice' else 'on_payment=1'),(inv['property_id'],inv['tenant_id'])):
        paid=inv['paid']
        status='ĐÃ THANH TOÁN' if paid>=inv['total'] else 'ĐÃ NHẬN THANH TOÁN' if event=='payment' else 'HÓA ĐƠN CẦN THANH TOÁN'
        msg=f'{status}\n{inv["property_name"]} · Phòng {inv["room_code"]}\nKhách: {inv["tenant_name"]}\nKỳ: {inv["period"]}\nTổng: {inv["total"]:,.0f} đ\nĐã thu: {paid:,.0f} đ\nCòn lại: {max(0,inv["total"]-paid):,.0f} đ'
        # Send each distinct payment once; duplicate webhook/repeated admin clicks are harmless.
        key=f'{event}:{invoice_id}:'+ (str(paid) if event=='payment' else 'published')
        con.execute('''INSERT OR IGNORE INTO zalo_outbox(destination_id,invoice_id,event,event_key,message,status)
          VALUES(?,?,?,?,?,'pending')''',(dest['id'],invoice_id,event,key,msg))


def enqueue_ticket_event(con, ticket_id):
    """Enqueue after a tenant creates the ticket, inside the same transaction.

    Owner-only destinations require tenant_id NULL, so a contact for another
    renter can never receive this tenant's repair details.
    """
    config=_setting(con)
    if not config.get('enabled') or not config.get('ticket_enabled'):
        return 0
    t=one(con,'''SELECT k.*,r.code room_code,r.property_id,p.name property_name,
             t.full_name tenant_name,t.phone tenant_phone
             FROM tickets k JOIN rooms r ON r.id=k.room_id
             JOIN properties p ON p.id=r.property_id
             JOIN tenants t ON t.id=k.reported_by_tenant_id WHERE k.id=?''',(ticket_id,))
    if not t:return 0
    category={'electric':'Điện','water':'Nước','internet':'Internet','furniture':'Nội thất','other':'Khác'}
    priority={'low':'Thấp','medium':'Trung bình','high':'Cao'}
    status={'new':'Mới tiếp nhận','in_progress':'Đang xử lý','done':'Đã hoàn thành'}
    photos=one(con,'SELECT COUNT(*) n FROM ticket_photos WHERE ticket_id=?',(ticket_id,))['n']
    message=(f'YÊU CẦU SỬA CHỮA MỚI #{ticket_id}\n'
       f'Cơ sở: {t["property_name"]}\nPhòng: {t["room_code"]}\n'
       f'Khách thuê: {t["tenant_name"]}\nSĐT: {t["tenant_phone"]}\n'
       f'Loại sự cố: {category.get(t["category"],t["category"])}\n'
       f'Tiêu đề: {t["title"]}\nMức ưu tiên: {priority.get(t["priority"],t["priority"])}\n'
       f'Tiến độ: {status.get(t["status"],t["status"])}\nNgày báo: {t["reported_at"]}\n'
       f'Nội dung: {t["description"] or "Không có"}\nSố ảnh: {photos}')
    destinations=rows(con,'''SELECT * FROM zalo_destinations WHERE enabled=1 AND on_ticket=1
       AND tenant_id IS NULL AND (property_id IS NULL OR property_id=?)''',(t['property_id'],))
    for d in destinations:
        con.execute('''INSERT OR IGNORE INTO zalo_outbox
          (destination_id,ticket_id,event,event_key,message,status)
          VALUES(?,?,'ticket',?,?,'pending')''',
          (d['id'],ticket_id,f'ticket:{ticket_id}',message[:1800]))
    return len(destinations)



def enqueue_ticket_tenant(con,ticket_id,status_before=None):
    """Notify only linked tenant's own repair, at creation and real status changes."""
    config=_setting(con)
    if not config.get('enabled') or not config.get('ticket_enabled'):return 0
    ticket=one(con,"""SELECT k.id,k.reported_by_tenant_id,k.status,k.title,k.description,
      r.code room_code,r.property_id FROM tickets k JOIN rooms r ON r.id=k.room_id WHERE k.id=?""",(ticket_id,))
    if not ticket or not ticket['reported_by_tenant_id']:return 0
    statuses={'new':'Đã tiếp nhận','in_progress':'Đang xử lý','done':'Đã hoàn thành'}
    msg=(f'TRỌFLOW - YÊU CẦU SỬA CHỮA #{ticket_id}\n'
       f'Phòng: {ticket["room_code"]}\nTiêu đề: {ticket["title"]}\n'
       f'Trạng thái: {statuses.get(ticket["status"],ticket["status"])}\n'
       f'Nội dung: {ticket["description"] or "Không có"}\n'
       'Bạn có thể theo dõi yêu cầu tại Cổng khách thuê.')
    key=('ticket_tenant:'+str(ticket_id)+':created' if status_before is None else
         'ticket_tenant:'+str(ticket_id)+':status:'+datetime.now(timezone.utc).isoformat())
    dests=rows(con,"""SELECT id FROM zalo_destinations WHERE enabled=1 AND on_ticket_tenant=1
       AND tenant_id=? AND (property_id IS NULL OR property_id=?)""",
       (ticket['reported_by_tenant_id'],ticket['property_id']))
    for d in dests:
        con.execute("""INSERT OR IGNORE INTO zalo_outbox(destination_id,ticket_id,event,event_key,message,status)
           VALUES(?,?,'ticket_tenant',?,?,'pending')""",(d['id'],ticket_id,key,msg[:1800]))
    return len(dests)


def enqueue_meter_submission(con, submission_id):
    """Notify owner destinations of the new reading submission awaiting review."""
    cfg=_setting(con)
    if not cfg.get('enabled') or not cfg.get('reading_enabled'):return 0
    reading=one(con,"""SELECT s.*,t.full_name tenant_name,r.code room_code,p.name property_name
       FROM tenant_meter_submissions s JOIN tenants t ON t.id=s.tenant_id
       JOIN rooms r ON r.id=s.room_id JOIN properties p ON p.id=s.property_id WHERE s.id=?""",(submission_id,))
    if not reading or reading['status']!='pending':return 0
    fmt=lambda v:f'{v:,.3f}'.rstrip('0').rstrip('.')
    msg=(f'TRỌFLOW - KHÁCH GỬI CHỈ SỐ ĐIỆN NƯỚC\n'
      f'Cơ sở: {reading["property_name"]} · Phòng: {reading["room_code"]}\n'
      f'Khách: {reading["tenant_name"]}\nKỳ: {reading["period"]}\n'
      f'Điện: {fmt(reading["electric_old"])} → {fmt(reading["electric_new"])} kWh\n'
      f'Nước: {fmt(reading["water_old"])} → {fmt(reading["water_new"])} m³\n'
      'Trạng thái: Chờ quản lý xác nhận. Mở TroFlow → Duyệt chỉ số khách thuê.')
    key=f'meter_submission:{submission_id}:'+datetime.now(timezone.utc).isoformat()
    dests=rows(con,"""SELECT id FROM zalo_destinations WHERE enabled=1 AND tenant_id IS NULL
       AND on_meter_submission=1 AND (property_id IS NULL OR property_id=?)""",(reading['property_id'],))
    for d in dests:
        con.execute("""INSERT OR IGNORE INTO zalo_outbox
         (destination_id,submission_id,event,event_key,message,status)
         VALUES(?,?,'meter_submission',?,?,'pending')""",(d['id'],submission_id,key,msg[:1800]))
    return len(dests)


def _http_json(opener,url,payload,timeout=12):
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
      headers={'Content-Type':'application/json','Accept':'application/json'},method='POST')
    with opener.open(req,timeout=timeout) as resp:
        if resp.status!=200:raise RuntimeError('Bot trả về HTTP '+str(resp.status))
        return json.loads(resp.read(512000).decode('utf-8'))


def _connection_status():
    checked_at=datetime.now(timezone.utc).isoformat(timespec='seconds')
    with connect() as con:config=_setting(con)
    result={'status':'disconnected','connected':False,'checked_at':checked_at,
            'message':'Chưa kiểm tra được kết nối.'}
    if not config.get('bot_url') or not config.get('account_selection'):
        return {**result,'status':'not_configured','message':'Chưa khai báo đầy đủ địa chỉ Bot Server và tài khoản Zalo.'}
    try:
        username,password=_credentials()
    except (OSError,RuntimeError,ValueError):
        return {**result,'status':'credentials_error','message':'Không đọc được thông tin đăng nhập bot. Kiểm tra khóa mã hóa và quyền truy cập.'}
    if not username or not password:
        return {**result,'status':'no_credentials','message':'Chưa nhập username/mật khẩu quản trị Zalo Bot.'}
    try:
        # Credentials stay strictly on the server. No client-side access and no HTTP redirects.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),_NoRedirect())
        logged=_http_json(opener,config['bot_url']+'/api/login',
                         {'username':username,'password':password},timeout=5)
        if not isinstance(logged,dict):
            raise ValueError('Phản hồi bot không phải JSON object.')
        if logged.get('success') is True:
            return {**result,'status':'connected','connected':True,
                    'message':'Đã kết nối và xác thực với Zalo Bot Server. Chưa kiểm chứng gửi tin nhắn đến tài khoản Zalo.'}
        return {**result,'status':'auth_failed','message':'Đã liên lạc với Bot Server nhưng đăng nhập không thành công. Kiểm tra username/mật khẩu bot.'}
    except HTTPError as exc:
        return {**result,'status':'auth_failed' if exc.code in (401,403) else 'server_error',
                'message':('Bot từ chối thông tin đăng nhập.' if exc.code in (401,403)
                           else f'Bot Server trả về HTTP {exc.code}. Kiểm tra API /api/login.')}
    except (URLError,OSError,TimeoutError):
        return {**result,'status':'unreachable',
                'message':'TroFlow không truy cập được Zalo Bot Server. Kiểm tra IP, cổng 3000, firewall và địa chỉ từ container.'}
    except (RuntimeError,ValueError,json.JSONDecodeError):
        return {**result,'status':'server_error',
                'message':'Bot Server phản hồi không đúng giao thức /api/login hoặc chuyển hướng bất thường.'}


def _bot_send(config,dest,msg,image_url=None,image_urls=None):
    username,password=_credentials()
    if not username or not password:raise RuntimeError('Chưa cấu hình tên đăng nhập/mật khẩu bot.')
    cookies=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(cookies),_NoRedirect())
    logged=_http_json(opener,config['bot_url']+'/api/login',{'username':username,'password':password})
    if not logged.get('success'):raise RuntimeError('Đăng nhập Zalo Bot thất bại.')
    params={'accountSelection':str(config['account_selection']),'threadId':str(dest['thread_id']),
            'type':1 if dest['kind']=='group' else 0,'message':msg}
    if image_urls and len(image_urls)>=2:
        if len(image_urls)>5:raise RuntimeError('Album tối đa 5 ảnh.')
        params['imagePaths']=image_urls
        endpoint='/api/sendImagesByAccount'  # Native zca-js album, ONE message.
    else:
        if image_urls and len(image_urls)==1:image_url=image_urls[0]
        if image_url:params['imagePath']=image_url
        endpoint='/api/sendImageByAccount' if image_url else '/api/sendMessageByAccount'
    outcome=_http_json(opener,config['bot_url']+endpoint,params)
    if not outcome.get('success'):raise RuntimeError(str(outcome.get('error') or 'Bot không xác nhận gửi thành công.')[:200])
    if image_urls and len(image_urls)>=2 and outcome.get('deliveryStatus') != 'accepted':
        raise RuntimeError('Bot chỉ xác nhận một phần album. Kiểm tra Zalo trước khi thử gửi lại.')
    return outcome


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise RuntimeError('Bot chuyển hướng không mong muốn (từ chối để bảo vệ tài khoản).')


def _invoice_png(invoice,qr=None,lines=None):
    """Customer-facing bill PNG for manual download AND Zalo.

    Never use current property tariffs for historical invoices.  This renderer
    shares the snapshot details and bank reference with the web/print template.
    """
    from PIL import Image, ImageDraw, ImageFont
    invoice=dict(invoice)
    lines=lines or []
    font_file='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    bold_file='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    def font(size,bold=False):
        return ImageFont.truetype(bold_file if bold else font_file,size)
    W=1080; L=65; R=W-65
    dark='#152b44'; muted='#60758a'; primary='#089b8d'; red='#d84b5c'
    def money(v):return f'{int(round(float(v or 0))):,}'+' đ'
    def meter(v):
        if v is None:return '—'
        return f'{float(v):,.3f}'.rstrip('0').rstrip('.')
    def wrap(draw,text,size,maximum,bold=False):
        result=[]; part=''
        for word in str(text).split():
            next_piece=(part+' '+word).strip()
            if part and draw.textlength(next_piece,font=font(size,bold))>maximum:
                result.append(part);part=word
            else:part=next_piece
        if part:result.append(part)
        return result or ['']
    fee_details=service_rows(invoice,lines)
    item_count=4+len(fee_details)+(1 if invoice.get('adjustment') else 0)
    H=1500+item_count*125+(450 if qr and qr.get('configured') else 0)
    image=Image.new('RGB',(W,H),'white')
    draw=ImageDraw.Draw(image)
    y=58
    def label(text,color=dark,size=25,bold=False,x=L,ypos=None):
        draw.text((x, y if ypos is None else ypos),str(text),font=font(size,bold),fill=color)
    def item(name,value,detail='',height=80):
        nonlocal y
        label(name, size=24,bold=True)
        draw.text((R-draw.textlength(money(value),font=font(26,True)),y),money(value),font=font(26,True),fill=dark)
        y+=37
        if detail:
            for piece in wrap(draw,detail,20,R-L-30):
                label(piece,muted,20,ypos=y);y+=29
        y+=max(21,height-37-(29 if detail else 0))
        draw.line((L,y-13,R,y-13),fill='#e5edf1',width=2)
    label('PHIẾU THU / HÓA ĐƠN NỘI BỘ',primary,22,True)
    paid_for_status=float(invoice.get('paid') or 0);total_for_status=float(invoice.get('total') or 0)
    status=('ĐÃ THANH TOÁN' if paid_for_status>=total_for_status else 'THANH TOÁN MỘT PHẦN' if paid_for_status>0 else 'CHƯA THANH TOÁN')
    color=primary if paid_for_status>=total_for_status else '#b97914' if paid_for_status>0 else red
    draw.text((R-draw.textlength(status,font=font(18,True)),y+7),status,font=font(18,True),fill=color)
    y+=54
    label('HÓA ĐƠN TIỀN PHÒNG',dark,39,True);y+=67
    label(f'{invoice["property_name"]} · Tháng {invoice["period"]} · HD-{invoice["id"]:05d}',muted,21);y+=65
    name=invoice.get('tenant_name') or '—';room=invoice.get('room_code') or '—';phone=invoice.get('tenant_phone') or '—'
    # Stand-out tenant identity panel, expanding for long names.
    identity=wrap(draw,f'Khách thuê: {name}  ·  Phòng: {room}',23,R-L-25,True)
    panel_height=60+len(identity)*34
    draw.rounded_rectangle((L-14,y-15,R+9,y+panel_height),radius=16,fill='#ebf8f5')
    for text in identity:label(text,dark,23,True,ypos=y);y+=34
    label(f'Số điện thoại: {phone}',dark,23,True,ypos=y+10)
    y+=91
    item('Tiền thuê phòng',invoice['rent'])
    for code, title, prefix, unit, amount_key,usage_key,old_key,new_key in [
      ('electric','Tiền điện','Điện','kWh','electricity','electric_usage','electric_old','electric_new'),
      ('water','Tiền nước','Nước','m³','water','water_usage','water_old','water_new')]:
        old=invoice.get(old_key);new=invoice.get(new_key)
        usage=invoice.get(usage_key)
        rate=utility_rate(invoice,lines,code)
        detail=f'Chỉ số: {meter(old)} → {meter(new)}  ·  Tiêu thụ: {meter(usage)} {unit}'
        if rate['rate'] is not None:
            detail+=f'  ·  {"Đơn giá quy đổi" if rate["estimated"] else "Đơn giá"}: {money(rate["rate"])}/{unit}'
        item(title,invoice[amount_key],detail,94)
    if fee_details:
        for fee in fee_details:
            quantity=meter(fee['quantity'])
            item(str(fee['label']),fee['amount'],f'{quantity} × {money(fee["unit_price"])}',92)
    else:
        item('Phí dịch vụ',invoice['services'])
    if invoice.get('adjustment'):item('Điều chỉnh',invoice['adjustment'])
    # High priority balance area.
    y+=12
    draw.rounded_rectangle((L-14,y-10,R+9,y+88),radius=14,fill='#ebf8f5')
    label('TỔNG CỘNG',dark,30,True,ypos=y+15)
    draw.text((R-draw.textlength(money(invoice['total']),font=font(34,True)),y+12),money(invoice['total']),font=font(34,True),fill=dark)
    y+=118
    label('ĐÃ THANH TOÁN',dark,27,True)
    draw.text((R-draw.textlength(money(invoice['paid']),font=font(29,True)),y),money(invoice['paid']),font=font(29,True),fill=primary)
    y+=78
    label('TỔNG TIỀN PHẢI THANH TOÁN',dark,26,True)
    balance=max(0,float(invoice['total'])-float(invoice['paid']))
    draw.text((R-draw.textlength(money(balance),font=font(31,True)),y),money(balance),font=font(31,True),fill=red if balance else primary)
    y+=120
    if qr and qr.get('configured'):
        bx=L+300
        entries=[('Ngân hàng',qr['bank_name']),('Chủ tài khoản',qr['holder']),
                 ('Số tài khoản',qr['account_number']),('Số tiền',money(qr['amount'])),('Nội dung CK',qr['content'])]
        bank_rows=[(label_text,wrap(draw,str(value),16,R-bx-16,True)) for label_text,value in entries]
        height_bank=max(320,55+sum(29+len(chunks)*23 for _,chunks in bank_rows))
        draw.rounded_rectangle((L-14,y-15,R+9,y+height_bank),radius=15,fill='#effaf7')
        label('THANH TOÁN CHUYỂN KHOẢN',primary,24,True,ypos=y)
        next_y=y+45
        for label_text,chunks in bank_rows:
            draw.text((bx,next_y),label_text+':',font=font(16),fill=muted)
            next_y+=21
            for part in chunks:
                draw.text((bx,next_y),part,font=font(16,True),fill=dark)
                next_y+=23
            next_y+=7
        qr_loaded=False
        try:
            with urllib.request.urlopen(qr['qr_url'],timeout=8) as resp:
                if resp.status==200 and resp.headers.get('Content-Type','').startswith('image/'):
                    raw=resp.read(2_000_001)
                    if len(raw)<=2_000_000:
                        small=Image.open(io.BytesIO(raw)).convert('RGB')
                        small.thumbnail((255,255))
                        image.paste(small,(L,y+38));qr_loaded=True
        except (OSError,ValueError,HTTPError,URLError):pass
        if not qr_loaded:
            draw.text((L,y+90),'QR chưa tải được',font=font(19,True),fill=red)
            draw.text((L,y+127),'Dùng thông tin',font=font(16),fill=muted)
            draw.text((L,y+152),'bên phải để CK.',font=font(16),fill=muted)
        y+=height_bank+30
    if invoice.get('note'):
        for item_text in wrap(draw,'Ghi chú: '+str(invoice['note']),19,R-L):
            label(item_text,muted,19,ypos=y);y+=26
    label('Hóa đơn quản lý nội bộ, không thay thế hóa đơn điện tử theo quy định.',muted,17,ypos=y+23)
    y+=75
    # Dynamic crop avoids enormous blank trailing pages for bills with 0 services.
    image=image.crop((0,0,min(W,W),min(H,max(y+40,1080))))
    output=io.BytesIO();image.save(output,format='PNG',optimize=True)
    return output.getvalue()


def queue_manual(con,dest_id,invoice_id,message,include_image=False):
    if not one(con,'SELECT id FROM zalo_destinations WHERE id=?',(dest_id,)):fail('Không có nơi nhận.',404)
    if invoice_id and not _invoice(con,invoice_id):fail('Không có hóa đơn.',404)
    token='manual:'+secrets.token_hex(16)
    cur=con.execute('''INSERT INTO zalo_outbox(destination_id,invoice_id,event,event_key,message,status,include_image)
      VALUES(?,?,?,?,?,'pending',?)''',(dest_id,invoice_id,'manual',token,message,int(include_image)))
    return cur.lastrowid


@router.post('/api/v6/zalo/send')
def send_manual(data:dict,user=Depends(admin_user)):
    with tx() as con:
        config=_setting(con)
        if not config['enabled']:fail('Hãy bật kênh Zalo trong cấu hình trước.',409)
        destination=positive(data.get('destination_id'),'Nơi nhận',1)
        invoice_id=int(data['invoice_id']) if data.get('invoice_id') else None
        text=trim(data.get('message'),'Nội dung thông báo',1800,True)
        ident=queue_manual(con,destination,invoice_id,text,bool(data.get('include_image') and invoice_id))
        audit(con,user,'enqueue','zalo_notification',ident)
    return {'id':ident,'status':'pending'}


@router.get('/api/v6/zalo/outbox')
def outbox(user=Depends(admin_user)):
    with connect() as con:
        return rows(con,'''SELECT o.id,o.destination_id,o.invoice_id,o.event,o.message,o.status,o.attempts,
          o.error,o.created_at,o.sent_at,d.name destination_name
          FROM zalo_outbox o LEFT JOIN zalo_destinations d ON d.id=o.destination_id ORDER BY o.id DESC LIMIT 150''')


@router.get('/api/v6/zalo/outbox/{ident}/status')
def notification_status(ident:int,user=Depends(admin_user)):
    with connect() as con:
        entry=one(con,'SELECT id,event,status,error,sent_at FROM zalo_outbox WHERE id=?',(ident,))
    if not entry:fail('Không tìm thấy thông báo.',404)
    return entry


@router.post('/api/v6/zalo/outbox/{ident}/retry')
def retry(ident:int,user=Depends(admin_user)):
    with tx() as con:
        cur=con.execute("UPDATE zalo_outbox SET status='pending',error='' WHERE id=? AND status='failed'",(ident,))
        if not cur.rowcount:fail('Chỉ có thể gửi lại thông báo thất bại.',409)
        audit(con,user,'retry','zalo_notification',ident)
    return {'ok':True}


def process_outbox(limit=6,only_ids=None):
    """One worker, post-commit; optionally restrict to a known notification ID.

    SQL status compare-and-swap prevents duplicate delivery when the scheduler
    and a request-scoped background task run concurrently.
    """
    with connect() as con:
        config=_setting(con)
        if not config['enabled']:return 0
        if only_ids is not None:
            safe_ids=[int(item) for item in only_ids if int(item)>0][:limit]
            if not safe_ids:return 0
            placeholders=','.join('?' for _ in safe_ids)
            pending=rows(con,f"SELECT id FROM zalo_outbox WHERE status='pending' AND id IN ({placeholders}) ORDER BY id",safe_ids)
        else:
            pending=rows(con,"SELECT id FROM zalo_outbox WHERE status='pending' ORDER BY id LIMIT ?",(limit,))
    count=0
    for entry in pending:
        ident=entry['id']
        with tx() as con:
            cur=con.execute("UPDATE zalo_outbox SET status='sending',attempts=attempts+1 WHERE id=? AND status='pending'",(ident,))
            if not cur.rowcount:continue
            record=one(con,'SELECT * FROM zalo_outbox WHERE id=?',(ident,))
            dest=one(con,'SELECT * FROM zalo_destinations WHERE id=?',(record['destination_id'],))
            config=_setting(con)
        error=''
        try:
            if not config['enabled'] or not dest or not dest['enabled']:
                raise RuntimeError('Kênh hoặc nơi nhận đang tắt.')
            image_url=None
            if record['invoice_id'] and (record['event'] in ('invoice','payment') or record['include_image']):
                with tx() as con:
                    token=secrets.token_urlsafe(32)
                    expire=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
                    con.execute('INSERT INTO notification_media(token,invoice_id,expires_at) VALUES(?,?,?)',(token,record['invoice_id'],expire))
                if not config['media_url']:raise RuntimeError('Chưa cấu hình địa chỉ TroFlow để Zalo tải ảnh.')
                image_url=config['media_url']+'/api/integration-media/'+token
            album_urls=None
            if record.get('event')=='ticket' and record.get('ticket_id'):
                if not config.get('ticket_enabled') or not dest.get('on_ticket') or dest.get('tenant_id'):
                    raise RuntimeError('Đã tắt thông báo sửa chữa hoặc nơi nhận không còn hợp lệ.')
                with tx() as con:
                    ticket=one(con,'SELECT r.property_id FROM tickets k JOIN rooms r ON r.id=k.room_id WHERE k.id=?',(record['ticket_id'],))
                    if not ticket or (dest.get('property_id') is not None and ticket['property_id']!=dest['property_id']):
                        raise RuntimeError('Yêu cầu đã bị xóa hoặc nơi nhận không đúng cơ sở.')
                    photos=rows(con,'SELECT id FROM ticket_photos WHERE ticket_id=? ORDER BY id',(record['ticket_id'],))
                    if photos:
                        if not config.get('media_url'):raise RuntimeError('Chưa thiết lập URL nội bộ để bot tải ảnh.')
                        album_urls=[]
                        expiry=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
                        con.execute('DELETE FROM ticket_media_tokens WHERE expires_at<?',(datetime.now(timezone.utc).isoformat(),))
                        for photo in photos:
                            token=secrets.token_urlsafe(32)
                            con.execute('INSERT INTO ticket_media_tokens(token,photo_id,expires_at) VALUES(?,?,?)',
                                        (token,photo['id'],expiry))
                            album_urls.append(config['media_url']+'/api/integration-ticket-media/'+token)
            if record['event']=='ticket_tenant':
                if not config.get('ticket_enabled') or not dest.get('on_ticket_tenant') or not dest.get('tenant_id'):
                    raise RuntimeError('Đã tắt thông báo sửa chữa cho khách hoặc nơi nhận không hợp lệ.')
                with connect() as con:
                    ticket=one(con,"""SELECT k.reported_by_tenant_id tenant_id,r.property_id
                         FROM tickets k JOIN rooms r ON r.id=k.room_id WHERE k.id=?""",(record['ticket_id'],))
                if not ticket or ticket['tenant_id']!=dest['tenant_id'] or (dest['property_id'] is not None and dest['property_id']!=ticket['property_id']):
                    raise RuntimeError('Nơi nhận không được phép xem yêu cầu sửa chữa này.')
            if record['event']=='meter_submission':
                if not config.get('reading_enabled') or not dest.get('on_meter_submission') or dest.get('tenant_id'):
                    raise RuntimeError('Đã tắt thông báo chỉ số hoặc nơi nhận không hợp lệ.')
                with connect() as con:
                    submission=one(con,'SELECT property_id FROM tenant_meter_submissions WHERE id=?',(record['submission_id'],))
                if not submission or (dest['property_id'] is not None and dest['property_id']!=submission['property_id']):
                    raise RuntimeError('Nơi nhận không được phép xem chỉ số này.')
            _bot_send(config,dest,record['message'],image_url,image_urls=album_urls)
        except Exception as exc:
            error=str(exc)[:220]
        with tx() as con:
            con.execute("UPDATE zalo_outbox SET status=?,error=?,sent_at=CASE WHEN ?='' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?",
                        ('failed' if error else 'sent',error,error,ident))
        count+=1
    return count



@router.get('/api/v6/invoices/{ident}/image.png')
def invoice_image_download(ident:int,user=Depends(authorized)):
    """Private PNG export with the same content as the automatic Zalo attachment."""
    from .main import scope_records
    if user['role']!='admin' and not user['permissions'].get('invoices.view'):
        fail('Không có quyền xem hóa đơn.',403)
    with connect() as con:
        accessible=scope_records(user,rows(con,
            'SELECT i.id,r.property_id FROM invoices i JOIN rooms r ON r.id=i.room_id WHERE i.id=?',(ident,)))
        if not accessible:fail('Không có quyền xem hóa đơn này.',404)
        invoice=_invoice(con,ident)
        if not invoice:fail('Không tìm thấy hóa đơn.',404)
        qr=_qr_details(con,ident)
        details=invoice_lines(con,ident)
    return Response(_invoice_png(invoice,qr,details),media_type='image/png',headers={
        'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
        'Content-Disposition':f'attachment; filename="HD{ident:05d}_{invoice["period"].replace("-","")}.png"'})

@router.get('/api/integration-media/{token}')
def integration_media(token:str):
    # Opaque 256-bit short-lived capability; only invoice rendering, never uploads/CCCD.
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,60}',token):fail('Không có nội dung.',404)
    with connect() as con:
        row=one(con,'SELECT invoice_id FROM notification_media WHERE token=? AND expires_at>?',(token,datetime.now(timezone.utc).isoformat()))
        if not row:fail('Liên kết hết hạn.',404)
        invoice=_invoice(con,row['invoice_id'])
        if not invoice:fail('Không có hóa đơn.',404)
        qr=_qr_details(con,row['invoice_id'])
    with connect() as con: details=invoice_lines(con,row['invoice_id'])
    return Response(_invoice_png(invoice,qr,details),media_type='image/png',headers={
        'Cache-Control':'no-store','Content-Disposition':'attachment; filename="hoa-don.png"',
        'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'})
