"""TroFlow 2.0 add-on REST API; old URLs/database remain backwards compatible."""
import csv
import io
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response

from .db import connect, tx, one, rows
from . import db as dbmodule
from .billing import calculate, create, month_range
from .main import authorized, admin_user, fail, positive, trim, date_str, period_str, enum, audit, json_ok, CONTRACT_SQL, occupied_contract

router = APIRouter(prefix='/api/v2', tags=['TroFlow 2'])
UPLOADS=Path(os.getenv('UPLOAD_DIRECTORY','/app/uploads'))
BACKUPS=Path(os.getenv('BACKUP_DIRECTORY','/app/backups'))


def right(user, property_id=None, permission='view'):
    """Admin unrestricted. Existing staff maps to manager; grants restrict property ids."""
    if user['role']=='admin': return
    # Capability checks are centralized in authorized(); here enforce property scope.
    grant_ids=user.get('grant_ids',[])
    if property_id is not None and grant_ids and int(property_id) not in grant_ids:
        fail('Không được truy cập cơ sở này.',403)


def contract_property(con,contract_id):
    row=one(con,'SELECT r.property_id FROM contracts c JOIN rooms r ON r.id=c.room_id WHERE c.id=?',(contract_id,))
    if not row: fail('Không tìm thấy hợp đồng.',404)
    return row['property_id']


def invoice_property(con,invoice_id):
    row=one(con,'SELECT r.property_id FROM invoices i JOIN rooms r ON r.id=i.room_id WHERE i.id=?',(invoice_id,))
    if not row: fail('Không tìm thấy hóa đơn.',404)
    return row['property_id']


def room_property(con,room_id):
    row=one(con,'SELECT property_id FROM rooms WHERE id=?',(room_id,))
    if not row: fail('Không tìm thấy phòng.',404)
    return row['property_id']


def money(data,key,default=0,limit=1_000_000_000):
    return positive(data.get(key,default),key,0,limit)


def get_contract(con,cid):
    item=one(con,CONTRACT_SQL+' WHERE c.id=?',(cid,))
    if not item:fail('Không tìm thấy hợp đồng.',404)
    return item


@router.get('/summary')
def summary(user=Depends(authorized)):
    with connect() as con:
        granted=user.get('grant_ids',[])
        param=() if user['role']=='admin' or not granted else tuple(granted)
        clause='' if not param else ' WHERE p.id IN ('+','.join('?' for _ in param)+')'
        props=rows(con,'SELECT p.id,p.name FROM properties p'+clause+' ORDER BY name',param)
        ids=[r['id'] for r in props]
        if not ids: return {'properties':[],'drafts':0,'missing_readings':[],'unsettled_deposits':0,'today':date.today().isoformat()}
        q=','.join('?' for _ in ids)
        drafts=one(con,f"SELECT COUNT(*) n FROM invoices i JOIN rooms r ON r.id=i.room_id WHERE i.status='draft' AND r.property_id IN ({q})",ids)['n']
        period=date.today().strftime('%Y-%m')
        missing=rows(con,f'''SELECT r.id room_id,r.code,p.name property_name FROM rooms r
         JOIN properties p ON p.id=r.property_id JOIN contracts c ON c.room_id=r.id AND c.status='active'
         LEFT JOIN readings d ON d.room_id=r.id AND d.period=?
         WHERE r.property_id IN ({q}) AND d.id IS NULL''',(period,*ids))
        unsettled=one(con,f'''SELECT COUNT(DISTINCT c.id) n FROM contracts c JOIN rooms r ON r.id=c.room_id
         WHERE c.status='ended' AND c.deposit>0 AND r.property_id IN ({q})
         AND EXISTS(SELECT 1 FROM deposit_transactions d WHERE d.contract_id=c.id)
         AND (SELECT COALESCE(SUM(CASE WHEN kind='receive' THEN amount ELSE -amount END),0)
         FROM deposit_transactions WHERE contract_id=c.id)>0''',ids)['n']
        return {'properties':props,'drafts':drafts,'missing_readings':missing,'unsettled_deposits':unsettled,'today':date.today().isoformat()}


# 01 DEPOSIT LEDGER. No edits/deletes: corrections must be offsetting entries.
@router.get('/deposits')
def deposits(contract_id:int|None=None,user=Depends(authorized)):
    with connect() as con:
        sql='''SELECT d.*,c.deposit expected,r.code room_code,p.name property_name,r.property_id,
          t.full_name tenant_name,t.phone tenant_phone,t.id_number tenant_id_number,t.photo_path tenant_photo_path FROM deposit_transactions d JOIN contracts c ON c.id=d.contract_id
          JOIN rooms r ON r.id=c.room_id JOIN properties p ON p.id=r.property_id
          JOIN tenants t ON t.id=c.tenant_id'''
        params=[]
        if contract_id: sql+=' WHERE d.contract_id=?';params=[contract_id]
        result=rows(con,sql+' ORDER BY d.id DESC',params)
        return [r for r in result if user['role']=='admin' or not user.get('grant_ids') or r['property_id'] in user['grant_ids']]

@router.get('/deposits/balances')
def deposit_balances(user=Depends(authorized)):
    with connect() as con:
        results=rows(con,'''SELECT c.id contract_id,c.deposit required_amount,c.status,r.code room_code,r.property_id,
           p.name property_name,t.full_name tenant_name,t.phone tenant_phone,t.id_number tenant_id_number,t.photo_path tenant_photo_path,
           COALESCE(SUM(CASE WHEN d.kind='receive' THEN d.amount WHEN d.kind IN ('refund','deduct') THEN -d.amount ELSE 0 END),0) held,
           COALESCE(SUM(CASE WHEN d.kind='receive' THEN d.amount ELSE 0 END),0) received,
           COALESCE(SUM(CASE WHEN d.kind='refund' THEN d.amount ELSE 0 END),0) refunded,
           COALESCE(SUM(CASE WHEN d.kind='deduct' THEN d.amount ELSE 0 END),0) deducted
           FROM contracts c JOIN rooms r ON r.id=c.room_id JOIN properties p ON p.id=r.property_id
           JOIN tenants t ON t.id=c.tenant_id LEFT JOIN deposit_transactions d ON d.contract_id=c.id
           GROUP BY c.id ORDER BY c.id DESC''')
        return [{**r,'missing':max(0,r['required_amount']-r['received'])} for r in results
                if user['role']=='admin' or not user.get('grant_ids') or r['property_id'] in user['grant_ids']]

@router.post('/deposits')
def add_deposit(data:dict,user=Depends(authorized)):
    cid=positive(data.get('contract_id'),'Hợp đồng',1)
    kind=enum(data.get('kind'),'Loại giao dịch',['receive','refund','deduct'])
    amount=money(data,'amount',limit=1_000_000_000)
    if not amount: fail('Số tiền phải lớn hơn 0.')
    on=date_str(data.get('transacted_on',date.today().isoformat()),'Ngày giao dịch')
    with tx() as con:
        right(user,contract_property(con,cid),'deposits')
        current=one(con,'''SELECT COALESCE(SUM(CASE WHEN kind='receive' THEN amount ELSE -amount END),0) balance
                           FROM deposit_transactions WHERE contract_id=?''',(cid,))['balance']
        if kind!='receive' and amount>current:fail('Số tiền hoàn/khấu trừ vượt quá số cọc còn giữ.')
        ident=con.execute('''INSERT INTO deposit_transactions(contract_id,kind,amount,transacted_on,note,created_by)
            VALUES(?,?,?,?,?,?)''',(cid,kind,amount,on,trim(data.get('note'),'Lý do',1000),user['id'])).lastrowid
        audit(con,user,'create','deposit',ident,f'{kind}:{amount}')
    return json_ok(id=ident)

