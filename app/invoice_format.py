"""Shared financial formatting: invoice references and original bill line snapshots.

No schema changes: reads existing invoice_lines created by billing.py. Old V1 records
without line snapshots remain readable but must not invent a historic utility tariff.
"""
import re
import unicodedata
from .db import rows


def _ascii_token(value, max_length):
    normalized = unicodedata.normalize('NFKD', str(value or '').replace('Đ', 'D').replace('đ', 'd'))
    ascii_value = normalized.encode('ascii', 'ignore').decode('ascii').upper()
    return re.sub(r'[^A-Z0-9]', '', ascii_value)[:max_length]


def transfer_reference(invoice):
    """Portable VietQR ASCII addInfo; always preserve invoice ID and period.

    E.g. TRANG-P01-0982986102 HD00002 202610.
    Limit the identity segment to prevent extremely long bank transfer descriptions.
    """
    name = _ascii_token(invoice.get('tenant_name'), 24) or 'KHACH'
    room = _ascii_token(invoice.get('room_code'), 12) or 'PHONG'
    phone = _ascii_token(invoice.get('tenant_phone'), 15) or 'KHONGSDT'
    number = int(invoice['id'])
    period = str(invoice['period']).replace('-', '')
    if not re.fullmatch(r'\d{6}', period):
        raise ValueError('Ky hoa don khong hop le')
    return f'{name}-{room}-{phone} HD{number:05d} {period}'


def invoice_lines(con, invoice_id):
    return rows(con, '''SELECT label,code,quantity,unit_price,amount
       FROM invoice_lines WHERE invoice_id=? ORDER BY id''', (invoice_id,))


def utility_rate(invoice, lines, key):
    """Rate from immutable invoice_lines; no current property prices assumed."""
    matching = next((item for item in lines if item['code'] == key), None)
    if matching:
        return {'rate': matching['unit_price'], 'estimated': False}
    usage = float(invoice.get('electric_usage' if key == 'electric' else 'water_usage') or 0)
    total = float(invoice.get('electricity' if key == 'electric' else 'water') or 0)
    if usage > 0:
        return {'rate': round(total / usage), 'estimated': True}
    return {'rate': None, 'estimated': True}


def service_rows(invoice, lines):
    """Never display outdated service breakdown if it no longer equals bill total."""
    selected = [line for line in lines if line['code'] in ('service', 'base_service')]
    if selected and sum(int(item['amount']) for item in selected) == int(invoice.get('services') or 0):
        return selected
    return []
