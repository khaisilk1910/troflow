"""Home Assistant meter snapshot import.

Only admin can configure credentials or import data. Home Assistant provides
current states, not historical invoices: persisted snapshots identify a new
supplier cycle. Electric provisional readings and prior-month finalized values
are separate; water uses a monthly closing window. Manual edits are protected.
"""
import json
import os
import re
import secrets
import urllib.request
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends
from .db import connect, tx, one, rows
from .main import admin_user, audit, fail
from .notify import _credential_cipher, _network_base
from . import db as dbmodule

router = APIRouter(prefix='/api/ha', tags=['Home Assistant'])
ENTITY_RE = re.compile(r'^sensor\.[a-z0-9_]{1,180}$')
MAPPING_KEYS = ('old_entity', 'new_entity', 'usage_entity', 'amount_entity')
EXTRA_KEYS = ('prev_usage_entity', 'prev_amount_entity', 'prev_end_entity',
              'paid_on_entity', 'paid_amount_entity')
CONFIG_KEYS = (*MAPPING_KEYS, *EXTRA_KEYS, 'period_offset')
BUSINESS_TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def _today():
    return datetime.now(BUSINESS_TZ).date()


def _cipher():
    result=_credential_cipher()
    if result is None:raise RuntimeError('Cần cấu hình TROFLOW_SECRET_KEY_FILE để mã hóa token Home Assistant.')
    return result


def _path():
    return dbmodule.DB_PATH.parent / 'home-assistant-credentials.bin'


def _config():
    try:
        blob = _path().read_bytes()
        data = json.loads(_cipher().decrypt(blob))
        if not isinstance(data, dict):raise ValueError('Invalid configuration')
        return data
    except FileNotFoundError:
        return {}
    except Exception:
        raise RuntimeError('Không giải mã được cấu hình Home Assistant. Kiểm tra integration.key.')


def _save_config(cfg):
    dest = _path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = _cipher().encrypt(json.dumps(cfg).encode('utf-8'))
    temp = dest.with_name(dest.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        with temp.open('xb') as f:
            os.chmod(temp, 0o600)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)


def _check_url(value):
    if not isinstance(value, str) or not value.strip():fail('Nhập URL Home Assistant.')
    url = value.strip().rstrip('/')
    parsed = urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
        parsed.username or parsed.password or parsed.path not in ('', '/') or
        parsed.query or parsed.fragment or len(url) > 250):
        fail('URL phải là http(s)://máy-chủ:8123, không chứa đường dẫn hoặc thông tin đăng nhập.')
    return _network_base(url,'Home Assistant')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Home Assistant trả về chuyển hướng; không gửi token đến địa chỉ khác.')


def _ha_get(path):
    cfg = _config()
    if not cfg.get('url') or not cfg.get('token'):
        raise RuntimeError('Chưa lưu URL và Long-Lived Access Token của Home Assistant.')
    url = cfg['url'] + path
    request = urllib.request.Request(url, headers={
        'Authorization':'Bearer ' + cfg['token'], 'Accept':'application/json'
    }, method='GET')
    try:
        # No redirect: avoids accidentally sending the authorization header onward.
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(request, timeout=7) as r:
            if r.status != 200:raise RuntimeError('Home Assistant HTTP ' + str(r.status))
            payload = r.read(262145)
            if len(payload)>262144:raise RuntimeError('Phản hồi Home Assistant quá lớn.')
            return json.loads(payload)
    except HTTPError as exc:
        raise RuntimeError('Home Assistant HTTP ' + str(exc.code)) from None
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError('Không kết nối được Home Assistant: ' + str(exc.reason if isinstance(exc,URLError) else exc)[:110]) from None
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError('Home Assistant không trả JSON hợp lệ.') from None


def _sensor(entity):
    value = _ha_get('/api/states/' + quote(entity, safe='.'))
    if not isinstance(value, dict) or value.get('entity_id') != entity:
        raise RuntimeError('Home Assistant trả về sai entity_id: ' + entity)
    raw = str(value.get('state', '')).strip()
    # HA REST states are machine-readable: decimal point, no thousands grouping.
    if not re.fullmatch(r'\d{1,12}(?:\.\d{1,5})?', raw):
        raise RuntimeError(entity + ': sensor không phải số hợp lệ (' + raw[:35] + ').')
    val = Decimal(raw)
    if not val.is_finite() or val > Decimal('100000000000'):
        raise RuntimeError(entity + ': giá trị vượt giới hạn.')
    return val


