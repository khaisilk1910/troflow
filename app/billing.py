"""Invoice engine, additive to v1. All amounts are integer VND."""
import calendar
import json
from datetime import date
from .db import one, rows


def month_range(period):
    year,month=map(int,period.split('-'))
    return date(year,month,1),date(year,month,calendar.monthrange(year,month)[1])


def calculate(con,contract,period,adjustment=0,discount=0,surcharge=0,require_reading=True):
    first,last=month_range(period)
    start=max(first,date.fromisoformat(contract['start_date']))
    finish=min(last,date.fromisoformat(contract['end_date']))
    if start>finish:
        raise ValueError('Hợp đồng không hoạt động trong kỳ này.')
    days_in_month=(last-first).days+1
    days_occupied=(finish-start).days+1
    contractual_rent=round(contract['monthly_rent']*days_occupied/days_in_month) if contract.get('prorate',0) else contract['monthly_rent']
    advance=one(con,"SELECT amount FROM rent_coverage WHERE contract_id=? AND period=? AND status='active'",(contract['id'],period))
    prepaid_rent=advance['amount'] if advance else 0
    if prepaid_rent and prepaid_rent!=contractual_rent:
        raise ValueError('Tiền thuê trả trước không khớp giá hợp đồng của kỳ này; cần đối soát.')
    rent=contractual_rent-prepaid_rent
    property_id=contract['property_id']
    prop=one(con,'SELECT * FROM properties WHERE id=?',(property_id,))
    reading=one(con,'SELECT * FROM readings WHERE room_id=? AND period=?',(contract['room_id'],period))
    if not reading and require_reading:
        raise ValueError(f"Phòng {contract['room_code']} chưa có chỉ số kỳ {period}.")
    eu=round(reading['electric_new']-reading['electric_old'],3) if reading else 0
    wu=round(reading['water_new']-reading['water_old'],3) if reading else 0
    electricity=round(eu*prop['electric_rate']);water=round(wu*prop['water_rate'])
    lines=[{'label':'Tiền thuê phòng','code':'rent','quantity':days_occupied if contract.get('prorate',0) else 1,
            'unit_price':contract['monthly_rent'],'amount':contractual_rent},
           *([{'label':'Đã thu tiền phòng trước ('+period+')','code':'prepaid_rent','quantity':1,
              'unit_price':-prepaid_rent,'amount':-prepaid_rent}] if prepaid_rent else []),
           {'label':'Tiền điện','code':'electric','quantity':eu,'unit_price':prop['electric_rate'],'amount':electricity},
           {'label':'Tiền nước','code':'water','quantity':wu,'unit_price':prop['water_rate'],'amount':water}]
    services=prop['service_fee']
    if services: lines.append({'label':'Phí dịch vụ cơ sở','code':'base_service','quantity':1,'unit_price':services,'amount':services})
    service_rows=rows(con,'''SELECT s.name,s.unit,s.charge_type,s.unit_price,cs.quantity
      FROM contract_services cs JOIN service_catalog s ON s.id=cs.service_id
      WHERE cs.contract_id=? AND cs.active=1 AND s.active=1''',(contract['id'],))
    num_people=one(con,'''SELECT COUNT(*) n FROM contract_residents WHERE contract_id=?
      AND moved_in<=? AND (moved_out IS NULL OR moved_out>=?)''',(contract['id'],last.isoformat(),first.isoformat()))['n']
    num_people=max(num_people,contract['occupants'] if not service_rows else num_people or 1)
    for s in service_rows:
        quantity=1 if s['charge_type']=='flat' else num_people if s['charge_type']=='person' else s['quantity']
        amount=round(quantity*s['unit_price'])
        services+=amount
        lines.append({'label':s['name'],'code':'service','quantity':quantity,'unit_price':s['unit_price'],'amount':amount})
    # Display previous outstanding amount; NEVER add it to this invoice's total:
    # adding it would double-count accounts receivable.
    balance=one(con,'''SELECT COALESCE(SUM(i.total-COALESCE(p.paid,0)),0) amount
       FROM invoices i LEFT JOIN (SELECT invoice_id,SUM(amount) paid FROM payments GROUP BY invoice_id) p ON p.invoice_id=i.id
       WHERE i.contract_id=? AND i.period<? AND i.status='published' ''',(contract['id'],period))['amount']
    if discount: lines.append({'label':'Giảm giá','code':'discount','quantity':1,'unit_price':-discount,'amount':-discount})
    if surcharge: lines.append({'label':'Truy thu / phụ thu','code':'surcharge','quantity':1,'unit_price':surcharge,'amount':surcharge})
    if adjustment: lines.append({'label':'Điều chỉnh','code':'adjustment','quantity':1,'unit_price':adjustment,'amount':adjustment})
    total=rent+electricity+water+services+adjustment-discount+surcharge
    if total<0: raise ValueError('Tổng hóa đơn không được âm.')
    following_year=first.year+(1 if first.month==12 else 0)
    following_month=1 if first.month==12 else first.month+1
    due=f'{following_year:04d}-{following_month:02d}-{contract["due_day"]:02d}'
    details={'days_occupied':days_occupied,'days_in_month':days_in_month,'prorated':bool(contract.get('prorate',0)),
             'occupants':num_people,'lines':lines,'carry_display_only':True,
             'contractual_rent':contractual_rent,'prepaid_rent':prepaid_rent}
    return {'rent':rent,'electricity':electricity,'water':water,'services':services,'adjustment':adjustment,
            'discount':discount,'surcharge':surcharge,'carried_debt':balance,'electric_usage':eu,'water_usage':wu,
            'total':total,'due_date':due,'calculation_json':json.dumps(details,ensure_ascii=False), 'lines':lines}


def create(con,contract,period,adjustment=0,note='',status='draft',discount=0,surcharge=0,require_reading=True):
    if one(con,'SELECT id FROM invoices WHERE contract_id=? AND period=?',(contract['id'],period)):
        return None
    calc=calculate(con,contract,period,adjustment,discount,surcharge,require_reading)
    data={k:v for k,v in calc.items() if k!='lines'}
    data.update(contract_id=contract['id'],room_id=contract['room_id'],period=period,note=note,status=status)
    if status=='published': data['published_at']=date.today().isoformat()
    cols=','.join(data)
    placeholders=','.join('?' for _ in data)
    inv_id=con.execute(f'INSERT INTO invoices({cols}) VALUES({placeholders})',tuple(data.values())).lastrowid
    for line in calc['lines']:
        con.execute('''INSERT INTO invoice_lines(invoice_id,label,code,quantity,unit_price,amount)
                       VALUES (?,?,?,?,?,?)''',(inv_id,line['label'],line['code'],line['quantity'],line['unit_price'],line['amount']))
    return inv_id
