"""Master utility meters and official supplier bills; separate from tenant room meters.

Customer collected share is estimated pro-rata on paid invoice balance; only
separate collection ledgers can produce an exact utility-only cash breakdown.
"""
import sqlite3
from collections import defaultdict
from datetime import date
from fastapi import APIRouter, Depends
from .db import tx, connect, one, rows
from .main import authorized, fail, positive, decimal, trim, enum, period_str, date_str, audit, json_ok

router=APIRouter(prefix='/api',tags=['Công tơ tổng'])

def allowed(user,pid):
    if user['role']!='admin' and user.get('grant_ids') and int(pid) not in user['grant_ids']:
        fail('Không có quyền với cơ sở được chọn.',403)

def meter_values(data):
    return dict(property_id=positive(data.get('property_id'),'Cơ sở',1),
                kind=enum(data.get('kind'),'Loại công tơ',['electric','water']),
                meter_number=trim(data.get('meter_number'),'Số công tơ',80,True),
                customer_code=trim(data.get('customer_code'),'Mã khách hàng nhà cung cấp',80,True),
                supplier=trim(data.get('supplier'),'Nhà cung cấp',120),
                label=trim(data.get('label'),'Tên công tơ',120),
                notes=trim(data.get('notes'),'Ghi chú',500),
                active=positive(data.get('active',1),'Trạng thái',0,1))

def bills_values(data):
    old=decimal(data.get('reading_old',0),'Chỉ số đầu kỳ')
    new=decimal(data.get('reading_new',0),'Chỉ số cuối kỳ')
    if new<old:fail('Chỉ số cuối phải lớn hơn hoặc bằng chỉ số đầu.')
    usage=decimal(data.get('billed_usage',round(new-old,3)),'Sản lượng tính tiền')
    charge=positive(data.get('bill_amount',0),'Tiền nhà cung cấp tính')
    paid=positive(data.get('paid_amount',0),'Tiền thực trả')
    if paid>charge:fail('Tiền đã trả không được lớn hơn tiền nhà cung cấp tính.')
    paid_on=date_str(data.get('paid_on'),'Ngày thanh toán') if data.get('paid_on') else None
    if paid and not paid_on:fail('Vui lòng nhập ngày đã thanh toán cho nhà cung cấp.')
    if not paid and paid_on:fail('Chưa có số tiền đã trả, không được nhập ngày thanh toán.')
    return dict(period=period_str(data.get('period')),reading_old=old,reading_new=new,
                billed_usage=usage,bill_amount=charge,paid_amount=paid,paid_on=paid_on,
                note=trim(data.get('note'),'Ghi chú',500))

def require_meter(con,user,meter_id):
    item=one(con,'SELECT * FROM utility_meters WHERE id=?',(meter_id,))
    if not item:fail('Không tìm thấy công tơ.',404)
    allowed(user,item['property_id'])
    return item

@router.get('/utility-meters')
def list_meters(user=Depends(authorized)):
    with connect() as con:
        data=rows(con,'''SELECT m.*,p.name property_name,
        (SELECT COUNT(*) FROM utility_meter_periods b WHERE b.meter_id=m.id) bill_count
        FROM utility_meters m JOIN properties p ON p.id=m.property_id ORDER BY p.name,m.kind,m.id''')
    return [r for r in data if user['role']=='admin' or not user['grant_ids'] or r['property_id'] in user['grant_ids']]

@router.post('/utility-meters')
def add_meter(data:dict,user=Depends(authorized)):
    val=meter_values(data);allowed(user,val['property_id'])
    try:
        with tx() as con:
            if not one(con,'SELECT id FROM properties WHERE id=?',(val['property_id'],)):
                fail('Cơ sở không tồn tại.',404)
            ident=con.execute('INSERT INTO utility_meters ('+','.join(val)+') VALUES ('+','.join('?' for _ in val)+')',tuple(val.values())).lastrowid
            audit(con,user,'create','utility_meter',ident,val['meter_number'])
    except sqlite3.IntegrityError:
        fail('Công tơ này đã tồn tại tại cơ sở hoặc thông tin không hợp lệ.',409)
    return json_ok(id=ident)

@router.put('/utility-meters/{ident}')
def edit_meter(ident:int,data:dict,user=Depends(authorized)):
    val=meter_values(data);allowed(user,val['property_id'])
    try:
        with tx() as con:
            old=require_meter(con,user,ident)
            if old['property_id']!=val['property_id'] or old['kind']!=val['kind']:
                if one(con,'SELECT id FROM utility_meter_periods WHERE meter_id=? LIMIT 1',(ident,)):
                    fail('Không thể đổi loại/cơ sở khi công tơ đã có kỳ ghi. Hãy tạo công tơ mới.',409)
            con.execute('UPDATE utility_meters SET '+','.join(k+'=?' for k in val)+' WHERE id=?',(*val.values(),ident))
            audit(con,user,'update','utility_meter',ident,old['meter_number']+' -> '+val['meter_number'])
    except sqlite3.IntegrityError:fail('Trùng số công tơ tại cùng cơ sở hoặc dữ liệu không hợp lệ.',409)
    return json_ok()