# 04 ALL RESIDENTS (lead was migrated from original tenant record)
@router.get('/residents')
def residents(contract_id:int|None=None,user=Depends(authorized)):
    with connect() as con:
        sql='''SELECT res.*,r.code room_code,r.property_id,p.name property_name FROM contract_residents res
          JOIN contracts c ON c.id=res.contract_id JOIN rooms r ON r.id=c.room_id JOIN properties p ON p.id=r.property_id'''
        params=[]
        if contract_id:sql+=' WHERE res.contract_id=?';params=[contract_id]
        items=rows(con,sql+' ORDER BY res.contract_id DESC,res.is_primary DESC,res.id',params)
        return [x for x in items if user['role']=='admin' or not user.get('grant_ids') or x['property_id'] in user['grant_ids']]

@router.post('/residents')
def add_resident(data:dict,user=Depends(authorized)):
    cid=positive(data.get('contract_id'),'Hợp đồng',1)
    with tx() as con:
        right(user,contract_property(con,cid),'residents')
        contract=get_contract(con,cid)
        move=date_str(data.get('moved_in',contract['start_date']),'Ngày vào')
        if move<contract['start_date']: fail('Ngày vào trước ngày bắt đầu hợp đồng.')
        ident=con.execute('''INSERT INTO contract_residents(contract_id,full_name,phone,id_number,hometown,moved_in,notes)
              VALUES(?,?,?,?,?,?,?)''',(cid,trim(data.get('full_name'),'Họ tên',120,True),
              trim(data.get('phone'),'Số điện thoại',30),trim(data.get('id_number'),'CCCD',40),
              trim(data.get('hometown'),'Quê quán',250),move,trim(data.get('notes'),'Ghi chú',500))).lastrowid
        audit(con,user,'create','resident',ident)
    return json_ok(id=ident)

@router.post('/residents/{ident}/leave')
def leave_resident(ident:int,data:dict,user=Depends(authorized)):
    left=date_str(data.get('moved_out'),'Ngày rời')
    with tx() as con:
        res=one(con,'SELECT * FROM contract_residents WHERE id=?',(ident,))
        if not res:fail('Không tìm thấy người ở.',404)
        right(user,contract_property(con,res['contract_id']),'residents')
        if res['is_primary']:fail('Không thể cho người đại diện rời phòng trước khi kết thúc hợp đồng.')
        if left<res['moved_in']:fail('Ngày rời trước ngày vào.')
        con.execute('UPDATE contract_residents SET moved_out=? WHERE id=?',(left,ident))
        audit(con,user,'leave','resident',ident)
    return json_ok()

# 03 CONTRACT-LEVEL SERVICE TARIFF
@router.get('/services')
def services(user=Depends(authorized)):
    with connect() as con:
        result=rows(con,'''SELECT s.*,p.name property_name FROM service_catalog s
          JOIN properties p ON p.id=s.property_id ORDER BY s.property_id,s.id''')
        return [x for x in result if user['role']=='admin' or not user.get('grant_ids') or x['property_id'] in user['grant_ids']]

@router.post('/services')
def new_service(data:dict,user=Depends(authorized)):
    pid=positive(data.get('property_id'),'Cơ sở',1)
    right(user,pid,'services')
    with tx() as con:
        try:
            ident=con.execute('''INSERT INTO service_catalog(property_id,name,unit,charge_type,unit_price)
                VALUES(?,?,?,?,?)''',(pid,trim(data.get('name'),'Tên dịch vụ',80,True),
                trim(data.get('unit','thang'),'Đơn vị',30),enum(data.get('charge_type'),'Cách tính',['flat','person','quantity']),
                money(data,'unit_price'))).lastrowid
        except sqlite3.IntegrityError:fail('Dịch vụ đã tồn tại tại cơ sở này.')
        audit(con,user,'create','service',ident)
    return json_ok(id=ident)

@router.put('/services/{ident}')
def edit_service(ident:int,data:dict,user=Depends(authorized)):
    with tx() as con:
        old=one(con,'SELECT * FROM service_catalog WHERE id=?',(ident,))
        if not old:fail('Không tìm thấy dịch vụ.',404)
        right(user,old['property_id'],'services')
        con.execute('UPDATE service_catalog SET name=?,unit=?,charge_type=?,unit_price=?,active=? WHERE id=?',(
            trim(data.get('name'),'Tên',80,True),trim(data.get('unit','thang'),'Đơn vị',30),
            enum(data.get('charge_type'),'Loại',['flat','person','quantity']),money(data,'unit_price'),
            1 if data.get('active',True) else 0,ident))
        audit(con,user,'update','service',ident)
    return json_ok()

@router.get('/contract-services')
def assigned_services(user=Depends(authorized)):
    with connect() as con:
        result=rows(con,'''SELECT cs.*,s.name service_name,s.charge_type,s.unit_price,c.room_id,r.property_id,
          r.code room_code FROM contract_services cs JOIN service_catalog s ON s.id=cs.service_id
          JOIN contracts c ON c.id=cs.contract_id JOIN rooms r ON r.id=c.room_id ORDER BY cs.id DESC''')
        return [x for x in result if user['role']=='admin' or not user.get('grant_ids') or x['property_id'] in user['grant_ids']]

@router.post('/contract-services')
def assign_service(data:dict,user=Depends(authorized)):
    cid=positive(data.get('contract_id'),'Hợp đồng',1)
    sid=positive(data.get('service_id'),'Dịch vụ',1)
    try:quantity=float(data.get('quantity',1))
    except (ValueError,TypeError):fail('Số lượng không hợp lệ.')
    if not 0<=quantity<=10000:fail('Số lượng không hợp lệ.')
    with tx() as con:
        pid=contract_property(con,cid);right(user,pid,'services')
        service=one(con,'SELECT * FROM service_catalog WHERE id=?',(sid,))
        if not service or service['property_id']!=pid:fail('Dịch vụ phải thuộc cùng cơ sở.')
        con.execute('''INSERT INTO contract_services(contract_id,service_id,quantity,active) VALUES(?,?,?,1)
          ON CONFLICT(contract_id,service_id) DO UPDATE SET quantity=excluded.quantity,active=1''',(cid,sid,quantity))
        audit(con,user,'assign','service',sid,f'contract:{cid}')
    return json_ok()

@router.delete('/contract-services/{ident}')
def remove_assigned_service(ident:int,user=Depends(authorized)):
    with tx() as con:
        assignment=one(con,'''SELECT cs.contract_id FROM contract_services cs WHERE cs.id=?''',(ident,))
        if not assignment:fail('Không tìm thấy liên kết.',404)
        right(user,contract_property(con,assignment['contract_id']),'services')
        con.execute('UPDATE contract_services SET active=0 WHERE id=?',(ident,))
        audit(con,user,'deactivate','service_assignment',ident)
    return json_ok()

