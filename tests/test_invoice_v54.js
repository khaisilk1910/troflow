const assert=require('node:assert/strict'), vm=require('node:vm'), fs=require('node:fs'), path=require('node:path');
let source=fs.readFileSync(path.join(__dirname,'../app/static/app.js'),'utf8').replace(/\binit\(\);\s*$/,'');
const ctx={console,document:{addEventListener(){},querySelector(){return null}},window:{},setTimeout(){},Date,URLSearchParams,Number,String,Math,Array};vm.createContext(ctx);vm.runInContext(source,ctx);
const invoice={id:2,period:'2026-10',due_date:'2026-11-05',property_name:'Ngõ 303',property_address:'Hà Nội',tenant_name:'Trang',tenant_phone:'0982986102',room_code:'P01',electric_old:19551,electric_new:19828,electric_usage:277,water_old:834,water_new:842,water_usage:8,rent:3000000,electricity:1108000,water:160000,services:100000,adjustment:0,total:4368000,paid:0,balance:4368000,status:'published',note:''};
const bank={configured:true,bank_name:'BIDV',holder:'NGUYEN THI NHUNG',account_number:'1250774410',amount:4368000,content:'TRANG-P01-0982986102 HD00002 202610',qr_url:'https://img.vietqr.io/image/970418-1250774410-compact2.png'};
const lines=[{code:'electric',label:'Tiền điện',unit_price:4000,amount:1108000},{code:'water',label:'Tiền nước',unit_price:20000,amount:160000},{code:'service',label:'Wi-Fi',quantity:1,unit_price:100000,amount:100000}];
ctx.invoice=invoice;ctx.bank=bank;ctx.lines=lines;
const html=vm.runInContext('renderInvoicePaper(invoice,bank,lines)',ctx);
assert.match(html,/Chỉ số cũ: <strong>19\.551<\/strong> → Chỉ số mới: <strong>19\.828<\/strong>/);
assert.match(html,/Tiêu thụ: <strong>277 kWh<\/strong>/);
assert.match(html,/Đơn giá: <strong>4\.000 ₫\/kWh<\/strong>/);
assert.match(html,/Đơn giá: <strong>20\.000 ₫\/m³<\/strong>/);
assert.match(html,/Wi-Fi/);assert.match(html,/1 × <strong>100\.000 ₫<\/strong>/);
assert.match(html,/Tổng tiền phải thanh toán/);
assert.match(html,/TRANG-P01-0982986102 HD00002 202610/);
assert(!html.includes('Hạn thu'));
assert(!html.includes('Số dư cần thanh toán'));
assert(!html.includes('TROFLOW'));
assert(html.includes('status-unpaid'));
const css=fs.readFileSync(path.join(__dirname,'../app/static/styles.css'),'utf8');assert(css.includes('.invoice-head-status .status-unpaid'));
assert(source.includes('data-action="download-invoice-png"'));
assert(source.includes('/image.png'));
const html2=vm.runInContext('renderInvoicePaper({...invoice,tenant_name:"<script>X</script>"},bank,lines)',ctx);
assert(!html2.includes('<script>'));
console.log('Invoice V5.4 UI: rates, itemized services, status, QR, PNG action and XSS OK');
if(process.argv[2]){
const filename=path.resolve(process.argv[2]);const style=fs.readFileSync(path.join(__dirname,'../app/static/styles.css'),'utf8');
fs.writeFileSync(filename,`<!doctype html><html lang="vi"><meta charset="utf-8"><title>Hoa don TrọFlow</title><style>${style}</style><main style="max-width:765px;margin:15px auto;background:white;padding:14px">${html}</main>`);
}
