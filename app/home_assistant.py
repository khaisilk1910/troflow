"""Home Assistant meter snapshot import.

Only admin can configure credentials or import data. REST reads current HA state,
never infers historical values. HA imports are provisional and never overwrite
manually entered or paid supplier bills.
"""
import json
import os
import re
import secrets
import urllib.request
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
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


def _period(offset):
    d = date.today()
    m = d.year * 12 + (d.month - 1) + offset
    return '%04d-%02d' % (m // 12, m % 12 + 1)


def _mapping(con, meter_id):
    meter = one(con, 'SELECT id,kind,active,property_id FROM utility_meters WHERE id=?',(meter_id,))
    if not meter:fail('Không tìm thấy công tơ.',404)
    if meter['kind']!='electric':fail('Đồng bộ này chỉ hỗ trợ công tơ điện tổng.',400)
    mapping = one(con,'SELECT * FROM ha_meter_mappings WHERE meter_id=?',(meter_id,))
    if not mapping:fail('Chưa cấu hình các sensor cho công tơ.',400)
    return meter, mapping


def _snapshot(mapping):
    data = {key:_sensor(mapping[key]) for key in MAPPING_KEYS}
    if data['new_entity'] < data['old_entity']:
        raise RuntimeError('Chỉ số cuối kỳ nhỏ hơn đầu kỳ; không nhập dữ liệu.')
    # These four HA sensors may represent billing-period adjustments. Their
    # identities and periods must be configured by the owner.
    return {'period':_period(mapping['period_offset']),
            'reading_old':float(data['old_entity']), 'reading_new':float(data['new_entity']),
            'billed_usage':float(data['usage_entity']),
            'bill_amount':int(data['amount_entity'].quantize(Decimal('1'), rounding=ROUND_HALF_UP))}


def sync_one(meter_id):
    with connect() as con:
        meter, mapping = _mapping(con, meter_id)
        if not meter['active'] or not mapping['enabled']:
            raise RuntimeError('Đồng bộ công tơ này đang tắt.')
    result = _snapshot(mapping)
    with tx() as con:
        # Recheck the active config and meter before storing values, in case
        # an admin edited mapping during the outbound HTTP requests.
        nowmeter, current = _mapping(con, meter_id)
        if not nowmeter['active'] or not current['enabled'] or any(current[k]!=mapping[k] for k in (*MAPPING_KEYS,'period_offset')):
            raise RuntimeError('Cấu hình công tơ đã thay đổi, vui lòng đồng bộ lại.')
        old=one(con,'SELECT id,origin,paid_amount FROM utility_meter_periods WHERE meter_id=? AND period=?',
                (meter_id,result['period']))
        note='Đồng bộ Home Assistant (tạm tính từ sensor; chưa phải hóa đơn nhà cung cấp).'
        if old and (old['origin']!='home_assistant' or old['paid_amount']):
            outcome='skipped_manual'
        elif old:
            con.execute('''UPDATE utility_meter_periods SET reading_old=?,reading_new=?,billed_usage=?,
                bill_amount=?,note=?,updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                (result['reading_old'],result['reading_new'],result['billed_usage'],result['bill_amount'],note,old['id']))
            outcome='updated'
        else:
            con.execute('''INSERT INTO utility_meter_periods
                (meter_id,period,reading_old,reading_new,billed_usage,bill_amount,paid_amount,note,origin)
                VALUES(?,?,?,?,?,?,0,?,'home_assistant')''',
                (meter_id,result['period'],result['reading_old'],result['reading_new'],result['billed_usage'],result['bill_amount'],note))
            outcome='created'
        con.execute('''UPDATE ha_meter_mappings SET last_sync_at=CURRENT_TIMESTAMP,last_error='',
             last_period=?,last_result=? WHERE meter_id=?''',(result['period'],outcome,meter_id))
    return {'ok':True,'result':outcome,**result}


def sync_automatic():
    """Hourly attempt; failure on one meter cannot stop processing other meters."""
    with tx() as con:
        now=datetime.now().strftime('%Y-%m-%d %H')
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
    values={}
    for key in MAPPING_KEYS:
        v=str(data.get(key,'')).strip().lower()
        if not ENTITY_RE.fullmatch(v):fail('Entity ID không hợp lệ: '+key+' (cần sensor.ten_sensor).')
        values[key]=v
    offset=data.get('period_offset',0)
    try:offset=int(offset)
    except (TypeError,ValueError):fail('Độ lệch tháng không hợp lệ.')
    if offset not in (-1,0):fail('Chỉ hỗ trợ kỳ hiện tại (0) hoặc tháng trước (-1).')
    enabled=int(bool(int(data.get('enabled',1))))
    auto_sync=int(bool(int(data.get('auto_sync',0))))
    with tx() as con:
        meter=one(con,'SELECT kind FROM utility_meters WHERE id=?',(meter_id,))
        if not meter or meter['kind']!='electric':fail('Không tìm thấy công tơ điện.',404)
        con.execute('''INSERT INTO ha_meter_mappings
            (meter_id,old_entity,new_entity,usage_entity,amount_entity,period_offset,enabled,auto_sync)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(meter_id) DO UPDATE SET
            old_entity=excluded.old_entity,new_entity=excluded.new_entity,usage_entity=excluded.usage_entity,
            amount_entity=excluded.amount_entity,period_offset=excluded.period_offset,
            enabled=excluded.enabled,auto_sync=excluded.auto_sync''',
            (meter_id,*(values[k] for k in MAPPING_KEYS),offset,enabled,auto_sync))
        audit(con,user,'update','ha_meter_mapping',meter_id)
    return {'ok':True}


@router.post('/preview/{meter_id}')
def preview(meter_id:int,user=Depends(admin_user)):
    with connect() as con:
        _meter,mapping=_mapping(con,meter_id)
    try:return {'ok':True,**_snapshot(mapping)}
    except RuntimeError as exc:return {'ok':False,'message':str(exc)}


@router.post('/sync/{meter_id}')
def manual_sync(meter_id:int,user=Depends(admin_user)):
    try:return sync_one(meter_id)
    except RuntimeError as exc:
        with tx() as con:
            con.execute('UPDATE ha_meter_mappings SET last_error=? WHERE meter_id=?',(str(exc)[:240],meter_id))
        fail(str(exc),400)