@router.delete('/utility-meters/{ident}')
def delete_meter(ident:int,user=Depends(authorized)):
    with tx() as con:
        require_meter(con,user,ident)
        if one(con,'SELECT id FROM utility_meter_periods WHERE meter_id=?',(ident,)):
            fail('Công tơ đã có lịch sử kỳ thanh toán. Hãy ngừng sử dụng thay vì xóa.',409)
        con.execute('DELETE FROM utility_meters WHERE id=?',(ident,))
        audit(con,user,'delete','utility_meter',ident)
    return json_ok()

@router.get('/utility-bills')
def list_bills(year:int|None=None,user=Depends(authorized)):
    if year is not None and not 2000<=year<=2100:fail('Năm không hợp lệ.')
    with connect() as con:
        data=rows(con,'''SELECT b.*,m.kind,m.meter_number,m.customer_code,m.label,m.property_id,p.name property_name
          FROM utility_meter_periods b JOIN utility_meters m ON m.id=b.meter_id
          JOIN properties p ON p.id=m.property_id ORDER BY b.period DESC,m.kind,m.id''')
    return [r for r in data if (year is None or r['period'].startswith(str(year)+'-')) and
            (user['role']=='admin' or not user['grant_ids'] or r['property_id'] in user['grant_ids'])]

@router.post('/utility-bills')
def add_bill(data:dict,user=Depends(authorized)):
    mid=positive(data.get('meter_id'),'Công tơ',1);val=bills_values(data)
    try:
        with tx() as con:
            meter=require_meter(con,user,mid)
            if not meter['active']:fail('Công tơ đã ngừng sử dụng.',409)
            ident=con.execute('INSERT INTO utility_meter_periods(meter_id,'+','.join(val)+') VALUES (?,'+','.join('?' for _ in val)+')',(mid,*val.values())).lastrowid
            audit(con,user,'create','utility_bill',ident,f"meter={mid} period={val['period']}")
    except sqlite3.IntegrityError:
        fail('Công tơ đã có dữ liệu tháng/năm này, vui lòng sửa bản ghi cũ.',409)
    return json_ok(id=ident)

@router.put('/utility-bills/{ident}')
def edit_bill(ident:int,data:dict,user=Depends(authorized)):
    mid=positive(data.get('meter_id'),'Công tơ',1);val=bills_values(data)
    try:
        with tx() as con:
            old=one(con,'SELECT * FROM utility_meter_periods WHERE id=?',(ident,))
            if not old:fail('Không tìm thấy kỳ công tơ.',404)
            require_meter(con,user,old['meter_id'])
            require_meter(con,user,mid)
            con.execute('UPDATE utility_meter_periods SET meter_id=?, '+','.join(k+'=?' for k in val)+',updated_at=CURRENT_TIMESTAMP WHERE id=?',(mid,*val.values(),ident))
            audit(con,user,'update','utility_bill',ident,f"old_meter={old['meter_id']} old_period={old['period']}")
    except sqlite3.IntegrityError:fail('Công tơ đã có dữ liệu kỳ này (trùng tháng/năm).',409)
    return json_ok()

@router.delete('/utility-bills/{ident}')
def delete_bill(ident:int,user=Depends(authorized)):
    with tx() as con:
        old=one(con,'SELECT * FROM utility_meter_periods WHERE id=?',(ident,))
        if not old:fail('Không tìm thấy kỳ ghi.',404)
        require_meter(con,user,old['meter_id'])
        if old['paid_amount']:
            fail('Kỳ đã ghi nhận tiền trả nhà cung cấp. Phải điều chỉnh về 0 và lưu nhật ký trước khi xóa.',409)
        con.execute('DELETE FROM utility_meter_periods WHERE id=?',(ident,))
        audit(con,user,'delete','utility_bill',ident,old['period'])
    return json_ok()

