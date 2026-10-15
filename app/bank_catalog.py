"""Curated offline VietQR bank catalog and opt-in refresh from VietQR's public API.

Only the fixed provider endpoint can be fetched. Cache lives under /app/data so the
admin can refresh without rebuilding or requiring an Internet connection on startup.
"""
import json
import re
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import db

BANKS_URL = 'https://api.vietqr.io/v2/banks'
SNAPSHOT = Path(__file__).with_name('vietqr_banks.json')
_LOCK = threading.Lock()


def _list_from_json(payload):
    items = payload.get('data')
    if not isinstance(items, list) or not 30 <= len(items) <= 200:
        raise ValueError('Danh sách VietQR không hợp lệ.')
    result = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        bin_code = str(item.get('bin', '')).strip()
        short = str(item.get('shortName') or item.get('short_name') or '').strip()
        name = str(item.get('name') or '').strip()
        code = str(item.get('code') or '').strip()
        if not re.fullmatch(r'\d{6}', bin_code) or not short or not name or len(name) > 180 or len(short) > 70 or len(code) > 25 or bin_code in seen:
            continue
        seen.add(bin_code)
        result.append({'bin': bin_code, 'shortName': short, 'name': name,
                       'code': code, 'transferSupported': bool(item.get('transferSupported') == 1)})
    if len(result) < 30:
        raise ValueError('VietQR trả về quá ít mã hợp lệ.')
    return result


def _fallback():
    raw = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    banks = [{'bin': b, 'shortName': short, 'name': name, 'code': code,
              'transferSupported': bool(transfer)} for b, short, name, code, transfer in raw['banks']]
    return {'source': BANKS_URL, 'retrieved_on': raw['retrieved_on'],
            'origin': 'bundled', 'banks': banks, 'count': len(banks)}


def _cached_path():
    return db.DB_PATH.parent / 'vietqr-banks-cache.json'


def get_catalog():
    path = _cached_path()
    try:
        cached = json.loads(path.read_text(encoding='utf-8'))
        if cached.get('source') == BANKS_URL:
            clean = _list_from_json({'data': cached.get('banks', [])})
            # Always construct response anew instead of trusting writable metadata.
            return {'source': BANKS_URL, 'retrieved_on': str(cached.get('retrieved_on', '')),
                    'origin': 'cached', 'banks': clean, 'count': len(clean)}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return _fallback()


def refresh_catalog():
    # Never accept user-provided URLs. Fixed HTTPS endpoint and bounded body size.
    with _LOCK:
        request = urllib.request.Request(BANKS_URL, headers={'Accept': 'application/json', 'User-Agent': 'TroFlow/5.3'})
        with urllib.request.urlopen(request, timeout=6) as response:
            data = response.read(256 * 1024 + 1)
        if len(data) > 256 * 1024:
            raise ValueError('Danh sách ngân hàng vượt quá giới hạn.')
        payload = json.loads(data.decode('utf-8'))
        if payload.get('code') != '00':
            raise ValueError('VietQR không xác nhận phản hồi thành công.')
        banks = _list_from_json(payload)
        cache = {'source': BANKS_URL, 'retrieved_on': datetime.now(timezone.utc).date().isoformat(),
                 'banks': banks}
        path = _cached_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        try:
            tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
        return {'source': BANKS_URL, 'retrieved_on': cache['retrieved_on'], 'origin': 'cached',
                'banks': banks, 'count': len(banks)}
