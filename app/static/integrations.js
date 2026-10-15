'use strict';
const root=document.getElementById('ui');let csrf='',banks=[],dest=[],props=[],tenants=[],logs=[],config={},bankCatalog={banks:[],count:0};
const page=new URLSearchParams(location.search).get('page')==='banks'?'banks':'zalo';
const E=x=>String(x??'').replace(/[&<>"']/g,v=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[v]));
const req=async(path,method='GET',data)=>{const res=await fetch('/api/'+path,{method,credentials:'same-origin',headers:{...(method==='GET'?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf})},body:data===undefined?undefined:JSON.stringify(data)});const j=await res.json().catch(()=>({}));if(!res.ok)throw Error(j.detail||'Yêu cầu bị từ chối.');return j};
const flash=(msg,bad=false)=>{const n=document.getElementById('flash');n.textContent=msg;n.style.display='block';n.style.background=bad?'#a63d52':'#18344b';setTimeout(()=>{n.style.display='none'},4500)};
const btn=(label,attrs='',cls='')=>`<button class="btn ${cls}" ${attrs}>${E(label)}</button>`;
const field=(label,name,value='',type='text',extra='')=>`<label class="field">${E(label)}<input name="${E(name)}" type="${type}" value="${E(value)}" ${extra}></label>`;
const select=(label,name,value,arr)=>`<label class="field">${E(label)}<select name="${E(name)}">${arr.map(v=>`<option value="${E(v[0])}" ${String(value||'')===String(v[0])?'selected':''}>${E(v[1])}</option>`).join('')}</select></label>`;
const ck=(label,name,value)=>`<label><input type="checkbox" name="${E(name)}" ${value?'checked':''}> ${E(label)}</label>`;
const opts=(arr)=>arr.map(x=>[x.id,x.name]);
const formdata=form=>Object.fromEntries([...new FormData(form).entries()]);
const backdrop=html=>{document.getElementById('overlay')?.remove();document.body.insertAdjacentHTML('beforeend',`<div class="overlay" id="overlay"><div class="dialog">${html}</div></div>`)};
const close=()=>document.getElementById('overlay')?.remove();
async function run(fn){try{await fn()}catch(e){flash(e.message,true)}}
async function reload(){const me=await req('auth/me');if(me.user.role!=='admin'){root.textContent='Chỉ quản trị viên được truy cập cấu hình.';return}csrf=me.csrf;
 [props,tenants]=await Promise.all([req('properties'),req('tenants')]);
 if(page==='banks'){[banks,bankCatalog]=await Promise.all([req('v6/banks'),req('v6/bank-catalog')]);renderBanks()}else{[dest,config,logs]=await Promise.all([req('v6/zalo/destinations'),req('v6/zalo/settings'),req('v6/zalo/outbox')]);renderZalo()}}
function renderBanks(){root.innerHTML=`<div class="top"><div><div class="eyebrow">TRỌFLOW / TÀI CHÍNH</div><h1>Tài khoản ngân hàng & QR</h1><p class="muted">Quản lý nhiều tài khoản theo cơ sở. Hóa đơn ưu tiên tài khoản mặc định đang bật.</p></div><div class="actions">${btn('↻ Cập nhật danh sách VietQR','data-action="bank-catalog-refresh"')}${btn('+ Thêm tài khoản','data-action="bank-add"','primary')}</div></div>
 <div class="card"><div class="table-wrap"><table><thead><tr><th>Cơ sở</th><th>Ngân hàng</th><th>Chủ tài khoản</th><th>Số tài khoản</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>${banks.map(b=>`<tr><td><strong>${E(b.property_name)}</strong></td><td>${E(b.bank_name)}<br><small>${E(b.bank_code)}</small></td><td>${E(b.holder)}</td><td><strong>${E(b.account_number)}</strong></td><td><span class="tag ${b.active?'':'off'}">${b.active?(b.is_default?'Mặc định':'Đang dùng'):'Đã tắt'}</span></td><td><div class="actions">${btn('Xem QR',`data-action="bank-preview" data-id="${b.id}"`,'small-btn')}${btn('Sửa',`data-action="bank-edit" data-id="${b.id}"`,'small-btn')}${btn('Xóa',`data-action="bank-delete" data-id="${b.id}"`,'danger small-btn')}</div></td></tr>`).join('')}</tbody></table></div>${banks.length?'':'<p class="muted">Chưa có tài khoản. Nhấn “Thêm tài khoản”.</p>'}</div><p class="hint">Danh mục ${bankCatalog.count} ngân hàng/đơn vị từ <a href="https://www.vietqr.io/api-bank" target="_blank" rel="noopener noreferrer">VietQR</a> (cập nhật ${E(bankCatalog.retrieved_on||'đang dùng bản tích hợp')}). Trường “Hỗ trợ quét” phản ánh khả năng ứng dụng ngân hàng gửi tiền bằng cách quét QR, không đảm bảo mọi tài khoản đều nhận được tiền qua VietQR.</p><p class="hint">VietQR là mã chuyển khoản; không đồng nghĩa giao dịch đã được ngân hàng xác nhận. Chỉ ghi nhận “đã thu” khi đối soát thực tế.</p>`}
function previewBank(id){const b=banks.find(x=>x.id===id);if(!b)return;
 const qr=`https://img.vietqr.io/image/${encodeURIComponent(b.bank_code)}-${encodeURIComponent(b.account_number)}-compact2.png?accountName=${encodeURIComponent(b.holder)}`;
 backdrop(`<header><h2>QR tài khoản · ${E(b.property_name)}</h2>${btn('✕','data-action="close"')}</header>
 <div style="text-align:center"><img src="${E(qr)}" width="250" height="250" alt="QR nhận chuyển khoản" style="max-width:100%;object-fit:contain"><h3>${E(b.bank_name)}</h3><strong>${E(b.account_number)}</strong><p>${E(b.holder)}</p></div>
 <div class="warn">QR này chưa có số tiền/nội dung. Trên hóa đơn, TrọFlow sẽ tự điền số tiền còn phải thanh toán và mã hóa đơn.</div>`);
}
function bankOptions(selected='',query=''){
 const normalized=x=>String(x||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/đ/g,'d');
 const needle=normalized(query);
 const all=bankCatalog.banks||[];
 const filtered=all.filter(b=>normalized(`${b.shortName} ${b.name} ${b.bin} ${b.code}`).includes(needle));
 if(selected && !filtered.some(b=>b.bin===selected)){
   const current=all.find(b=>b.bin===selected);if(current)filtered.unshift(current);
 }
 const options=filtered.map(b=>`<option value="${E(b.bin)}">${E(b.shortName)} · ${E(b.bin)}${b.transferSupported?'':' · Chưa xác nhận hỗ trợ quét'}</option>`).join('');
 return `<option value="">-- Chọn ngân hàng (${filtered.length} kết quả) --</option>${options}<option value="manual">Khác / nhập BIN thủ công</option>`;
}
function editBank(id){
 const b=banks.find(x=>x.id===id)||{property_id:props[0]?.id||'',active:1,is_default:1};
 const isListed=(bankCatalog.banks||[]).some(x=>x.bin===b.bank_code);
 const selected=isListed?b.bank_code:(b.bank_code?'manual':'');
 backdrop(`<header><h2>${id?'Sửa':'Thêm'} tài khoản ngân hàng</h2>${btn('✕','data-action="close"')}</header>
  <form id="bank-form" data-id="${id||''}"><div class="grid">
  ${select('Cơ sở / Tòa nhà','property_id',b.property_id,opts(props))}
  <div class="field"><label for="bank-search">Tìm kiếm ngân hàng</label><input id="bank-search" type="search" autocomplete="off" placeholder="VD: Vietcombank, MB, 970436..."></div>
  <div class="field bank-picker-wrap"><label for="bank-picker">Ngân hàng / mã BIN VietQR <span class="required">*</span></label><select id="bank-picker" name="catalog_bin" required>${bankOptions(selected)}</select></div>
  ${field('Mã ngân hàng / BIN VietQR','bank_code',b.bank_code||'','text','id="bank-bin" required maxlength="20" inputmode="numeric"')}
  ${field('Tên ngân hàng','bank_name',b.bank_name||'','text','id="bank-name" required maxlength="120"')}
  ${field('Tên chủ tài khoản','holder',b.holder||'','text','required maxlength="120"')}
  ${field('Số tài khoản','account_number',b.account_number||'','text','required maxlength="34"')}
  </div><div class="checks">${ck('Đang sử dụng','active',b.active)}${ck('Là tài khoản mặc định','is_default',b.is_default)}</div>
  <div class="actions">${btn('Hủy','type="button" data-action="close"')}${btn('Lưu tài khoản','type="submit"','primary')}</div></form>
  <p class="hint">Chọn ngân hàng để tự điền BIN và tên; không cần nhớ mã 6 chữ số. Khi không tìm thấy, chọn “Khác / nhập BIN thủ công”. Hãy quét kiểm tra QR trước khi gửi cho khách thuê.</p>`);
 const picker=document.getElementById('bank-picker');picker.value=selected;
 updateBankFields(selected);
}
function updateBankFields(value){
 const bin=document.getElementById('bank-bin'),name=document.getElementById('bank-name');
 if(!bin||!name)return;
 const entry=(bankCatalog.banks||[]).find(b=>b.bin===value);
 if(entry){bin.value=entry.bin;name.value=entry.shortName;bin.readOnly=true;name.readOnly=true;}
 else if(value==='manual'){bin.readOnly=false;name.readOnly=false;}
 else {bin.value='';name.value='';bin.readOnly=true;name.readOnly=true;}
}
document.addEventListener('input',event=>{
 if(event.target.id!=='bank-search')return;
 const picker=document.getElementById('bank-picker');if(!picker)return;
 const selected=picker.value;
 picker.innerHTML=bankOptions(selected,event.target.value);
 picker.value=selected;
 // Keep an explicit choice; searching should not silently change the bank.
});
document.addEventListener('change',event=>{
 if(event.target.id==='bank-picker')updateBankFields(event.target.value);
});
function renderZalo(){root.innerHTML=`<div class="top"><div><div class="eyebrow">TRỌFLOW / TÍCH HỢP</div><h1>Thông báo Zalo</h1><p class="muted">Kết nối Zalo Bot Server đang chạy trên Ubuntu · Quản lý người nhận và nhật ký gửi</p></div><span class="tag ${config.enabled?'':'off'}">${config.enabled?'● Đang bật':'○ Đang tắt'}</span></div>
 <div class="card"><div class="top"><div><h2>Kết nối Zalo Bot Server</h2><p class="hint">Đăng nhập bằng session qua API của bot; thông tin mật khẩu không bao giờ được trả về giao diện.</p></div>${btn('Lưu cấu hình','type="submit" form="config-form"','primary')}</div><form id="config-form"><div class="grid">${field('Địa chỉ bot trên server','bot_url',config.bot_url,'url','required')}${field('Zalo ownId hoặc số điện thoại account đã đăng nhập','account_selection',config.account_selection||'','text','required')}${field('URL nội bộ TroFlow để bot tải ảnh','media_url',config.media_url||'','url','required')}${field('Username quản trị Zalo Bot','username',config.username||'','text','autocomplete="off"')}${field('Mật khẩu bot (để trống nếu giữ nguyên)','password','','password','autocomplete="new-password"')}</div><div class="checks">${ck('Bật gửi thông báo','enabled',config.enabled)}${ck('Gửi khi phát hành hóa đơn','invoice_enabled',config.invoice_enabled)}${ck('Gửi khi thu tiền','payment_enabled',config.payment_enabled)}</div><div class="hint">Trạng thái thông tin đăng nhập: <b>${config.credentials_configured?'Đã cấu hình':'Chưa cấu hình'}</b>${config.environment_credentials?' (qua biến môi trường)':''}. Bot sử dụng API <code>sendMessageByAccount</code> / <code>sendImageByAccount</code>. Gửi ảnh cần URL nội bộ hai chiều có thể truy cập.</div></form></div>
 <div class="card"><div class="top"><div><h2>Danh sách nơi nhận</h2><p class="hint">User hoặc nhóm Zalo, có thể gắn với khách thuê và cơ sở.</p></div>${btn('+ Thêm nơi nhận','data-action="dest-add"','primary')}</div>
 ${dest.length?dest.map(d=>`<div class="row"><div><strong>${E(d.name)} <span class="tag ${d.enabled?'':'off'}">${d.enabled?'Bật':'Tắt'}</span></strong><small>${d.kind==='group'?'Nhóm':'Người dùng'} · ID: ${E(d.thread_id)}${d.tenant_name?' · Khách: '+E(d.tenant_name):''}${d.property_name?' · '+E(d.property_name):''}<br>Hóa đơn: ${d.on_invoice?'Có':'Không'} · Thu tiền: ${d.on_payment?'Có':'Không'}</small></div><div class="actions">${btn(d.enabled?'Tắt nhanh':'Bật nhanh',`data-action="dest-toggle" data-id="${d.id}"`,'small-btn')}${btn('Gửi',`data-action="send" data-id="${d.id}"`,'small-btn primary')}${btn('Sửa',`data-action="dest-edit" data-id="${d.id}"`,'small-btn')}${btn('Xóa',`data-action="dest-delete" data-id="${d.id}"`,'danger small-btn')}</div></div>`).join(''):'<p class="muted">Chưa thêm nơi nhận.</p>'}</div>
 <div class="card"><div class="top"><div><h2>Nhật ký thông báo</h2><p class="hint">Đã gửi, đang chờ hoặc thất bại; có thể gửi lại thủ công khi lỗi.</p></div>${btn('Làm mới','data-action="reload"')}</div><div class="table-wrap"><table><thead><tr><th>ID</th><th>Nơi nhận</th><th>Nội dung</th><th>Trạng thái</th><th>Thời điểm</th><th></th></tr></thead><tbody>${logs.map(l=>`<tr><td>${l.id}</td><td>${E(l.destination_name||'Đã xóa nơi nhận')}</td><td><span class="break">${E(l.message.slice(0,150))}</span>${l.error?`<p class="error">${E(l.error)}</p>`:''}</td><td><span class="tag ${l.status==='sent'?'':'off'}">${E(l.status)}</span></td><td>${E(l.sent_at||l.created_at)}</td><td>${l.status==='failed'?btn('Gửi lại',`data-action="retry" data-id="${l.id}"`,'small-btn'):''}</td></tr>`).join('')}</tbody></table></div>${logs.length?'':'<p class="muted">Chưa có thông báo.</p>'}</div><div class="warn">Zalo Bot Server sử dụng API Zalo cá nhân không chính thức; có thể bị gián đoạn hoặc ảnh hưởng phiên đăng nhập khi Zalo thay đổi. Chỉ gửi cho người đã đồng ý nhận thông báo, không dùng để gửi hàng loạt tin nhắn không mong muốn.</div>`}
function editDest(id){const d=dest.find(x=>x.id===id)||{kind:'user',enabled:1,on_invoice:1,on_payment:1};backdrop(`<header><h2>${id?'Sửa':'Thêm'} nơi nhận Zalo</h2>${btn('✕','data-action="close"')}</header><form id="dest-form" data-id="${id||''}"><div class="grid">${field('Tên nơi nhận','name',d.name||'','text','required maxlength="120"')}${select('Loại','kind',d.kind,[['user','User'],['group','Nhóm']])}${field('ID Zalo (threadId / groupId, dạng số)','thread_id',d.thread_id||'','text','required inputmode="numeric"')}${select('Khách thuê liên kết (nếu có)','tenant_id',d.tenant_id||'',[['','Không gắn khách thuê'],...tenants.map(x=>[x.id,x.full_name+' · '+(x.phone||'')])])}${select('Cơ sở giới hạn (nếu có)','property_id',d.property_id||'',[['','Tất cả cơ sở'],...opts(props)])}</div><div class="checks">${ck('Bật nơi nhận','enabled',d.enabled)}${ck('Thông báo hóa đơn','on_invoice',d.on_invoice)}${ck('Thông báo thu tiền','on_payment',d.on_payment)}</div><div class="actions">${btn('Hủy','data-action="close" type="button"')}${btn('Lưu nơi nhận','type="submit"','primary')}</div></form><div class="warn">Dùng Zalo UserID/GroupID từ Zalo Bot Server, <b>không dùng số điện thoại khách thuê làm threadId</b>. Tên và số điện thoại chỉ để dễ nhận biết.</div>`)}
function sendDialog(id){const d=dest.find(x=>x.id===id);backdrop(`<header><h2>Gửi thông báo · ${E(d?.name)}</h2>${btn('✕','data-action="close"')}</header><form id="send-form"><input name="destination_id" type="hidden" value="${id}">${select('Hóa đơn đính kèm (nếu có)','invoice_id','',[['','Không đính kèm'],...(window.availableInvoices||[]).map(x=>[x.id,`HD-${x.id} · ${x.tenant_name} · ${x.period}`])])}<label class="field">Nội dung gửi<textarea name="message" rows="5" required maxlength="1800" placeholder="Xin chào, thông báo từ nhà trọ..."></textarea></label><div class="checks">${ck('Gửi kèm ảnh hóa đơn nếu đã chọn hóa đơn','include_image',true)}</div><div class="actions">${btn('Hủy','type="button" data-action="close"')}${btn('Đưa vào hàng đợi gửi','type="submit"','primary')}</div></form>`)}

document.addEventListener('submit',e=>{const f=e.target;if(!['bank-form','config-form','dest-form','send-form'].includes(f.id))return;e.preventDefault();run(async()=>{const data=formdata(f);for(const check of f.querySelectorAll('input[type=checkbox]'))data[check.name]=check.checked?1:0;
 if(f.id==='bank-form'){const id=f.dataset.id;await req('v6/banks'+(id?'/'+id:''),id?'PUT':'POST',data)}
 if(f.id==='config-form')await req('v6/zalo/settings','PUT',data);
 if(f.id==='dest-form'){const id=f.dataset.id;await req('v6/zalo/destinations'+(id?'/'+id:''),id?'PUT':'POST',data)}
 if(f.id==='send-form'){data.destination_id=Number(data.destination_id);if(data.invoice_id)data.invoice_id=Number(data.invoice_id);await req('v6/zalo/send','POST',data)}
 close();await reload();flash('Đã lưu. Thông báo được đưa vào hàng đợi nếu có yêu cầu gửi.');});});
document.addEventListener('click',e=>{const el=e.target.closest('[data-action]');if(!el)return;const action=el.dataset.action;const id=Number(el.dataset.id);run(async()=>{
 if(action==='close'){close();return}
 if(action==='reload'){await reload();return}
 if(action==='bank-add'){editBank();return}
 if(action==='bank-catalog-refresh'){bankCatalog=await req('v6/bank-catalog/refresh','POST',{});renderBanks();flash('Đã cập nhật '+bankCatalog.count+' ngân hàng từ VietQR.');return}
 if(action==='bank-preview'){previewBank(id);return}
 if(action==='bank-edit'){editBank(id);return}
 if(action==='bank-delete'){if(!confirm('Xóa tài khoản ngân hàng này?'))return;await req('v6/banks/'+id,'DELETE');await reload();return}
 if(action==='dest-add'){editDest();return}
 if(action==='dest-edit'){editDest(id);return}
 if(action==='dest-delete'){if(!confirm('Xóa nơi nhận này? Nhật ký vẫn được giữ.'))return;await req('v6/zalo/destinations/'+id,'DELETE');await reload();return}
 if(action==='dest-toggle'){const row=dest.find(x=>x.id===id);const {name,thread_id,kind,property_id,tenant_id,enabled,on_invoice,on_payment}=row;await req('v6/zalo/destinations/'+id,'PUT',{name,thread_id,kind,property_id,tenant_id,enabled:enabled?0:1,on_invoice,on_payment});await reload();return}
 if(action==='send'){window.availableInvoices=await req('invoices');sendDialog(id);return}
 if(action==='retry'){await req('v6/zalo/outbox/'+id+'/retry','POST',{});await reload();flash('Đã đưa lại vào hàng đợi.');return}
 })});
reload().catch(e=>{root.innerHTML='<div class="card error">'+E(e.message)+'</div>'});
document.body.insertAdjacentHTML('beforeend','<div id="flash" role="status"></div>');