# 02 PRORATED RENT SWITCH: legacy stays full month unless explicitly enabled.
@router.put('/contracts/{ident}/proration')
def contract_proration(ident:int,data:dict,user=Depends(authorized)):
    with tx() as con:
        pid=contract_property(con,ident);right(user,pid,'billing')
        if one(con,"SELECT 1 FROM rent_coverage WHERE contract_id=? AND status='active' LIMIT 1",(ident,)):
            fail('Hợp đồng đã nhận tiền thuê trả trước. Không thể thay đổi cách tính theo ngày trước khi quyết toán.')
        con.execute('UPDATE contracts SET prorate=? WHERE id=?',(1 if data.get('enabled') else 0,ident))
        audit(con,user,'update','contract_proration',ident)
    return json_ok()

# 05 READING BATCH, ALERTS
@router.post('/readings/batch')
def readings_batch(data:dict,user=Depends(authorized)):
    period=period_str(data.get('period'))
    entries=data.get('entries',[])
    if not isinstance(entries,list) or not 1<=len(entries)<=500: fail('Cần từ 1 đến 500 dòng chỉ số.')
    done=[];alerts=[]
    with tx() as con:
        for entry in entries:
            rid=positive(entry.get('room_id'),'Phòng',1)
            right(user,room_property(con,rid),'reading')
            if user['role']!='admin' and not user['permissions'].get('readings.record'):
                fail('Chưa được cấp quyền ghi chỉ số.',403)
            if not occupied_contract(con,rid,period):
                fail(f'Phòng #{rid} chưa có người thuê / hợp đồng trong kỳ {period}.')
            vals=[float(entry.get(k,0)) for k in ('electric_old','electric_new','water_old','water_new')]
            if any(x<0 or x>10_000_000 for x in vals) or vals[1]<vals[0] or vals[3]<vals[2]:fail('Chỉ số mới phải >= chỉ số cũ và không âm.')
            if one(con,'SELECT id FROM invoices WHERE room_id=? AND period=?',(rid,period)):
                fail(f'Phòng #{rid} đã có hóa đơn, không thể sửa chỉ số.')
            prev=one(con,'''SELECT electric_new,water_new FROM readings
                            WHERE room_id=? AND period<? ORDER BY period DESC LIMIT 1''',(rid,period))
            if prev and (vals[0]!=prev['electric_new'] or vals[2]!=prev['water_new']):
                alerts.append({'room_id':rid,'message':'Chỉ số đầu kỳ khác chỉ số cuối kỳ trước.'})
            if vals[1]-vals[0]>500 or vals[3]-vals[2]>50:
                alerts.append({'room_id':rid,'message':'Mức tiêu thụ bất thường, cần kiểm tra.'})
            con.execute('''INSERT INTO readings(room_id,period,electric_old,electric_new,water_old,water_new)
             VALUES(?,?,?,?,?,?) ON CONFLICT(room_id,period) DO UPDATE SET
             electric_old=excluded.electric_old,electric_new=excluded.electric_new,
             water_old=excluded.water_old,water_new=excluded.water_new''',(rid,period,*vals))
            done.append(rid)
        audit(con,user,'batch','reading',None,f'{period}:{len(done)}')
    return json_ok(updated=len(done),alerts=alerts)

@router.get('/readings/alerts')
def reading_alerts(period:str,user=Depends(authorized)):
    period=period_str(period)
    first,last=month_range(period)
    with connect() as con:
        contracts=rows(con,CONTRACT_SQL+" WHERE c.status='active' AND c.start_date<=? AND c.end_date>=?",(last.isoformat(),first.isoformat()))
        warnings=[]
        for item in contracts:
            if user['role']!='admin' and user.get('grant_ids') and item['property_id'] not in user['grant_ids']:continue
            rd=one(con,'SELECT * FROM readings WHERE room_id=? AND period=?',(item['room_id'],period))
            if not rd:warnings.append({'room_id':item['room_id'],'room_code':item['room_code'],'message':'Thiếu chỉ số kỳ này'});continue
            if rd['electric_new']-rd['electric_old']>500 or rd['water_new']-rd['water_old']>50:
                warnings.append({'room_id':item['room_id'],'room_code':item['room_code'],'message':'Tiêu thụ tăng bất thường'})
            prev=one(con,'SELECT electric_new,water_new FROM readings WHERE room_id=? AND period<? ORDER BY period DESC LIMIT 1',(item['room_id'],period))
            if prev and (rd['electric_old']!=prev['electric_new'] or rd['water_old']!=prev['water_new']):
                warnings.append({'room_id':item['room_id'],'room_code':item['room_code'],'message':'Chỉ số không liên tục'})
        return warnings

# 06 DRAFT, REVIEW, REVISE, APPROVE
@router.post('/invoices/preview')
def invoice_preview(data:dict,user=Depends(authorized)):
    cid=positive(data.get('contract_id'),'Hợp đồng',1)
    period=period_str(data.get('period'))
    with connect() as con:
        c=get_contract(con,cid);right(user,c['property_id'],'billing')
        try:return calculate(con,c,period,int(data.get('adjustment',0)),money(data,'discount'),money(data,'surcharge'))
        except ValueError as exc:fail(str(exc))

@router.post('/invoices/draft')
def invoice_draft(data:dict,user=Depends(authorized)):
    cid=positive(data.get('contract_id'),'Hợp đồng',1);period=period_str(data.get('period'))
    with tx() as con:
        contract=get_contract(con,cid);right(user,contract['property_id'],'billing')
        if one(con,'SELECT id FROM invoices WHERE contract_id=? AND period=?',(cid,period)):
            fail('Hợp đồng đã có hóa đơn cho kỳ này.')
        try:ident=create(con,contract,period,int(data.get('adjustment',0)),trim(data.get('note'),'Ghi chú',1000),
                    status='draft',discount=money(data,'discount'),surcharge=money(data,'surcharge'))
        except ValueError as exc:fail(str(exc))
        audit(con,user,'create_draft','invoice',ident)
    return json_ok(id=ident)

@router.get('/invoices/{ident}/lines')
def invoice_lines(ident:int,user=Depends(authorized)):
    with connect() as con:
        right(user,invoice_property(con,ident),'view')
        return rows(con,'SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY id',(ident,))

@router.get('/invoices/{ident}/revisions')
def invoice_revisions(ident:int,user=Depends(authorized)):
    with connect() as con:
        right(user,invoice_property(con,ident),'view')
        return rows(con,'SELECT * FROM invoice_revisions WHERE invoice_id=? ORDER BY id DESC',(ident,))

