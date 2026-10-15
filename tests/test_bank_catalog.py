"""VietQR dropdown regression tests; no dependency on network access."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import db, bank_catalog
from app.main import app


class TestBankCatalog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / 'data' / 'troflow.db'
        db.init_db()
        self.client = TestClient(app)
        setup = self.client.post('/api/auth/setup', json={
            'username': 'admin', 'full_name': 'Quản trị', 'password': 'pass-1234567890'})
        self.assertEqual(setup.status_code, 200, setup.text)
        self.headers = {'x-csrf-token': setup.json()['csrf']}
        prop = self.client.post('/api/properties', json={
            'name': 'Cơ sở 1', 'electric_rate': 4000, 'water_rate': 20000, 'service_fee': 0}, headers=self.headers)
        self.assertEqual(prop.status_code, 200, prop.text)
        self.prop_id = prop.json()['id']

    def tearDown(self):
        self.client.close()
        db.DB_PATH = self.old_path
        self.temp.cleanup()

    def test_included_banks_and_authorization(self):
        response = self.client.get('/api/v6/bank-catalog')
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['origin'], 'bundled')
        self.assertEqual(data['source'], bank_catalog.BANKS_URL)
        self.assertEqual(data['count'], 75)
        names = {b['bin']: b['shortName'] for b in data['banks']}
        self.assertEqual(names['970436'], 'Vietcombank')
        self.assertEqual(names['970422'], 'MBBank')
        self.assertEqual(names['970418'], 'BIDV')
        unauth = TestClient(app)
        self.assertIn(unauth.get('/api/v6/bank-catalog').status_code, (401, 403))
        unauth.close()

    def test_choose_bank_automatically_standardizes_bin_name_and_prevents_mismatch(self):
        payload = {'property_id': self.prop_id, 'catalog_bin': '970436',
                   'bank_code': '970436', 'bank_name': 'không phải ngân hàng đúng',
                   'holder': 'NGUYEN VAN A', 'account_number': '1234567890',
                   'is_default': 1, 'active': 1}
        created = self.client.post('/api/v6/banks', json=payload, headers=self.headers)
        self.assertEqual(created.status_code, 200, created.text)
        saved = self.client.get('/api/v6/banks').json()[0]
        self.assertEqual(saved['bank_name'], 'Vietcombank')
        self.assertEqual(saved['bank_code'], '970436')
        payload['bank_code'] = '970422'
        payload['account_number'] = '222222222'
        bad = self.client.post('/api/v6/banks', json=payload, headers=self.headers)
        self.assertEqual(bad.status_code, 400, bad.text)
        payload['catalog_bin'] = '000000'
        bad = self.client.post('/api/v6/banks', json=payload, headers=self.headers)
        self.assertEqual(bad.status_code, 400, bad.text)
        # Legacy bank codes/manual input must remain supported for existing users.
        payload.update({'catalog_bin': 'manual', 'bank_code': 'VCB', 'bank_name': 'Legacy Bank'})
        valid = self.client.post('/api/v6/banks', json=payload, headers=self.headers)
        self.assertEqual(valid.status_code, 200, valid.text)

    def test_refresh_mocked_response_and_offline_fallback(self):
        original = bank_catalog.get_catalog()['banks']
        remote = [{'bin': b['bin'], 'shortName': b['shortName'] + (' Live' if i == 0 else ''),
                   'name': b['name'], 'code': b['code'],
                   'transferSupported': int(b['transferSupported'])} for i, b in enumerate(original)]
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, *args): return json.dumps({'code': '00', 'data': remote}).encode()
        with patch('app.bank_catalog.urllib.request.urlopen', return_value=FakeResponse()) as mocked:
            result = self.client.post('/api/v6/bank-catalog/refresh', headers=self.headers, json={})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['origin'], 'cached')
        self.assertTrue(result.json()['banks'][0]['shortName'].endswith('Live'))
        self.assertEqual(mocked.call_args.kwargs['timeout'], 6)
        cache = bank_catalog._cached_path()
        self.assertTrue(cache.exists())
        self.assertEqual(self.client.get('/api/v6/bank-catalog').json()['origin'], 'cached')
        cache.write_text('{ corrupted', encoding='utf-8')
        self.assertEqual(self.client.get('/api/v6/bank-catalog').json()['origin'], 'bundled')

    def test_failed_refresh_keeps_offline_data(self):
        with patch('app.bank_catalog.urllib.request.urlopen', side_effect=OSError('offline')):
            resp = self.client.post('/api/v6/bank-catalog/refresh', headers=self.headers, json={})
        self.assertEqual(resp.status_code, 502, resp.text)
        self.assertEqual(self.client.get('/api/v6/bank-catalog').json()['count'], 75)

if __name__ == '__main__': unittest.main()
