"""Invoice engine, additive to v1. All amounts are integer VND."""
import calendar
import json
from datetime import date
from .db import one, rows


def month_range(period):
    year,month=map(int,period.split('-'))
    return date(year,month,1),date(year,month,calendar.monthrange(year,month)[1])


def previous_period(period):
    year, month = map(int, period.split('-'))
    return f'{year-1:04d}-12' if month == 1 else f'{year:04d}-{month-1:02d}'


def utility_period_for_invoice(invoice):
    """Old invoices keep legacy consumption period; V10 entries carry their own."""
    return invoice.get('utility_period') or invoice['period']


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
    meter_period = previous_period(period)
    _, meter_last = month_range(meter_period)
    # Do not bill a new tenant for the previous tenant's meter usage.
    eligible = date.fromisoformat(contract['start_date']) <= meter_last
    reading = (one(con,'SELECT * FROM readings WHERE room_id=? AND period=?',
                   (contract['room_id'],meter_period)) if eligible else None)
    if not reading and eligible and require_reading:
        raise ValueError(f"Phòng {contract['room_code']} chưa có chỉ số tiêu thụ {meter_period} để lập hóa đơn tiền phòng {period}.")
    eu=round(reading['electric_new']-reading['electric_old'],3) if reading else 0
    wu=round(reading['water_new']-reading['water_old'],3) if reading else 0
    electricity=round(eu*prop['electric_rate']);water=round(wu*prop['water_rate'])
    lines=[{'label':f'Tiền thuê phòng tháng {period[5:7]}/{period[:4]}','code':'rent','quantity':days_occupied if contract.get('prorate',0) else 1,
            'unit_price':contract['monthly_rent'],'amount':contractual_rent},
           *([{'label':'Đã thu tiền phòng trước ('+period+')','code':'prepaid_rent','quantity':1,
              'unit_price':-prepaid_rent,'amount':-prepaid_rent}] if prepaid_rent else []),
           {'label':f'Tiền điện tháng {meter_period[5:7]}/{meter_period[:4]}','code':'electric','quantity':eu,'unit_price':prop['electric_rate'],'amount':electricity},
           {'label':f'Tiền nước tháng {meter_period[5:7]}/{meter_period[:4]}','code':'water','quantity':wu,'unit_price':prop['water_rate'],'amount':water}]
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
    balance=one(con,'''SELECT COALESCE(SUM(MAX(0,i.total-COALESCE(p.paid,0))),0) amount
       FROM invoices i LEFT JOIN (SELECT invoice_id,SUM(amount) paid FROM payments GROUP BY invoice_id) p ON p.invoice_id=i.id
       WHERE i.contract_id=? AND i.period<? AND i.status='published' ''',(contract['id'],period))['amount']
    if discount: lines.append({'label':'Giảm giá','code':'discount','quantity':1,'unit_price':-discount,'amount':-discount})
    if surcharge: lines.append({'label':'Truy thu / phụ thu','code':'surcharge','quantity':1,'unit_price':surcharge,'amount':surcharge})
    if adjustment: lines.append({'label':'Điều chỉnh','code':'adjustment','quantity':1,'unit_price':adjustment,'amount':adjustment})
    total=rent+electricity+water+services+adjustment-discount+surcharge
    if total<0: raise ValueError('Tổng hóa đơn không được âm.')
    due=f'{first.year:04d}-{first.month:02d}-{contract["due_day"]:02d}'
    details={'days_occupied':days_occupied,'days_in_month':days_in_month,'prorated':bool(contract.get('prorate',0)),
             'occupants':num_people,'lines':lines,'carry_display_only':True,
             'contractual_rent':contractual_rent,'prepaid_rent':prepaid_rent,
             'utility_period':meter_period,'meter_exempt_new_tenant':not eligible}
    return {'rent':rent,'electricity':electricity,'water':water,'services':services,'adjustment':adjustment,
            'discount':discount,'surcharge':surcharge,'carried_debt':balance,'electric_usage':eu,'water_usage':wu,
            'total':total,'due_date':due,'utility_period':meter_period,'calculation_json':json.dumps(details,ensure_ascii=False), 'lines':lines}


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


def locked_reading(con,room_id,reading_period):
    # Historic rows (NULL) keep their original same-month binding.
    return one(con,'''SELECT id FROM invoices WHERE room_id=? AND status<>'void'
      AND COALESCE(utility_period,period)=? LIMIT 1''',(room_id,reading_period))