@router.put('/invoices/{ident}/draft')
def edit_invoice_draft(ident:int,data:dict,user=Depends(authorized)):
    with tx() as con:
        right(user,invoice_property(con,ident),'billing')
        inv=one(con,'SELECT * FROM invoices WHERE id=?',(ident,))
        if inv['status']!='draft':fail('Chỉ được sửa hóa đơn nháp.')
        before=json.dumps(inv,ensure_ascii=False)
        # Price changes require explicit reason. Rent & utilities remain original ledger snapshots.
        discount=money(data,'discount');surcharge=money(data,'surcharge')
        try: adjustment=int(data.get('adjustment',inv['adjustment']))
        except (ValueError,TypeError):fail('Điều chỉnh không hợp lệ.')
        if abs(adjustment)>100_000_000:fail('Điều chỉnh quá lớn.')
        total=inv['rent']+inv['electricity']+inv['water']+inv['services']+adjustment-discount+surcharge
        if total<0:fail('Tổng hóa đơn không thể âm.')
        note=trim(data.get('note',inv['note']),'Ghi chú',1000)
        reason=trim(data.get('reason'),'Lý do thay đổi',500,True)
        con.execute('''UPDATE invoices SET discount=?,surcharge=?,adjustment=?,total=?,note=? WHERE id=?''',
                    (discount,surcharge,adjustment,total,note,ident))
        con.execute("DELETE FROM invoice_lines WHERE invoice_id=? AND code IN ('discount','surcharge','adjustment')",(ident,))
        for label,code,amount in [('Giảm giá','discount',-discount),('Truy thu','surcharge',surcharge),('Điều chỉnh','adjustment',adjustment)]:
            if amount:con.execute('INSERT INTO invoice_lines(invoice_id,label,code,quantity,unit_price,amount) VALUES(?,?,?,1,?,?)',
                                 (ident,label,code,amount,amount))
        after=json.dumps(one(con,'SELECT * FROM invoices WHERE id=?',(ident,)),ensure_ascii=False)
        con.execute('''INSERT INTO invoice_revisions(invoice_id,actor_id,before_json,after_json,reason)
             VALUES(?,?,?,?,?)''',(ident,user['id'],before,after,reason))
        audit(con,user,'revise','invoice',ident,reason)
    return json_ok()

@router.post('/invoices/{ident}/publish')
def publish_invoice(ident:int,user=Depends(authorized)):
    with tx() as con:
        right(user,invoice_property(con,ident),'billing')
        invoice=one(con,'SELECT * FROM invoices WHERE id=?',(ident,))
        if invoice['status']!='draft':fail('Hóa đơn đã chốt.')
        con.execute("UPDATE invoices SET status='published',published_at=? WHERE id=?",(date.today().isoformat(),ident))
        audit(con,user,'publish','invoice',ident)
        from .notify import enqueue_invoice_event
        enqueue_invoice_event(con,ident,'invoice')
    return json_ok()

# 07 VietQR quick link (bank image is an external service, never an auto-payment acknowledgment).
@router.put('/properties/{ident}/bank')
def bank_settings(ident:int,data:dict,user=Depends(admin_user)):
    bank=trim(data.get('bank_code'),'Mã ngân hàng',20)
    account=trim(data.get('bank_account'),'Số tài khoản',30)
    holder=trim(data.get('bank_name'),'Chủ tài khoản',120)
    if bank and not re.fullmatch(r'[A-Za-z0-9]{2,20}',bank):fail('Mã ngân hàng không hợp lệ.')
    if account and not re.fullmatch(r'[0-9]{4,25}',account):fail('Số tài khoản không hợp lệ.')
    with tx() as con:
        con.execute('UPDATE properties SET bank_code=?,bank_account=?,bank_name=? WHERE id=?',(bank,account,holder,ident))
        # Compatibility: legacy bank setting must update the active V6 bank too.
        if bank and account:
            from .notify import _save_bank
            existing=one(con,'SELECT id FROM bank_accounts WHERE property_id=? AND bank_code=? AND account_number=?',
                         (ident,bank.upper(),account))
            if existing:
                con.execute('UPDATE bank_accounts SET is_default=0 WHERE property_id=?',(ident,))
                con.execute('UPDATE bank_accounts SET is_default=1,active=1,holder=? WHERE id=?',(holder,existing['id']))
            else:
                _save_bank(con,{'property_id':ident,'bank_code':bank.upper(),'bank_name':bank.upper(),
                               'holder':holder,'account_number':account,'is_default':1,'active':1})
        audit(con,user,'update','bank_config',ident)
    return json_ok()

@router.get('/invoices/{ident}/vietqr')
def vietqr(ident:int,user=Depends(authorized)):
    """Backwards-compatible V2 VietQR endpoint; now uses the active default bank."""
    from .notify import _qr_details
    with connect() as con:
        right(user,invoice_property(con,ident),'view')
        state=one(con,'SELECT status FROM invoices WHERE id=?',(ident,))
        if not state:fail('Không tìm thấy hóa đơn.',404)
        if state['status']!='published':fail('Hãy chốt hóa đơn trước khi xuất VietQR.')
        result=_qr_details(con,ident)
        if not result['configured']:fail('Cơ sở chưa cấu hình tài khoản ngân hàng.')
        # Return the same reference/QR as all other invoice views and Zalo images.
        return {'url':result['qr_url'],'amount':result['amount'],
                'transfer_note':result['content'],'bank_name':result['holder'],
                'bank_code':result['bank_code'],'bank_account':result['account_number'],
                'disclaimer':'QR chỉ tạo yêu cầu chuyển khoản, không xác nhận đã nhận tiền.'}

# 08 HANDOVER & CHECKOUT (atomic deposit withholding)
@router.get('/handovers')
def handovers(user=Depends(authorized)):
    with connect() as con:
        result=rows(con,'''SELECT h.*,r.code room_code,r.property_id,p.name property_name,t.full_name tenant_name,t.phone tenant_phone,t.id_number tenant_id_number,t.photo_path tenant_photo_path
          FROM handovers h JOIN contracts c ON c.id=h.contract_id JOIN rooms r ON r.id=c.room_id
          JOIN properties p ON p.id=r.property_id JOIN tenants t ON t.id=c.tenant_id ORDER BY h.id DESC''')
        return [x for x in result if user['role']=='admin' or not user.get('grant_ids') or x['property_id'] in user['grant_ids']]

