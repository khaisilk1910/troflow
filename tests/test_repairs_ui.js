'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = file => fs.readFileSync(path.join(__dirname,'..','app','static',file),'utf8');
const tenant=read('tenant.js'),app=read('app.js'),settings=read('integrations.js');
assert(tenant.includes('form id="repair-form"'));
assert(tenant.includes('live[0].room_code'));
assert(!/id="repair-form"[^`]*name="room_id"/.test(tenant));
assert(tenant.includes("req('/api/tenant/tickets'"));
assert(tenant.includes('name="photos"') && tenant.includes('multiple'));
assert(tenant.includes('data-repair-photos'));
assert(app.includes('ticket-photos-input') && app.includes("apiMultipart('v8/tickets'"));
assert(settings.includes("'ticket_enabled'") && settings.includes("'on_ticket'"));

// Render the tenant portal using a browser-shaped DOM stub. This catches
// template mistakes in the new card without requiring the blocked localhost.
const nodes=new Map();
const getNode=(name)=>{
 if(!nodes.has(name))nodes.set(name,{innerHTML:'',hidden:false,addEventListener(){}});
 return nodes.get(name);
};
const fake={
 '/api/tenant/auth/me':{csrf:'demo'},
 '/api/tenant/home':{
  tenant:{name:'Trang',phone:'0982986102',property:'Ngõ 303'},
  contracts:[{contract_id:1,room_code:'P01',property_name:'Ngõ 303',start_date:'2025-01-01',end_date:'2028-12-31',monthly_rent:3000000}],
  owner:null,invoices:[],readings:[],submissions:[]
 },
 '/api/tenant/tickets':[{id:4,title:'Sự cố vòi nước',room_code:'P01',priority:'medium',status:'new',reported_at:'2026-10-15',photo_count:2}]
};
const ctx=vm.createContext({
 document:{querySelector:getNode,querySelectorAll:()=>[],addEventListener(){}},
 fetch:async url=>({ok:true,json:async()=>fake[url]}),
 console,Date,URL,FormData,setTimeout
});
vm.runInContext(tenant,ctx,{filename:'tenant.js'});
setImmediate(()=>{
 const html=getNode('#portal').innerHTML;
 assert(html.includes('id="repair-form"'),html.slice(-700));
 assert(html.includes('data-nav-tab="repairs"'));
 assert(html.includes('Phòng <b>P01 · Ngõ 303</b>'));
 assert(html.includes('Sự cố vòi nước'));
 assert(html.includes('Xem 2 ảnh'));
 assert(!html.includes('P09'));
 console.log('Maintenance UI: tenant room locked, photos, admin, Zalo toggles, DOM render: OK');
});
