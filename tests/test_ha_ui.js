const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../app/static/app.js'),'utf8').replace(/\binit\(\);\s*$/,'');
const ctx={console,document:{addEventListener(){}},window:{},setTimeout(){},URLSearchParams,Date,Number,String,Math,Array};
vm.createContext(ctx);vm.runInContext(code,ctx,{timeout:4000});
const html=vm.runInContext(`(()=>{state.user={role:'admin'};state.data={properties:[{id:1,name:'Ngõ 303'}],utilitymeters:[{id:3,kind:'electric',property_name:'Ngõ 303',meter_number:'PD05000030540',customer_code:'PD05',active:1,bill_count:1}],utilitybills:[{id:4,kind:'electric',property_name:'Ngõ 303',meter_number:'PD05000030540',period:'2026-10',reading_old:3860.67,reading_new:4523.87,billed_usage:663.2,bill_amount:2113344,paid_amount:0,origin:'home_assistant'}],hamappings:[{meter_id:3,auto_sync:1,last_period:'2026-10',last_error:''}],utilityreport:{items:[],totals:{}}};state.utilityYear=2026;return pageUtilityMeters()})()`,ctx);
for(const required of ['data-utility="ha-config"','data-utility="ha-meter"','data-utility="ha-sync"','4,523.87','3,860.67','2,113,344','HA · tạm tính','HA · Tự động'])assert(html.includes(required),required);
assert.equal(vm.runInContext('amount(2113344)',ctx),'2,113,344 ₫');
assert.equal(vm.runInContext('readNum(4523.87)',ctx),'4,523.87');
console.log('Home Assistant UI: actions, indicators, periods and decimal grouping OK');
