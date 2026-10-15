"""V5.4: Transfer ref, historical line-item rates, private PNG and Zalo attachments."""
import io
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app import db, notify
from app.invoice_format import transfer_reference, utility_rate, service_rows

class InvoiceV54Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=db.DB_PATH
  db.DB_PATH=Path(self.temp.name)/'troflow.db';db.init_db()
  self.client=TestClient(app)
  login=self.client.post('/api/auth/setup',json={'username':'root','full_name':'Manager','password':'StrongPassword987654'})
  assert login.status_code==200,login.text
  self.headers={'x-csrf-token':login.json()['csrf']}
  self.p=self.req('POST','properties',{'name':'Ngõ 303','electric_rate':4000,'water_rate':20000,'service_fee':0})['id']
  self.r=self.req('POST','rooms',{'property_id':self.p,'code':'P01','rent':3000000})['id']
  self.t=self.req('POST','tenants',{'full_name':'Trần Ngọc Trang','phone':'0982986102','id_number':'001234567890'})['id']
  self.c=self.req('POST','contracts',{'room_id':self.r,'tenant_id':self.t,'start_date':'2026-01-01','end_date':'2027-12-31','monthly_rent':3000000})['id']
  self.req('POST','readings',{'room_id':self.r,'period':'2026-10','electric_old':19551,'electric_new':19828,'water_old':834,'water_new':842})
  service=self.req('POST','v2/services',{'property_id':self.p,'name':'Wi-Fi 100Mbps','charge_type':'flat','unit_price':100000})['id']
  self.req('POST','v2/contract-services',{'contract_id':self.c,'service_id':service,'quantity':1})
  self.bank=self.req('POST','v6/banks',{'property_id':self.p,'bank_code':'970418','bank_name':'BIDV','holder':'NGUYEN THI NHUNG','account_number':'1250774410','is_default':1,'active':1})['id']
  self.req('POST','invoices/generate',{'period':'2026-10'})
  self.inv=self.req('GET','invoices')[0]
 def tearDown(self):
  self.client.close();db.DB_PATH=self.old;self.temp.cleanup()
 def req(self,method,path,payload=None):
  r=self.client.request(method,'/api/'+path,json=payload,headers=self.headers)
  self.assertEqual(r.status_code,200,(method,path,r.text))
  return r.json()
 def test_ascii_transfer_reference_vietqr_old_api_and_text(self):
  invoice={'tenant_name':'Trần Ngọc Trang','tenant_phone':'0982986102','room_code':'P01','id':2,'period':'2026-10'}
  self.assertEqual(transfer_reference(invoice),'TRANNGOCTRANG-P01-0982986102 HD00002 202610')
  self.assertEqual(transfer_reference({'tenant_name':'Đỗ Mỹ','tenant_phone':'+84 98 123 45','room_code':'A/01','id':123456,'period':'2026-01'}),'DOMY-A01-849812345 HD123456 202601')
  qr=self.req('GET',f'v6/invoices/{self.inv["id"]}/payment-qr')
  expected=f'TRANNGOCTRANG-P01-0982986102 HD{self.inv["id"]:05d} 202610'
  self.assertEqual(qr['content'],expected)
  self.assertEqual(parse_qs(urlparse(qr['qr_url']).query)['addInfo'][0],expected)
  self.assertNotIn('TROFLOW',qr['qr_url'].upper())
  self.assertEqual(self.req('GET',f'v2/invoices/{self.inv["id"]}/vietqr')['transfer_note'],expected)
 def test_rates_and_services_read_historical_snapshot(self):
  details=self.req('GET',f'v2/invoices/{self.inv["id"]}/lines')
  self.assertEqual(utility_rate(self.inv,details,'electric'),{'rate':4000,'estimated':False})
  self.assertEqual(utility_rate(self.inv,details,'water'),{'rate':20000,'estimated':False})
  self.assertEqual(service_rows(self.inv,details)[0]['label'],'Wi-Fi 100Mbps')
  self.req('PUT',f'properties/{self.p}',{'name':'Ngõ 303','electric_rate':9000,'water_rate':35000,'service_fee':0})
  with db.connect() as con:
   saved=notify.invoice_lines(con,self.inv['id'])
  self.assertEqual(utility_rate(self.inv,saved,'electric')['rate'],4000)
  self.assertEqual(utility_rate(self.inv,saved,'water')['rate'],20000)
  self.assertEqual(utility_rate(self.inv,[],'electric'),{'rate':4000,'estimated':True})
 def test_download_png_and_bot_image_content_match(self):
  uri=f'/api/v6/invoices/{self.inv["id"]}/image.png'
  self.assertEqual(TestClient(app).get(uri).status_code,401)
  with patch('app.notify.urllib.request.urlopen',side_effect=OSError('VietQR temporarily offline')):
   response=self.client.get(uri)
   self.assertEqual(response.status_code,200,response.text[:100] if response.status_code!=200 else '')
   self.assertEqual(response.headers['content-type'],'image/png')
   self.assertIn('attachment',response.headers['content-disposition'])
   self.assertTrue(response.content.startswith(b'\x89PNG\r\n\x1a\n'))
   width,height=Image.open(io.BytesIO(response.content)).size
   self.assertEqual(width,1080);self.assertGreater(height,1000)
   with db.connect() as con:
    invoice=notify._invoice(con,self.inv['id']);qr=notify._qr_details(con,self.inv['id']);lines=notify.invoice_lines(con,self.inv['id'])
   expected=notify._invoice_png(invoice,qr,lines)
   self.assertEqual(response.content,expected)
 def test_private_pdf_uses_same_invoice_image_layout(self):
  with patch('app.notify.urllib.request.urlopen',side_effect=OSError('offline')):
   response=self.client.get(f'/api/v2/invoices/{self.inv["id"]}/pdf')
  self.assertEqual(response.status_code,200,response.text[:80] if response.status_code!=200 else '')
  self.assertEqual(response.headers['content-type'],'application/pdf')
  self.assertTrue(response.content.startswith(b'%PDF-'))
  self.assertGreater(len(response.content),4000)
 def test_vietqr_image_is_embedded_when_online(self):
  from PIL import ImageDraw
  tmp=Image.new('RGB',(180,180),'white');dr=ImageDraw.Draw(tmp)
  dr.rectangle((60,60,119,119),fill='black')
  stream=io.BytesIO();tmp.save(stream,format='PNG')
  class Response:
   status=200
   headers={'Content-Type':'image/png'}
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,limit):return stream.getvalue()
  with patch('app.notify.urllib.request.urlopen',return_value=Response()):
   online=self.client.get(f'/api/v6/invoices/{self.inv["id"]}/image.png')
  with patch('app.notify.urllib.request.urlopen',side_effect=OSError('offline')):
   offline=self.client.get(f'/api/v6/invoices/{self.inv["id"]}/image.png')
  self.assertEqual(online.status_code,200)
  self.assertNotEqual(online.content,offline.content)
 def test_no_duplicate_service_rows_if_total_changed(self):
  details=[{'code':'service','label':'Wifi','quantity':1,'unit_price':100000,'amount':100000}]
  self.assertEqual(service_rows({'services':1000},details),[])
