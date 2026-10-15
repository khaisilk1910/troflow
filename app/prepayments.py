"""Advance rent receipts, accounted separately from monthly utility invoices."""
from datetime import date
from fastapi import APIRouter, Depends
from .db import connect,tx,one,rows
from .billing import month_range
from .main import authorized, fail, positive, date_str, trim, enum, audit, json_ok, CONTRACT_SQL
from .advanced import right, get_contract

router=APIRouter(prefix='/api/v2/prepayments',tags=['Rent prepayments'])

def months_between(start,end):
    a,b=map(int,start.split('-'));c,d=map(int,end.split('-'))
    count=(c-a)*12+d-b+1
    if count<1 or count>36:fail('Khoảng trả trước phải từ 1 đến 36 tháng.')
    return [f'{(a+(b-1+j)//12):04d}-{((b-1+j)%12+1):02d}' for j in range(count)]

@router.get('')
def list_prepayments(user=Depends(authorized)):
    with connect() as con:
        r=rows(con,'''SELECT x.*,b.paid_on,b.method,b.note,b.total batch_total,
          c.monthly_rent,c.status contract_status,t.full_name tenant_name,t.phone tenant_phone,
          r.code room_code,r.property_id,p.name property_name
          FROM rent_coverage x JOIN rent_prepayment_batches b ON b.id=x.batch_id
          JOIN contracts c ON c.id=x.contract_id JOIN tenants t ON t.id=c.tenant_id
          JOIN rooms r ON r.id=c.room_id JOIN properties p ON p.id=r.property_id
          ORDER BY x.period DESC,x.id DESC''')
        return [a for a in r if user['role']=='admin' or not user.get('grant_ids') or a['property_id'] in user['grant_ids']]

@router.post('')
def create_prepayment(data:dict,user=Depends(authorized)):
    cid=positive(data.get('contract_id'),'Hợp đồng',1)
    start=trim(data.get('start_period'),'Tháng bắt đầu',7,True)
    end=trim(data.get('end_period'),'Tháng kết thúc',7,True)
    from .main import period_str
    start=period_str(start);end=period_str(end)
    periods=months_between(start,end)
    paid_on=date_str(data.get('paid_on'),'Ngày nhận tiền')
    method=enum(data.get('method','transfer'),'Phương thức',['cash','transfer','other'])
    note=trim(data.get('note'),'Ghi chú',1000)
    with tx() as con:
        c=get_contract(con,cid)
        right(user,c['property_id'],'billing')
        if c['status']!='active':fail('Chỉ nhận tiền thuê trả trước cho hợp đồng đang hiệu lực.')
        totals=[]
        for period in periods:
            first,last=month_range(period)
            occupied_start=max(first,date.fromisoformat(c['start_date']))
            occupied_end=min(last,date.fromisoformat(c['end_date']))
            if occupied_start>occupied_end:fail(f'Hợp đồng không có hiệu lực trong tháng {period}.')
            if one(con,'SELECT id FROM invoices WHERE contract_id=? AND period=?',(cid,period)):
                fail(f'Tháng {period} đã có hóa đơn; không được trả trước lần nữa.')
            if one(con,"SELECT id FROM rent_coverage WHERE contract_id=? AND period=? AND status='active'",(cid,period)):
                fail(f'Tháng {period} đã có giao dịch trả trước.')
            days=(occupied_end-occupied_start).days+1
            month_days=(last-first).days+1
            cost=round(c['monthly_rent']*days/month_days) if c.get('prorate',0) else c['monthly_rent']
            if cost<1:fail(f'Tiền thuê của tháng {period} phải lớn hơn 0.')
            totals.append(cost)
        total=sum(totals)
        batch=con.execute('''INSERT INTO rent_prepayment_batches(contract_id,paid_on,method,total,note,created_by)
         VALUES(?,?,?,?,?,?)''',(cid,paid_on,method,total,note,user['id'])).lastrowid
        for period,cost in zip(periods,totals):
            con.execute('''INSERT INTO rent_coverage(batch_id,contract_id,period,amount)
                VALUES(?,?,?,?)''',(batch,cid,period,cost))
        audit(con,user,'receive','rent_prepayment',batch,f'{start} to {end}: {total}')
    return json_ok(id=batch,months=len(periods),total=total,periods=periods)

@router.post('/{ident}/refund')
def refund_prepayment(ident:int,data:dict,user=Depends(authorized)):
    refunded_on=date_str(data.get('refunded_on'),'Ngày hoàn tiền')
    reason=trim(data.get('reason'),'Lý do hoàn',500,True)
    with tx() as con:
        r=one(con,'''SELECT x.*,rm.property_id FROM rent_coverage x JOIN contracts c ON c.id=x.contract_id
        JOIN rooms rm ON rm.id=c.room_id WHERE x.id=?''',(ident,))
        if not r:fail('Không tìm thấy kỳ trả trước.',404)
        right(user,r['property_id'],'billing')
        if r['status']!='active':fail('Khoản này đã hoàn.')
        if one(con,'SELECT id FROM invoices WHERE contract_id=? AND period=?',(r['contract_id'],r['period'])):
            fail('Tháng đã có hóa đơn; cần điều chỉnh qua quy trình đối soát thay vì xóa khoản thu.')
        con.execute("UPDATE rent_coverage SET status='refunded',refunded_on=? WHERE id=?",(refunded_on,ident))
        audit(con,user,'refund','rent_prepayment',ident,f'{r["amount"]}: {reason}')
    return json_ok(refunded=r['amount'])