@router.get('/utility-report')
def utility_report(year:int,property_id:int|None=None,user=Depends(authorized)):
    if not 2000<=year<=2100:fail('Năm không hợp lệ.')
    if user['role']!='admin' and not user['permissions'].get('utilitymeters.view',False):
        fail('Cần quyền xem công tơ trước khi xem báo cáo.',403)
    if property_id is not None:allowed(user,property_id)
    with connect() as con:
        props=rows(con,'SELECT id,name FROM properties ORDER BY id')
        allowed_props={p['id'] for p in props if (user['role']=='admin' or not user['grant_ids'] or p['id'] in user['grant_ids']) and (not property_id or property_id==p['id'])}
        if not allowed_props:
            return {'year':year,'items':[],'totals':{},'method':'Phân bổ số tiền khách đã trả theo tỷ lệ trên tổng hóa đơn; không phải đối soát riêng từng khoản điện nước.'}
        ph=','.join('?' for _ in allowed_props)
        # Actual supplier bills, per meter & month. Duplicate cycles blocked by UNIQUE.
        bills=rows(con,f'''SELECT m.property_id,b.period,m.kind,SUM(b.billed_usage) usage,
            SUM(b.bill_amount) charged,SUM(b.paid_amount) paid,COUNT(*) entries
            FROM utility_meter_periods b JOIN utility_meters m ON m.id=b.meter_id
            WHERE m.property_id IN ({ph}) AND b.period LIKE ? GROUP BY m.property_id,b.period,m.kind''',(*allowed_props,str(year)+'-%'))
        # Customer billing and collected share, with payments grouped before aggregation.
        customer=rows(con,f'''SELECT r.property_id,i.period,
            SUM(CASE WHEN i.status='published' THEN i.electricity ELSE 0 END) electric_charge,
            SUM(CASE WHEN i.status='published' THEN i.water ELSE 0 END) water_charge,
            SUM(CASE WHEN i.status='published' AND i.total>0 THEN
              i.electricity * (CAST(MIN(i.total, COALESCE(p.paid,0)) AS REAL)/i.total) ELSE 0 END) electric_collected,
            SUM(CASE WHEN i.status='published' AND i.total>0 THEN
              i.water * (CAST(MIN(i.total, COALESCE(p.paid,0)) AS REAL)/i.total) ELSE 0 END) water_collected
          FROM invoices i JOIN rooms r ON r.id=i.room_id
          LEFT JOIN (SELECT invoice_id,SUM(amount) paid FROM payments GROUP BY invoice_id) p ON p.invoice_id=i.id
          WHERE r.property_id IN ({ph}) AND i.period LIKE ? GROUP BY r.property_id,i.period''',(*allowed_props,str(year)+'-%'))
        meters=rows(con,f'''SELECT property_id,kind,COUNT(*) n FROM utility_meters
          WHERE property_id IN ({ph}) AND active=1 GROUP BY property_id,kind''',tuple(allowed_props))
    aggregate={}
    def entry(pid,period):
        return aggregate.setdefault((pid,period),{'property_id':pid,'property_name':next(p['name'] for p in props if p['id']==pid),
          'period':period,'electric_usage':0,'water_usage':0,'electric_charged':0,'water_charged':0,
          'electric_paid':0,'water_paid':0,'electric_billed':0,'water_billed':0,
          'electric_collected_est':0,'water_collected_est':0,'meter_entries':0})
    for r in bills:
        item=entry(r['property_id'],r['period']);k=r['kind']
        item[k+'_usage']+=r['usage'];item[k+'_charged']+=r['charged'];item[k+'_paid']+=r['paid'];item['meter_entries']+=r['entries']
    for r in customer:
        item=entry(r['property_id'],r['period'])
        for key in ('electric_charge','water_charge'):
            item[key.replace('_charge','_billed')]+=r[key]
        item['electric_collected_est']+=round(r['electric_collected'])
        item['water_collected_est']+=round(r['water_collected'])
    by_prop=defaultdict(int)
    for r in meters:by_prop[(r['property_id'],r['kind'])]=r['n']
    result=[]
    for item in sorted(aggregate.values(),key=lambda x:(x['period'],x['property_name']),reverse=True):
        item['missing_electric_bill']=(by_prop[(item['property_id'],'electric')]>0 or item['electric_billed']>0) and not any(r['property_id']==item['property_id'] and r['period']==item['period'] and r['kind']=='electric' for r in bills)
        item['missing_water_bill']=(by_prop[(item['property_id'],'water')]>0 or item['water_billed']>0) and not any(r['property_id']==item['property_id'] and r['period']==item['period'] and r['kind']=='water' for r in bills)
        item['customer_billed']=item['electric_billed']+item['water_billed']
        item['customer_collected_est']=item['electric_collected_est']+item['water_collected_est']
        item['supplier_charged']=item['electric_charged']+item['water_charged']
        item['supplier_paid']=item['electric_paid']+item['water_paid']
        item['accrual_margin']=item['customer_billed']-item['supplier_charged']
        item['cash_difference_est']=item['customer_collected_est']-item['supplier_paid']
        result.append(item)
    fields=('electric_usage','water_usage','customer_billed','customer_collected_est','supplier_charged','supplier_paid','accrual_margin','cash_difference_est')
    totals={k:sum(x[k] for x in result) for k in fields}
    return {'year':year,'items':result,'totals':totals,
            'method':'Tiền điện/nước thu từ khách là ước tính theo tỷ lệ hóa đơn đã thanh toán, không phải số dư thu thực tế riêng từng dịch vụ. Lãi lỗ dồn tích = đã tính cho khách - nhà cung cấp đã tính. Chênh lệch tiền = đã thu phân bổ - đã thực trả. Khi thiếu kỳ nhà cung cấp, chênh lệch có thể chưa đầy đủ.'}