def _mapping(con, meter_id):
    meter = one(con, 'SELECT id,kind,active,property_id FROM utility_meters WHERE id=?',(meter_id,))
    if not meter:fail('Không tìm thấy công tơ.',404)
    mapping = one(con,'SELECT * FROM ha_meter_mappings WHERE meter_id=?',(meter_id,))
    if not mapping:fail('Chưa cấu hình các sensor cho công tơ.',400)
    return meter, mapping


def _sensor_date(entity):
    # Date-valued HA sensor; never guess an invalid date.
    item = _ha_get('/api/states/' + quote(entity, safe='.'))
    if not isinstance(item, dict) or item.get('entity_id') != entity:
        raise RuntimeError('Home Assistant trả về sai entity_id: ' + entity)
    raw = str(item.get('state') or '').strip()
    if raw.lower() in ('', 'unknown', 'unavailable', 'none', 'null', '-'):
        return None
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            return date.fromisoformat(raw).isoformat()
        if re.fullmatch(r'\d{2}/\d{2}/\d{4}', raw):
            return datetime.strptime(raw,'%d/%m/%Y').date().isoformat()
        if re.fullmatch(r'\d{2}-\d{2}-\d{4}', raw):
            return datetime.strptime(raw,'%d-%m-%Y').date().isoformat()
        # HA sometimes renders an ISO datetime rather than just a date.
        if re.match(r'^\d{4}-\d{2}-\d{2}T', raw):
            return date.fromisoformat(raw[:10]).isoformat()
    except ValueError:
        pass
    raise RuntimeError(entity + ': ngày thanh toán không hợp lệ (YYYY-MM-DD hoặc DD/MM/YYYY).')


def _snapshot(mapping, kind='electric', today=None):
    today = today or _today()
    observed = {key:_sensor(mapping[key]) for key in MAPPING_KEYS}
    if observed['new_entity'] < observed['old_entity']:
        raise RuntimeError('Chỉ số cuối kỳ nhỏ hơn đầu kỳ; không nhập dữ liệu.')
    snapshot = {key: str(value) for key,value in observed.items()}
    result = {'period':_period(mapping['period_offset'], today),
              'reading_old':float(observed['old_entity']), 'reading_new':float(observed['new_entity']),
              'billed_usage':float(observed['usage_entity']),
              'bill_amount':int(observed['amount_entity'].quantize(Decimal('1'), rounding=ROUND_HALF_UP))}
    if kind == 'water':
        paid = _sensor(mapping['paid_amount_entity'])
        paid_on = _sensor_date(mapping['paid_on_entity'])
        paid = int(paid.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        result.update(paid_amount=paid, paid_on=paid_on)
        snapshot.update(paid_amount_entity=str(paid), paid_on_entity=paid_on or '')
    elif 1 <= today.day <= 7 and mapping.get('prev_usage_entity') and mapping.get('prev_amount_entity'):
        usage = _sensor(mapping['prev_usage_entity'])
        amount = _sensor(mapping['prev_amount_entity'])
        end = _sensor(mapping['prev_end_entity']) if mapping.get('prev_end_entity') else observed['old_entity']
        beginning = end - usage
        if beginning < 0:
            raise RuntimeError('Chỉ số cuối kỳ trước nhỏ hơn sản lượng kỳ trước.')
        previous = {'period':_period(-1,today), 'reading_old':float(beginning),
                    'reading_new':float(end), 'billed_usage':float(usage),
                    'bill_amount':int(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))}
        result['previous'] = previous
        snapshot.update(prev_usage_entity=str(usage),prev_amount_entity=str(amount),prev_end_entity=str(end))
    result['observed'] = snapshot
    return result