@router.post('/handovers')
def handover(data:dict,user=Depends(authorized)):
    cid=positive(data.get('contract_id'),'Hợp đồng',1)
    kind=enum(data.get('handover_type'),'Loại bàn giao',['checkin','checkout'])
    handover_on=date_str(data.get('handover_on',date.today().isoformat()),'Ngày bàn giao')
    damage=money(data,'damage_amount')
    if kind=='checkin' and (damage or money(data,'refund_amount')):
        fail('Khấu trừ và hoàn cọc chỉ thực hiện khi trả phòng.')
    with tx() as con:
        contract=get_contract(con,cid);right(user,contract['property_id'],'handover')
        if kind=='checkout' and user['role']!='admin':
            if not user['permissions'].get('contracts.end'):
                fail('Chưa được cấp quyền kết thúc hợp đồng.',403)
            if (damage or money(data,'refund_amount')) and not user['permissions'].get('deposits.record'):
                fail('Chưa được cấp quyền xử lý tiền cọc.',403)
        if kind=='checkout' and contract['status']!='active':fail('Hợp đồng đã kết thúc.')
        if handover_on<contract['start_date']:fail('Ngày bàn giao trước ngày hợp đồng bắt đầu.')
        try:
            ident=con.execute('''INSERT INTO handovers(contract_id,handover_type,handover_on,description,
             damage_amount,electric_final,water_final,confirmed_by,created_by) VALUES(?,?,?,?,?,?,?,?,?)''',(
              cid,kind,handover_on,trim(data.get('description'),'Biên bản',2000),damage,
              float(data['electric_final']) if str(data.get('electric_final','')).strip() else None,
              float(data['water_final']) if str(data.get('water_final','')).strip() else None,
              trim(data.get('confirmed_by'),'Người xác nhận',120),user['id'])).lastrowid
        except sqlite3.IntegrityError:fail('Hợp đồng đã có biên bản cùng loại.')
        if kind=='checkout':
            future=one(con,'''SELECT COALESCE(SUM(amount),0) n FROM rent_coverage
                WHERE contract_id=? AND period>? AND status='active' ''',(cid,handover_on[:7]))['n']
            if future:fail(f'Còn {future:,} VND tiền thuê trả trước của các tháng sau ngày trả phòng. Hãy hoàn các tháng chưa dùng trước khi kết thúc hợp đồng.')
            unpaid=one(con,'''SELECT COALESCE(SUM(i.total-COALESCE(p.amount,0)),0) amount
                 FROM invoices i LEFT JOIN (SELECT invoice_id,SUM(amount) amount FROM payments GROUP BY invoice_id) p
                 ON p.invoice_id=i.id WHERE i.contract_id=? AND i.status='published' ''',(cid,))['amount']
            if unpaid>0 and not data.get('ack_debt'):
                fail(f'Hợp đồng còn {unpaid:,} VND công nợ. Xác nhận đối chiếu nợ trước khi trả phòng.')
            # End-of-occupancy meter snapshot: don't mutate readings already invoiced.
            if data.get('electric_final') is not None or data.get('water_final') is not None:
                period=handover_on[:7]
                existing=one(con,'SELECT * FROM readings WHERE room_id=? AND period=?',(contract['room_id'],period))
                previous=one(con,'SELECT electric_new,water_new FROM readings WHERE room_id=? AND period<? ORDER BY period DESC LIMIT 1',
                             (contract['room_id'],period))
                eo=existing['electric_old'] if existing else (previous['electric_new'] if previous else 0)
                wo=existing['water_old'] if existing else (previous['water_new'] if previous else 0)
                en=float(data.get('electric_final') if data.get('electric_final') not in (None,'') else existing['electric_new'] if existing else eo)
                wn=float(data.get('water_final') if data.get('water_final') not in (None,'') else existing['water_new'] if existing else wo)
                if en<eo or wn<wo or en>1e7 or wn>1e7:fail('Chỉ số bàn giao không hợp lệ.')
                locked=one(con,'SELECT id FROM invoices WHERE room_id=? AND period=?',(contract['room_id'],period))
                if locked and (not existing or en!=existing['electric_new'] or wn!=existing['water_new']):
                    fail('Chỉ số tháng này đã lên hóa đơn. Cần quyết toán điện nước trước khi thay đổi chỉ số cuối.')
                if not locked:
                    con.execute('''INSERT INTO readings(room_id,period,electric_old,electric_new,water_old,water_new)
                     VALUES(?,?,?,?,?,?) ON CONFLICT(room_id,period) DO UPDATE SET
                     electric_new=excluded.electric_new,water_new=excluded.water_new''',
                     (contract['room_id'],period,eo,en,wo,wn))
            held=one(con,'''SELECT COALESCE(SUM(CASE WHEN kind='receive' THEN amount ELSE -amount END),0) n
                 FROM deposit_transactions WHERE contract_id=?''',(cid,))['n']
            if damage>held:fail('Khấu trừ vượt số cọc còn giữ. Hãy ghi nhận khoản khác riêng.')
            if damage:
                con.execute('''INSERT INTO deposit_transactions(contract_id,kind,amount,transacted_on,note,created_by)
                 VALUES(?,'deduct',?,?,?,?)''',(cid,damage,handover_on,'Khấu trừ hư hỏng khi trả phòng',user['id']))
            refund=money(data,'refund_amount')
            if refund>held-damage:fail('Hoàn cọc vượt số dư còn giữ.')
            if refund:
                con.execute('''INSERT INTO deposit_transactions(contract_id,kind,amount,transacted_on,note,created_by)
                 VALUES(?,'refund',?,?,?,?)''',(cid,refund,handover_on,'Hoàn cọc khi trả phòng',user['id']))
            con.execute('UPDATE contracts SET status=\'ended\',end_date=? WHERE id=?',(handover_on,cid))
            con.execute('''UPDATE contract_residents SET moved_out=? WHERE contract_id=? AND moved_out IS NULL''',(handover_on,cid))
        audit(con,user,'handover','contract',cid,kind)
    return json_ok(id=ident,open_debt=unpaid if kind=='checkout' else 0)

# 05 + 08 PHOTOS. Private with authenticated fetch; validate basic file signatures.
@router.post('/files')
async def upload_file(category:str=Form(...),related_id:int=Form(...),file:UploadFile=File(...),user=Depends(authorized)):
    category=enum(category,'Loại tệp',['electric','water','checkin','checkout','tenant','tenant_id_front','tenant_id_back'])
    if user['role']!='admin' and category in ('electric','water') and not user['permissions'].get('readings.photos'):
        fail('Chưa được cấp quyền tải ảnh công tơ.',403)
    contents=await file.read(3*1024*1024+1)
    if len(contents)>3*1024*1024 or len(contents)<24: fail('Ảnh phải dưới 3 MB và không rỗng.')
    if contents.startswith(b'\x89PNG\r\n\x1a\n'): ext='png'
    elif contents.startswith(b'\xff\xd8\xff'):ext='jpg'
    elif contents[:4]==b'RIFF' and contents[8:12]==b'WEBP':ext='webp'
    else:fail('Chỉ chấp nhận JPG, PNG hoặc WebP.')
    with tx() as con:
        if category in ('tenant','tenant_id_front','tenant_id_back'):
            if user['role']!='admin' and not user['permissions'].get('tenants.edit'):
                fail('Chưa được cấp quyền cập nhật người thuê.',403)
            entity=one(con,'SELECT id FROM tenants WHERE id=?',(related_id,))
            if not entity:fail('Không tìm thấy khách thuê.',404)
            if user['role']!='admin' and user['grant_ids']:
                permitted=one(con,'''SELECT 1 FROM contracts c JOIN rooms r ON r.id=c.room_id
                     WHERE c.tenant_id=? AND r.property_id IN ('''+','.join('?' for _ in user['grant_ids'])+')',
                     (related_id,*user['grant_ids']))
                if not permitted:fail('Khách thuê không thuộc cơ sở được phép.',403)
        elif category in ('electric','water'):
            entity=one(con,'SELECT room_id FROM readings WHERE id=?',(related_id,))
            if not entity:fail('Chỉ số không tồn tại.',404)
            right(user,room_property(con,entity['room_id']),'reading')
        else:
            entity=one(con,'SELECT contract_id,handover_type FROM handovers WHERE id=?',(related_id,))
            if not entity or entity['handover_type']!=category:fail('Biên bản không tồn tại.',404)
            right(user,contract_property(con,entity['contract_id']),'handover')
        UPLOADS.mkdir(parents=True,exist_ok=True)
        name=secrets.token_hex(20)+'.'+ext
        dest=UPLOADS / name
        with open(dest,'xb') as f:f.write(contents)
        os.chmod(dest,0o600)
        if category in ('tenant','tenant_id_front','tenant_id_back'):
            column={'tenant':'photo_path','tenant_id_front':'id_front_path','tenant_id_back':'id_back_path'}[category]
            con.execute(f'UPDATE tenants SET {column}=? WHERE id=?',(name,related_id))
        elif category in ('electric','water'):
            con.execute(f'UPDATE readings SET {category}_photo=? WHERE id=?',(name,related_id))
        else:
            con.execute('UPDATE handovers SET photo_path=? WHERE id=?',(name,related_id))
        audit(con,user,'upload','photo',related_id,category)
    return json_ok(name=name)

