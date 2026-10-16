'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync(path.join(__dirname,'../app/static/integrations.js'),'utf8')
 .replace(/reload\(\)\.catch\(e=>\{root\.innerHTML=.*?\}\);/s,'');
const root={innerHTML:''};
const connectionEl={innerHTML:'',className:''};
const ctx={console,document:{getElementById(id){return id==='ui'?root:id==='zalo-connection-status'?connectionEl:null;},
 addEventListener(){},body:{insertAdjacentHTML(){}}},location:{search:'?page=zalo'},
 URLSearchParams,setTimeout(){},Date,Number,String,Math,Array};
vm.createContext(ctx);vm.runInContext(src,ctx,{timeout:3000});
const values=`config={enabled:1,bot_url:'http://host.docker.internal:3000',account_selection:'12345',
 username:'admin',media_url:'http://host.docker.internal:8001',credentials_configured:true};
 dest=[{id:3,name:'Chủ nhà',kind:'group',thread_id:'12345678',enabled:1,on_invoice:1,on_payment:1,on_ticket:1,welcome_status:'sent'}];
 logs=[{id:10,destination_name:'Chủ nhà',message:'Xác nhận',status:'sent',event:'destination_welcome'}];
 connection={status:'connected',connected:true,message:'Đã kết nối với bot',checked_at:'2026-10-16T00:00:00+00:00'};
 renderZalo();paintZaloConnection();`;
vm.runInContext(values,ctx,{timeout:3000});
assert(root.innerHTML.includes('id="zalo-connection-status"'));
assert(root.innerHTML.includes('Lưu &amp; kiểm tra')||root.innerHTML.includes('Lưu & kiểm tra'));
assert(root.innerHTML.includes('data-action="connection-check"'));
assert(root.innerHTML.includes('Xác nhận: Đã gửi'));
assert(connectionEl.innerHTML.includes('Đã kết nối Zalo Bot Server'));
assert(connectionEl.className.includes('is-connected'));
vm.runInContext(`connection={status:'unreachable',connected:false,message:'Không thấy server'};paintZaloConnection();`,ctx);
assert(connectionEl.innerHTML.includes('Không thấy server'));
assert(connectionEl.className.includes('is-disconnected'));
console.log('Zalo connection status, recipient confirmation status, mobile panel: OK');