def _period(offset, on=None):
    d = on or _today()
    m = d.year * 12 + (d.month - 1) + offset
    return '%04d-%02d' % (m // 12, m % 12 + 1)


def _stored_snapshot(mapping):
    try:
        payload=json.loads(mapping.get('last_snapshot') or '{}')
        return payload if isinstance(payload,dict) else {}
    except (ValueError,TypeError):
        return {}


def _insert_ha(con,meter_id,values,note):
    con.execute('''INSERT INTO utility_meter_periods
        (meter_id,period,reading_old,reading_new,billed_usage,bill_amount,paid_amount,paid_on,note,origin)
        VALUES (?,?,?,?,?,?,?,?,?,'home_assistant')''',
        (meter_id,values['period'],values['reading_old'],values['reading_new'],
         values['billed_usage'],values['bill_amount'],values.get('paid_amount',0),values.get('paid_on'),note))


def _check_water_payment(values):
    if values['paid_amount'] > values['bill_amount']:
        raise RuntimeError('Số tiền nước đã trả lớn hơn số tiền nhà cung cấp tính.')
    if bool(values['paid_amount']) != bool(values['paid_on']):
        raise RuntimeError('Sensor thanh toán nước không khớp: cần cả số tiền đã trả và ngày thanh toán, hoặc cả hai trống/0.')


def _upsert_ha(con,meter_id,values,note,allow_paid=False):
    if one(con,'SELECT 1 FROM ha_period_deletions WHERE meter_id=? AND period=?',
           (meter_id,values['period'])):
        return 'skipped_deleted'
    old=one(con,'SELECT id,origin,paid_amount FROM utility_meter_periods WHERE meter_id=? AND period=?',
            (meter_id,values['period']))
    if old and (old['origin']!='home_assistant' or (old['paid_amount'] and not allow_paid)):
        return 'skipped_manual'
    if allow_paid:
        _check_water_payment(values)
    if old:
        # A previously paid HA invoice can be updated only by the water supplier
        # feed; never silently erase a recorded payment when HA resets its sensor.
        if allow_paid and (values.get('paid_amount',0) < old['paid_amount'] or values['bill_amount'] < old['paid_amount']):
            return 'skipped_payment_decrease'
        con.execute('''UPDATE utility_meter_periods SET reading_old=?,reading_new=?,billed_usage=?,
            bill_amount=?,paid_amount=?,paid_on=?,note=?,updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (values['reading_old'],values['reading_new'],values['billed_usage'],
             values['bill_amount'],values.get('paid_amount',0),values.get('paid_on'),note,old['id']))
        return 'updated'
    _insert_ha(con,meter_id,values,note)
    return 'created'


def sync_one(meter_id, today=None):
    today=today or _today()
    with connect() as con:
        meter, mapping = _mapping(con, meter_id)
        if not meter['active'] or not mapping['enabled']:
            raise RuntimeError('Đồng bộ công tơ này đang tắt.')
    result = _snapshot(mapping,meter['kind'],today)
    observed=result.pop('observed')
    previous_result=None
    with tx() as con:
        # Reject an obsolete HTTP response if settings changed while fetching.
        nowmeter, current = _mapping(con, meter_id)
        if not nowmeter['active'] or not current['enabled'] or nowmeter['kind']!=meter['kind'] or any(
            (current[k] or '') != (mapping[k] or '') for k in CONFIG_KEYS):
            raise RuntimeError('Cấu hình công tơ đã thay đổi, vui lòng đồng bộ lại.')
        old_snapshot=_stored_snapshot(current)
        if meter['kind']=='water':
            last_period=_period(-1,today)
            if 6<=today.day<=12:
                result['period']=last_period
                # Baseline on first poll. A current HA 'latest cycle' sensor is
                # not necessarily the previous month until a real change is seen.
                if not old_snapshot:
                    outcome='waiting_change'
                elif any(observed[k]!=old_snapshot.get(k) for k in
                         ('old_entity','new_entity','usage_entity','amount_entity')):
                    outcome=_upsert_ha(con,meter_id,result,
                        'Home Assistant · Nước kỳ trước (chỉ số nhà cung cấp đã chốt).',allow_paid=True)
                else:
                    # Payment can arrive after the readings, without any changes
                    # to the consumption figures.
                    existing=one(con,"SELECT id FROM utility_meter_periods WHERE meter_id=? AND period=? AND origin='home_assistant'",
                                 (meter_id,last_period))
                    if existing and any(observed[k]!=old_snapshot.get(k) for k in ('paid_amount_entity','paid_on_entity')):
                        outcome=_upsert_ha(con,meter_id,result,
                            'Home Assistant · Nước kỳ trước (đã cập nhật thanh toán).',allow_paid=True)
                    else:outcome='unchanged'
            else:
                outcome='outside_window'
                # After day 12, keep payment state current for the same imported
                # previous month, but never reassign meter readings outside cutoff.
                if today.day>12 and current.get('last_period')==last_period:
                    existing=one(con,'''SELECT id,origin FROM utility_meter_periods
                         WHERE meter_id=? AND period=?''',(meter_id,last_period))
                    if existing and existing['origin']=='home_assistant' and not one(con,
                        'SELECT 1 FROM ha_period_deletions WHERE meter_id=? AND period=?',(meter_id,last_period)) and any(
                        observed[k]!=old_snapshot.get(k) for k in ('paid_amount_entity','paid_on_entity')):
                        # Validate the payment date, not newer readings from a different cycle.
                        if bool(result['paid_amount']) != bool(result['paid_on']):
                            raise RuntimeError('Sensor thanh toán nước không khớp số tiền/ngày.')
                        con.execute('''UPDATE utility_meter_periods SET paid_amount=?,paid_on=?,updated_at=CURRENT_TIMESTAMP
                          WHERE id=? AND bill_amount>=? AND paid_amount<=?''',
                          (result['paid_amount'],result['paid_on'],existing['id'],result['paid_amount'],result['paid_amount']))
                        if con.execute('SELECT changes()').fetchone()[0]:outcome='payment_updated'
        else:
            result['period']=_period(mapping['period_offset'],today)
            outcome=_upsert_ha(con,meter_id,result,
                'Home Assistant · Điện tạm tính trong kỳ (chưa chốt hóa đơn nhà cung cấp).')
            # Official previous-period data is imported only when the prior-end
            # sensor CHANGES between polls within days 1..7. The first poll sets
            # a baseline instead of silently copying stale data from an old bill.
            official=result.get('previous')
            if official and mapping['period_offset']==0:
                if not old_snapshot:previous_result='waiting_change'
                elif observed['old_entity'] != old_snapshot.get('old_entity'):
                    previous_result=_upsert_ha(con,meter_id,official,
                        'Home Assistant · Điện kỳ trước đã chốt theo nhà cung cấp.')
                else:previous_result='unchanged'
            elif 1<=today.day<=7 and mapping['period_offset']==0:
                previous_result='not_configured'
        # Observe all sensor data even when the bill is protected from overwrite.
        con.execute('''UPDATE ha_meter_mappings SET last_sync_at=CURRENT_TIMESTAMP,last_error='',
             last_period=?,last_result=?,last_snapshot=? WHERE meter_id=?''',
             (result['period'] if outcome not in ('waiting_change','outside_window','unchanged') else
              (current['last_period'] if meter['kind']=='water' else result['period']),
              outcome,json.dumps(observed,sort_keys=True),meter_id))
    payload={k:v for k,v in result.items() if k!='previous'}
    return {'ok':True,'result':outcome,'previous_result':previous_result,
            'previous':result.get('previous'),**payload}


def sync_automatic():
    """Hourly attempt; failure on one meter cannot stop processing other meters."""
    with tx() as con:
        now=datetime.now(BUSINESS_TZ).strftime('%Y-%m-%d %H')
        previous=one(con,"SELECT value FROM app_settings WHERE key='ha_sync_hour'")
        if previous and previous['value']==now:return
        con.execute("INSERT INTO app_settings(key,value) VALUES('ha_sync_hour',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(now,))
        ids=[r['meter_id'] for r in rows(con,'SELECT meter_id FROM ha_meter_mappings WHERE enabled=1 AND auto_sync=1')]
    for meter_id in ids:
        try:
            sync_one(meter_id)
        except Exception as exc:
            with tx() as con:
                con.execute('UPDATE ha_meter_mappings SET last_error=? WHERE meter_id=?',(str(exc)[:240],meter_id))


@router.get('/config')
def get_config(user=Depends(admin_user)):
    cfg=_config()
    return {'url':cfg.get('url',''), 'configured':bool(cfg.get('token'))}


@router.put('/config')
def put_config(data:dict,user=Depends(admin_user)):
    url=_check_url(data.get('url',''))
    existing=_config()
    token=data.get('token','')
    if token:
        if not isinstance(token,str) or len(token)>4096 or '\n' in token or '\r' in token:
            fail('Token không hợp lệ.')
    else:
        token=existing.get('token','')
    if not token:fail('Nhập Long-Lived Access Token của Home Assistant.')
    _save_config({'url':url,'token':token})
    return {'ok':True,'configured':True}


@router.get('/test')
def test_connection(user=Depends(admin_user)):
    try:
        result=_ha_get('/api/')
        return {'ok':True,'message':result.get('message','Home Assistant phản hồi thành công.') if isinstance(result,dict) else 'Kết nối thành công.'}
    except RuntimeError as exc:
        return {'ok':False,'message':str(exc)}


@router.get('/mappings')
def list_mappings(user=Depends(admin_user)):
    with connect() as con:
        return rows(con,'SELECT * FROM ha_meter_mappings ORDER BY meter_id')


@router.put('/mappings/{meter_id}')
def set_mapping(meter_id:int,data:dict,user=Depends(admin_user)):
    with connect() as con:
        meter=one(con,'SELECT kind FROM utility_meters WHERE id=?',(meter_id,))
    if not meter:fail('Không tìm thấy công tơ.',404)
    values={}
    for key in MAPPING_KEYS:
        v=str(data.get(key,'')).strip().lower()
        if not ENTITY_RE.fullmatch(v):fail('Entity ID không hợp lệ: '+key+' (cần sensor.ten_sensor).')
        values[key]=v
    for key in EXTRA_KEYS:
        v=str(data.get(key,'') or '').strip().lower()
        if v and not ENTITY_RE.fullmatch(v):fail('Entity ID không hợp lệ: '+key)
        values[key]=v
    if meter['kind']=='electric':
        if bool(values['prev_usage_entity'])!=bool(values['prev_amount_entity']):
            fail('Cần cấu hình cả Tiêu thụ kỳ trước và Tiền điện kỳ trước.')
        if values['paid_on_entity'] or values['paid_amount_entity']:
            fail('Sensor thanh toán này chỉ dành cho đồng hồ nước.')
    else:
        if not values['paid_on_entity'] or not values['paid_amount_entity']:
            fail('Đồng hồ nước cần sensor Ngày thanh toán và Đã thanh toán kỳ hóa đơn.')
        if any(values[k] for k in ('prev_usage_entity','prev_amount_entity','prev_end_entity')):
            fail('Các sensor điện kỳ trước không áp dụng cho đồng hồ nước.')
    offset=data.get('period_offset',0)
    try:offset=int(offset)
    except (TypeError,ValueError):fail('Độ lệch tháng không hợp lệ.')
    if offset not in (-1,0):fail('Chỉ hỗ trợ kỳ hiện tại (0) hoặc tháng trước (-1).')
    if meter['kind']=='water':offset=-1
    try:
        enabled=int(bool(int(data.get('enabled',1))))
        auto_sync=int(bool(int(data.get('auto_sync',0))))
    except (TypeError,ValueError):fail('Giá trị bật/tắt không hợp lệ.')
    with tx() as con:
        old=one(con,'SELECT * FROM ha_meter_mappings WHERE meter_id=?',(meter_id,))
        changed=bool(old and any((old[k] or '') != (values[k] or '') for k in (*MAPPING_KEYS,*EXTRA_KEYS)))
        columns=(*MAPPING_KEYS,*EXTRA_KEYS,'period_offset','enabled','auto_sync')
        payload=(*(values[k] for k in (*MAPPING_KEYS,*EXTRA_KEYS)),offset,enabled,auto_sync)
        con.execute('''INSERT INTO ha_meter_mappings (meter_id,'''+','.join(columns)+''')
            VALUES ('''+','.join('?' for _ in range(len(columns)+1))+''')
            ON CONFLICT(meter_id) DO UPDATE SET '''+
            ','.join(k+'=excluded.'+k for k in columns), (meter_id,*payload))
        if changed:
            con.execute("UPDATE ha_meter_mappings SET last_snapshot='',last_period=NULL,last_result='mapping_changed' WHERE meter_id=?",(meter_id,))
        audit(con,user,'update','ha_meter_mapping',meter_id)
    return {'ok':True}


@router.post('/preview/{meter_id}')
def preview(meter_id:int,user=Depends(admin_user)):
    with connect() as con:
        _meter,mapping=_mapping(con,meter_id)
    try:
        result=_snapshot(mapping,_meter['kind'])
        result.pop('observed',None)
        return {'ok':True,**result}
    except RuntimeError as exc:return {'ok':False,'message':str(exc)}


@router.post('/sync/{meter_id}')
def manual_sync(meter_id:int,user=Depends(admin_user)):
    try:return sync_one(meter_id)
    except RuntimeError as exc:
        with tx() as con:
            con.execute('UPDATE ha_meter_mappings SET last_error=? WHERE meter_id=?',(str(exc)[:240],meter_id))
        fail(str(exc),400)