@router.get('/files/{name}')
def fetch_file(name:str,user=Depends(authorized)):
    if not re.fullmatch(r'[0-9a-f]{40}\.(png|jpg|webp)',name):fail('Tên ảnh không hợp lệ.',400)
    with connect() as con:
        r=one(con,'''SELECT r.property_id FROM readings d JOIN rooms r ON r.id=d.room_id
            WHERE d.electric_photo=? OR d.water_photo=? LIMIT 1''',(name,name))
        if not r:r=one(con,'''SELECT r.property_id FROM handovers h JOIN contracts c ON c.id=h.contract_id
            JOIN rooms r ON r.id=c.room_id WHERE h.photo_path=?''',(name,))
        if not r:
            tenant=one(con,'SELECT id FROM tenants WHERE photo_path=? OR id_front_path=? OR id_back_path=?',(name,name,name))
            if tenant:
                if user['role']!='admin' and not user['permissions'].get('tenants.view'):
                    fail('Chưa được cấp quyền xem ảnh khách thuê.',403)
                if user['role']!='admin' and user['grant_ids']:
                    r=one(con,'''SELECT r.property_id FROM contracts c JOIN rooms r ON r.id=c.room_id
                            WHERE c.tenant_id=? AND r.property_id IN ('''+','.join('?' for _ in user['grant_ids'])+') LIMIT 1',
                            (tenant['id'],*user['grant_ids']))
                    if not r:fail('Không có quyền xem ảnh khách thuê này.',403)
                else:r={'property_id':None}
        if not r:fail('Không tìm thấy ảnh.',404)
        if r['property_id'] is not None:right(user,r['property_id'],'view')
    path=UPLOADS/name
    if not path.is_file():fail('Tệp không tồn tại.',404)
    return FileResponse(path,media_type=mimetypes.guess_type(name)[0] or 'image/jpeg',
                        headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

# 09 CSV/XLSX import, 500 rows max, all-or-nothing; dry run uses a savepoint.
IMPORT_FIELDS={
 'rooms':['property_id','code','floor','area','rent','deposit','condition','notes'],
 'tenants':['full_name','phone','email','id_number','hometown','notes'],
 'contracts':['room_id','tenant_id','start_date','end_date','monthly_rent','deposit','due_day','occupants','notes'],
 'readings':['room_id','period','electric_old','electric_new','water_old','water_new']}

@router.get('/imports/template/{entity}')
def import_template(entity:str,user=Depends(authorized)):
    if entity not in IMPORT_FIELDS:fail('Không hỗ trợ mẫu nhập.',404)
    contents=','.join(IMPORT_FIELDS[entity])+'\r\n'
    return Response('\ufeff'+contents,media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="troflow-import-{entity}.csv"'})


def load_import_rows(raw,filename):
    if len(raw)>1_500_000:fail('File vượt 1.5 MB.')
    if filename.lower().endswith('.xlsx'):
        try:
            from openpyxl import load_workbook
            wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
            sheet=wb.active
            iterator=sheet.iter_rows(values_only=True)
            header=[str(x).strip() if x is not None else '' for x in next(iterator)]
            if len(header)!=len(set(header)):fail('Tiêu đề cột trùng lặp.')
            data=[dict(zip(header,record)) for record in iterator if any(x is not None for x in record)]
            wb.close()
        except Exception as exc:
            fail('Không đọc được tệp XLSX: '+str(exc)[:120])
    elif filename.lower().endswith('.csv'):
        try:
            text=raw.decode('utf-8-sig')
            reader=csv.DictReader(io.StringIO(text))
            if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):fail('Thiếu tiêu đề CSV.')
            data=[row for row in reader if any(v and str(v).strip() for v in row.values())]
        except UnicodeDecodeError:fail('CSV cần mã hóa UTF-8.')
    else:fail('Chỉ hỗ trợ CSV hoặc XLSX.')
    if not 1<=len(data)<=500:fail('Tệp cần từ 1 đến 500 dòng dữ liệu.')
    return data


def insert_import(con,entity,row,user):
    from .main import room_values,tenant_values
    permission={'rooms':'rooms.create','tenants':'tenants.create','contracts':'contracts.create','readings':'readings.record'}.get(entity)
    if user['role']!='admin' and not user['permissions'].get(permission,False):
        fail('Chưa được cấp quyền thêm dữ liệu loại này.',403)
    if entity=='rooms':
        values=room_values(row); right(user,values['property_id'],'imports')
        if not one(con,'SELECT id FROM properties WHERE id=?',(values['property_id'],)):fail('Cơ sở không tồn tại.')
        return con.execute(f"INSERT INTO rooms({','.join(values)}) VALUES({','.join('?' for _ in values)})",tuple(values.values())).lastrowid
    if entity=='tenants':
        right(user,permission='imports')
        values=tenant_values(row,creating=True)
        return con.execute(f"INSERT INTO tenants({','.join(values)}) VALUES({','.join('?' for _ in values)})",tuple(values.values())).lastrowid
    if entity=='contracts':
        roomid=positive(row.get('room_id'),'Phòng',1);tid=positive(row.get('tenant_id'),'Khách thuê',1)
        right(user,room_property(con,roomid),'imports')
        start=date_str(row.get('start_date'),'Ngày bắt đầu');end=date_str(row.get('end_date'),'Ngày kết thúc')
        if start>end:fail('Ngày kết thúc trước ngày bắt đầu.')
        if not one(con,'SELECT id FROM tenants WHERE id=?',(tid,)):fail('Khách thuê không tồn tại.')
        values={'room_id':roomid,'tenant_id':tid,'start_date':start,'end_date':end,
          'monthly_rent':money(row,'monthly_rent'),'deposit':money(row,'deposit'),
          'due_day':positive(row.get('due_day',5),'Ngày thanh toán',1,28),
          'occupants':positive(row.get('occupants',1),'Số người',1,50),'notes':trim(row.get('notes'),'Ghi chú',1000)}
        ident=con.execute(f"INSERT INTO contracts({','.join(values)}) VALUES({','.join('?' for _ in values)})",tuple(values.values())).lastrowid
        t=one(con,'SELECT * FROM tenants WHERE id=?',(tid,))
        con.execute('''INSERT INTO contract_residents(contract_id,tenant_id,full_name,phone,id_number,hometown,is_primary,moved_in)
          VALUES(?,?,?,?,?,?,1,?)''',(ident,tid,t['full_name'],t['phone'],t['id_number'],t['hometown'],start))
        return ident
    if entity=='readings':
        rid=positive(row.get('room_id'),'Phòng',1);right(user,room_property(con,rid),'imports')
        period=period_str(row.get('period'))
        if not occupied_contract(con,rid,period):fail('Không thể nhập chỉ số: phòng chưa có người thuê trong kỳ.')
        values=[float(row.get(k,0)) for k in ['electric_old','electric_new','water_old','water_new']]
        if any(x<0 or x>1e7 for x in values) or values[1]<values[0] or values[3]<values[2]:fail('Chỉ số không hợp lệ.')
        return con.execute('''INSERT INTO readings(room_id,period,electric_old,electric_new,water_old,water_new)
          VALUES(?,?,?,?,?,?)''',(rid,period,*values)).lastrowid

@router.post('/imports/{entity}')
async def import_file(entity:str,file:UploadFile=File(...),dry_run:bool=True,user=Depends(authorized)):
    if entity not in IMPORT_FIELDS:fail('Loại dữ liệu không được hỗ trợ.',404)
    data=load_import_rows(await file.read(1_500_001),file.filename or '')
    if any(not set(IMPORT_FIELDS[entity][:2]).issubset(set(r)) for r in data):
        fail('Thiếu cột bắt buộc. Hãy tải đúng file mẫu.')
    result=[]
    # All-or-nothing even for preview; rollback on dry-run.
    with tx() as con:
        for index,r in enumerate(data,2):
            try: result.append(insert_import(con,entity,r,user))
            except (sqlite3.IntegrityError,ValueError,TypeError) as exc:
                fail(f'Lỗi ở dòng {index}: {str(exc)[:150]}')
        if dry_run:
            # Use a named savepoint rollback rather than commit from tx()
            # A private sentinel exception only after data integrity is checked.
            con.rollback()
        else:
            audit(con,user,'import',entity,None,f'{len(result)} rows')
    return json_ok(rows=len(result),dry_run=dry_run,
                   message='Đã kiểm tra hợp lệ, chưa ghi dữ liệu.' if dry_run else 'Đã nhập dữ liệu.')

# 10 Granular staff scope; legacy users role=staff remain manager for compatibility.
@router.get('/access')
def access_list(user=Depends(admin_user)):
    with connect() as con:
        data=rows(con,'SELECT id,username,full_name,role,job_role,active FROM users ORDER BY id')
        from .permissions import effective
        for item in data:
            item['permissions']=effective(con,item)
            item['property_ids']=[x['property_id'] for x in rows(con,'SELECT property_id FROM property_grants WHERE user_id=?',(item['id'],))]
        return data

@router.get('/access/catalog')
def access_catalog(user=Depends(admin_user)):
    from .permissions import GROUPS, ACTIONS, ADMIN_ONLY, ADMIN_RESERVED, defaults
    return {'groups':[{'id':gid,'label':label,'actions':[{'key':gid+'.'+act,'label':ACTIONS.get(act,act),'locked':gid+'.'+act in ADMIN_RESERVED or gid in ADMIN_ONLY} for act in actions],
                       'admin_only':gid in ADMIN_ONLY} for gid,label,actions in GROUPS],
            'role_defaults':{role:defaults(role) for role in ('manager','accountant','collector','maintenance','viewer')}}

@router.put('/access/{ident}')
def access_update(ident:int,data:dict,user=Depends(admin_user)):
    job=enum(data.get('job_role'),'Vai trò',['manager','accountant','collector','maintenance','viewer'])
    grants=data.get('property_ids',[])
    if not isinstance(grants,list) or len(grants)>100:fail('Danh sách cơ sở không hợp lệ.')
    ids=[positive(x,'Cơ sở',1) for x in grants]
    from .permissions import ALL_KEYS,ADMIN_ONLY,ADMIN_RESERVED
    chosen=data.get('permissions')
    if chosen is not None:
        if not isinstance(chosen,dict) or set(chosen)!=ALL_KEYS or any(type(v) is not bool for v in chosen.values()):
            fail('Danh sách quyền không đầy đủ hoặc có giá trị không hợp lệ.')
        if any(chosen[k] for k in chosen if k.split('.')[0] in ADMIN_ONLY or k in ADMIN_RESERVED):
            fail('Các chức năng quản trị và phục hồi dữ liệu chỉ dành cho Admin.')
    with tx() as con:
        account=one(con,'SELECT * FROM users WHERE id=?',(ident,))
        if not account:fail('Tài khoản không tồn tại.',404)
        if account['role']=='admin':fail('Quản trị viên toàn hệ thống không cần phân quyền theo cơ sở.')
        for pid in ids:
            if not one(con,'SELECT 1 FROM properties WHERE id=?',(pid,)):fail('Cơ sở không tồn tại.')
        con.execute('UPDATE users SET job_role=? WHERE id=?',(job,ident))
        con.execute('DELETE FROM property_grants WHERE user_id=?',(ident,))
        for pid in set(ids):con.execute('INSERT INTO property_grants(user_id,property_id) VALUES(?,?)',(ident,pid))
        if chosen is not None:
            con.execute('DELETE FROM user_permissions WHERE user_id=?',(ident,))
            con.executemany('INSERT INTO user_permissions(user_id,permission_key,allowed) VALUES(?,?,?)',
                [(ident,key,int(allow)) for key,allow in chosen.items()])
        con.execute('DELETE FROM sessions WHERE user_id=?',(ident,))
        audit(con,user,'update','access',ident)
    return json_ok()

# 11 Manage local snapshots. Restore is STAGED and applied only on next server startup.
@router.get('/backups')
def list_backups(user=Depends(admin_user)):
    BACKUPS.mkdir(parents=True,exist_ok=True)
    return [{'name':p.name,'bytes':p.stat().st_size,'modified':datetime.fromtimestamp(p.stat().st_mtime).isoformat()}
            for p in sorted(BACKUPS.glob('troflow-*.sqlite3'),reverse=True)[:60]]

@router.post('/backups/create')
def backup_create(user=Depends(admin_user)):
    from scripts.backup_sqlite import make_backup
    path=make_backup(dbmodule.DB_PATH,BACKUPS)
    with tx() as con:audit(con,user,'create','backup',None,path.name)
    return json_ok(name=path.name)

@router.post('/backups/verify')
def backup_verify(data:dict,user=Depends(admin_user)):
    filename=trim(data.get('name'),'Tên backup',200,True)
    if not re.fullmatch(r'troflow-[A-Za-z0-9_.-]+\.sqlite3',filename):fail('Tên file không hợp lệ.')
    path=BACKUPS/filename
    if not path.is_file():fail('Không tìm thấy backup.',404)
    try:
        with closing(sqlite3.connect(f'file:{path}?mode=ro',uri=True)) as con:
            result=con.execute('PRAGMA integrity_check').fetchone()[0]
            valid=bool(con.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone())
    except sqlite3.DatabaseError:result='corrupted';valid=False
    return {'valid':result=='ok' and valid,'check':result,'bytes':path.stat().st_size}

@router.post('/backups/restore')
def backup_restore(data:dict,user=Depends(admin_user)):
    if data.get('confirm')!='KHOI PHUC':fail('Nhập chính xác KHOI PHUC để xác nhận.')
    filename=trim(data.get('name'),'Tên backup',200,True)
    result=backup_verify({'name':filename},user)
    if not result['valid']:fail('Backup không hợp lệ.')
    request_file=dbmodule.DB_PATH.parent/'.troflow-restore-request.json'
    request_file.write_text(json.dumps({'filename':filename,'requested_at':datetime.now().isoformat()}))
    os.chmod(request_file,0o600)
    with tx() as con:audit(con,user,'stage_restore','backup',None,filename)
    return json_ok(message='Đã lên lịch khôi phục. DỪNG và KHỞI ĐỘNG LẠI container để áp dụng. Backup hiện tại được giữ lại.')

@router.get('/backups/config')
def backup_config(user=Depends(admin_user)):
    with connect() as con:
        return {'backup_hour':(one(con,"SELECT value FROM app_settings WHERE key='backup_hour'") or {'value':'03:00'})['value']}

@router.put('/backups/config')
def backup_set_config(data:dict,user=Depends(admin_user)):
    backup_hour=trim(data.get('backup_hour'),'Giờ sao lưu',5,True)
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',backup_hour):fail('Giờ không hợp lệ (HH:MM).')
    with tx() as con:
        con.execute("INSERT INTO app_settings(key,value) VALUES('backup_hour',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(backup_hour,))
        audit(con,user,'update','backup_schedule',None,backup_hour)
    return json_ok()

# 12 Invoice schedule with per-property scheduling; creates DRAFT only.
@router.get('/schedules')
def list_schedules(user=Depends(authorized)):
    with connect() as con:
        records=rows(con,'''SELECT s.*,p.name property_name FROM invoice_schedules s
          JOIN properties p ON p.id=s.property_id ORDER BY p.name''')
        return [r for r in records if user['role']=='admin' or not user.get('grant_ids') or r['property_id'] in user['grant_ids']]

@router.put('/schedules/{property_id}')
def configure_schedule(property_id:int,data:dict,user=Depends(authorized)):
    right(user,property_id,'billing')
    day=positive(data.get('day_of_month',1),'Ngày lập hóa đơn',1,28)
    with tx() as con:
        if not one(con,'SELECT id FROM properties WHERE id=?',(property_id,)):fail('Cơ sở không tồn tại.',404)
        con.execute('''INSERT INTO invoice_schedules(property_id,active,day_of_month,require_readings)
          VALUES(?,?,?,1) ON CONFLICT(property_id) DO UPDATE SET active=excluded.active,
          day_of_month=excluded.day_of_month''',(property_id,1 if data.get('active') else 0,day))
        audit(con,user,'update','invoice_schedule',property_id)
    return json_ok()

@router.get('/schedules/events')
def schedule_events(period:str|None=None,user=Depends(authorized)):
    with connect() as con:
        records=rows(con,'SELECT e.*,p.name property_name FROM schedule_events e JOIN properties p ON p.id=e.property_id ORDER BY e.id DESC LIMIT 150')
        return [r for r in records if (not period or r['period']==period) and
                (user['role']=='admin' or not user.get('grant_ids') or r['property_id'] in user['grant_ids'])]

@router.post('/schedules/run/{property_id}')
def run_schedule(property_id:int,data:dict,user=Depends(authorized)):
    right(user,property_id,'billing')
    if user['role']!='admin' and not user['permissions'].get('invoices.create'):
        fail('Chưa được cấp quyền lập hóa đơn.',403)
    period=period_str(data.get('period',date.today().strftime('%Y-%m')))
    from .scheduler import run_billing_period
    result=run_billing_period(property_id,period,user)
    return json_ok(**result)


def advanced_page():
    return FileResponse(Path(__file__).parent/'static'/'advanced.html',headers={'Cache-Control':'no-cache'})

# 06 Printable PDF documents; private API route, Vietnamese font embedded in image.
def pdf_document(title,subtitle,lines,footer='Tài liệu quản lý nội bộ - không thay thế hóa đơn điện tử hợp pháp.'):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from reportlab.lib.units import mm
    from html import escape
    font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    if os.path.exists(font):
        if 'DejaVu' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('DejaVu',font))
        normal='DejaVu'
    else:normal='Helvetica'
    buff=io.BytesIO()
    doc=SimpleDocTemplate(buff,pagesize=A4,rightMargin=20*mm,leftMargin=20*mm,topMargin=22*mm,bottomMargin=22*mm)
    heading=ParagraphStyle('h',fontName=normal,fontSize=18,leading=27,textColor=colors.HexColor('#172c50'))
    sub=ParagraphStyle('sub',fontName=normal,fontSize=10,leading=17,textColor=colors.HexColor('#51637d'))
    small=ParagraphStyle('small',fontName=normal,fontSize=9,leading=14)
    story=[Paragraph(escape(title),heading),Spacer(1,5*mm),Paragraph(escape(subtitle),sub),Spacer(1,8*mm)]
    data=[]
    for label,value in lines:
        data.append([Paragraph(escape(str(label)),small),Paragraph(escape(str(value)),small)])
    table=Table(data,colWidths=[77*mm,94*mm],hAlign='LEFT')
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.HexColor('#e2e8f0')),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),10),
                ('BOTTOMPADDING',(0,0),(-1,-1),10),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#f4f8fc'))]))
    story.extend([table,Spacer(1,12*mm),Paragraph(escape(footer),sub)])
    doc.build(story)
    return buff.getvalue()

@router.get('/invoices/{ident}/pdf')
def invoice_pdf(ident:int,user=Depends(authorized)):
    """Private PDF from the same invoice image used for PNG and Zalo.

    This keeps details, historical unit prices, services, QR and transfer note
    consistent. Splits long invoices across A4 pages rather than shrinking text.
    """
    from .notify import _invoice, _invoice_png, _qr_details
    from .invoice_format import invoice_lines
    from PIL import Image as PILImage
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    with connect() as con:
        right(user,invoice_property(con,ident),'view')
        invoice=_invoice(con,ident)
        if not invoice:fail('Không tìm thấy hóa đơn.',404)
        details=invoice_lines(con,ident)
        qr=_qr_details(con,ident)
    png=_invoice_png(invoice,qr,details)
    source=PILImage.open(io.BytesIO(png)).convert('RGB')
    buf=io.BytesIO()
    pdf=canvas.Canvas(buf,pagesize=A4,pageCompression=1)
    page_w,page_h=A4
    margin=13*mm
    out_w=page_w-2*margin
    px_per_page=max(1,int((page_h-2*margin)*source.width/out_w))
    for top in range(0,source.height,px_per_page):
        cropped=source.crop((0,top,source.width,min(source.height,top+px_per_page)))
        out_h=cropped.height*out_w/cropped.width
        pdf.drawImage(ImageReader(cropped),margin,page_h-margin-out_h,width=out_w,height=out_h)
        pdf.showPage()
    pdf.save()
    return Response(buf.getvalue(),media_type='application/pdf',headers={
        'Content-Disposition':f'attachment; filename="HD{ident:05d}_{invoice["period"].replace("-","")}.pdf"',
        'Cache-Control':'private, no-store'})

@router.get('/handovers/{ident}/pdf')
def handover_pdf(ident:int,user=Depends(authorized)):
    with connect() as con:
        h=one(con,'''SELECT h.*,r.property_id,r.code room_code,p.name property_name,t.full_name tenant_name,t.phone tenant_phone,t.id_number tenant_id_number,t.photo_path tenant_photo_path
          FROM handovers h JOIN contracts c ON c.id=h.contract_id JOIN rooms r ON r.id=c.room_id
          JOIN properties p ON p.id=r.property_id JOIN tenants t ON t.id=c.tenant_id WHERE h.id=?''',(ident,))
        if not h:fail('Không tìm thấy biên bản.',404)
        right(user,h['property_id'],'view')
        rows_data=[('Cơ sở',h['property_name']),('Phòng',h['room_code']),('Người thuê',h['tenant_name']),
             ('Loại bàn giao','Nhận phòng' if h['handover_type']=='checkin' else 'Trả phòng'),
             ('Ngày bàn giao',h['handover_on']),('Hiện trạng / ghi chú',h['description']),
             ('Điện cuối kỳ',h['electric_final'] or 'Chưa ghi'),('Nước cuối kỳ',h['water_final'] or 'Chưa ghi'),
             ('Khấu trừ hư hỏng',f"{h['damage_amount']:,} VND"),('Người xác nhận',h['confirmed_by'])]
        pdf=pdf_document(f'BIÊN BẢN BÀN GIAO BB-{ident:05d}',f'TrọFlow • {h["handover_on"]}',rows_data,
                         'Biên bản nội bộ. Các bên nên ký xác nhận và lưu bản giấy/bản điện tử.')
    return Response(pdf,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="troflow-handover-{ident}.pdf"'})
