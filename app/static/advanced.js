/* TrọFlow Pro: no external JS, zero front-end build step. */
'use strict';
const $=(q,el=document)=>el.querySelector(q);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>Number(n||0).toLocaleString('en-US')+' ₫';
const readNum=n=>Number(n||0).toLocaleString('en-US',{maximumFractionDigits:3});
const today=()=>new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Ho_Chi_Minh'});
const period=()=>today().slice(0,7);
const PAGES=[
 ['overview','Tổng quan','⌂'],['deposits','Tiền cọc','▣'],['prepayments','Thuê trả trước','◉'],['residents','Người ở','♙'],
 ['services','Phí dịch vụ','◈'],['meters','Điện & nước','ϟ'],['invoices','Hóa đơn','▤'],
 ['handovers','Bàn giao phòng','⚿'],['imports','Nhập Excel','⇥'],['access','Phân quyền','⚙'],
 ['automation','Tự động hóa','↻'],['backups','Sao lưu','▦'],['bank','VietQR','◉']];
const initialPage=new URLSearchParams(location.search).get('page');
const embedded=new URLSearchParams(location.search).get('embedded')==='1';
if(embedded)document.body.classList.add('embedded');
const state={page:PAGES.some(x=>x[0]===initialPage)?initialPage:'overview',data:{},auth:null,csrf:'',form:null,filters:{period:period(),meterYear:Number(period().slice(0,4))},busy:false};
async function api(path,method='GET',body){
 const args={method,credentials:'same-origin',headers:{'Accept':'application/json'}};
 if(method!=='GET')args.headers['X-CSRF-Token']=state.csrf;
 if(body!==undefined){if(body instanceof FormData)args.body=body;else{args.headers['Content-Type']='application/json';args.body=JSON.stringify(body);}}
 const r=await fetch('/api/'+path,args);let data;try{data=await r.json()}catch{throw Error('Phản hồi máy chủ không hợp lệ.');}
 if(!r.ok){const err=Error(typeof data.detail==='string'?data.detail:'Không thể xử lý thao tác.');err.status=r.status;throw err;}return data;
}
function toast(text,error=false){const el=document.createElement('div');el.className='toast'+(error?' error':'');el.textContent=text;$('#message').append(el);setTimeout(()=>el.remove(),4500);}
function opt(items,label){return items.map(i=>`<option value="${esc(i.id)}">${esc(label(i))}</option>`).join('');}
function formspec(name,label,type='text',options={},value=''){return {name,label,type,options,value};}
const fk={property:()=>state.data.properties||[],contract:()=>state.data.contracts||[],room:()=>state.data.rooms||[],service:()=>state.data.services||[],user:()=>state.data.access||[],invoice:()=>state.data.invoices||[]};
function field(item){const val=item.value??'',n=esc(item.name),label=esc(item.label),kind=item.type;
 let control='';
 if(kind==='select'){
  const options=typeof item.options==='string'?fk[item.options]?.()||[]:item.options||[];
  control=`<select name="${n}" ${item.required?'required':''}>${options.map(o=>`<option value="${esc(o.value??o.id)}" ${String(o.value??o.id)===String(val)?'selected':''}>${esc(o.label??o.name??o.full_name??o.code)}</option>`).join('')}</select>`;
 }else if(kind==='textarea')control=`<textarea name="${n}">${esc(val)}</textarea>`;
 else if(kind==='checkbox')control=`<input name="${n}" type="checkbox" ${val?'checked':''} value="1">`;
 else control=`<input name="${n}" type="${kind==='money'?'number':kind}" ${kind==='number'||kind==='money'?`step="any" ${item.name==='adjustment'?'':'min="0"'}`:''} value="${esc(val)}" ${item.required?'required':''}>`;
 return `<div class="field ${item.wide?'wide':''}"><label>${label}</label>${control}${item.hint?`<small>${esc(item.hint)}</small>`:''}</div>`;
}
function form(title,spec,save,label='Lưu thay đổi',hint=''){
 state.form={save};
 $('#modal').innerHTML=`<div class="modal-wrap" data-dismiss="true"><div class="dialog" role="dialog" aria-modal="true" aria-label="${esc(title)}">
 <div class="dialog-head"><h2>${esc(title)}</h2><button class="button" type="button" data-cmd="close">✕</button></div>
 <form id="pro-form"><div class="dialog-body">${hint?`<div class="note">${esc(hint)}</div>`:''}<div class="fields">${spec.map(field).join('')}</div></div>
 <div class="dialog-foot"><button type="button" class="button" data-cmd="close">Hủy</button><button type="submit" class="button primary">${esc(label)}</button></div></form></div></div>`;
 $('#pro-form input:not([type=hidden]),#pro-form select')?.focus();
}
function close(){state.form=null;$('#modal').innerHTML='';}
const C=(value,label)=>({value:String(value),label});
const pOpts=()=>state.data.properties?.map(x=>C(x.id,x.name))||[];
const cOpts=()=>state.data.contracts?.map(x=>C(x.id,`#${x.id} · ${x.property_name} / ${x.room_code} · ${x.tenant_name}`))||[];
const invOpts=()=>state.data.invoices?.map(x=>C(x.id,`HD-${x.id} · ${x.room_code} · ${x.period}`))||[];
const sOpts=()=>state.data.services?.map(x=>C(x.id,`${x.property_name} · ${x.name} (${money(x.unit_price)})`))||[];
const rOpts=()=>state.data.rooms?.map(x=>C(x.id,`${x.property_name} · ${x.code}`))||[];
const jsonForm=()=>{const fd=new FormData($('#pro-form'));const o=Object.fromEntries(fd.entries());for(const x of $$('input[type="checkbox"]','#pro-form'))o[x.name]=x.checked;return o;};
function $$(q,el=document){return [...(typeof el==='string'?$(el):el).querySelectorAll(q)];}
const pageAbility={overview:'dashboard.view',deposits:'deposits.view',prepayments:'prepayments.view',residents:'residents.view',services:'services.view',meters:'readings.view',invoices:'invoices.view',handovers:'handovers.view',imports:'imports.view',access:'access.view',automation:'schedules.view',backups:'backups.view',bank:'bank.view'};
const can=key=>state.auth?.user?.role==='admin'||Boolean(state.auth?.user?.permissions?.[key]);
const cmdAbility={'prepay-new':'prepayments.record','prepay-refund':'prepayments.refund','deposit-new':'deposits.record','resident-new':'residents.create','resident-leave':'residents.leave','service-new':'services.create','service-edit':'services.edit','service-assign':'services.assign','service-remove':'services.remove','meter-batch':'readings.batch','meter-photo-e':'readings.photos','meter-photo-w':'readings.photos','invoice-new':'invoices.create','invoice-edit':'invoices.edit','invoice-publish':'invoices.publish','proration':'contracts.proration','handover-new':'handovers.create','handover-photo':'files.upload','schedule-new':'schedules.edit','schedule-run':'schedules.execute','backup-create':'backups.create','backup-verify':'backups.verify','backup-restore':'backups.restore','backup-config':'backups.edit','bank-edit':'bank.edit','access-edit':'access.edit'};
function btn(label,cmd,id='',style=''){if(cmdAbility[cmd]&&!can(cmdAbility[cmd]))return '';return `<button type="button" class="button ${style}" data-cmd="${esc(cmd)}" data-id="${esc(id)}">${esc(label)}</button>`;}
function badge(text,kind=''){return `<span class="pill ${kind}">${esc(text)}</span>`;}
function table(headers,records){return `<div class="panel"><div class="table-scroll"><table class="data"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${records.length?records.join(''):`<tr><td colspan="${headers.length}"><div class="empty">Chưa có dữ liệu. Bạn có thể tạo bản ghi mới ở phía trên.</div></td></tr>`}</tbody></table></div></div>`;}
function header(title,desc,action=''){return `<div class="pagehead"><div><div class="eyebrow">TRỌFLOW WORKSPACE · VERSION 5.0</div><h1>${esc(title)}</h1><p>${esc(desc)}</p></div><div class="btnrow">${action}</div></div>`;}
function panel(title,description,content){return `<section class="panel"><div class="panelhead"><div><strong>${esc(title)}</strong><p>${esc(description)}</p></div></div><div class="panelbody">${content}</div></section>`;}
function tenantIdentity(x){
 const photo=x.tenant_photo_path;
 const meta=[x.tenant_phone||'',x.tenant_id_number?'CCCD: '+x.tenant_id_number:''].filter(Boolean).join(' · ');
 return `<span style="display:inline-flex;align-items:center;gap:8px;max-width:310px">${photo?`<img src="/api/v2/files/${encodeURIComponent(photo)}" alt="Ảnh khách thuê" style="width:34px;height:34px;object-fit:cover;border-radius:9px">`:''}<span><strong>${esc(x.tenant_name||'Chưa rõ')}</strong>${meta?`<br><small style="color:#75839a;line-height:1.5">${esc(meta)}</small>`:''}</span></span>`;
}
function pageOverview(){let s=state.data.summary||{},d=state.data;
 const kpis=[['Số cơ sở',s.properties?.length||0,'▣'],['Hóa đơn nháp',s.drafts||0,'▤'],['Phòng thiếu chỉ số',s.missing_readings?.length||0,'ϟ'],['Hợp đồng cần đối chiếu cọc',s.unsettled_deposits||0,'◈']];
 const cards=kpis.map(([label,value,icon])=>`<div class="kpi"><span class="symbol">${icon}</span><div class="hint">${label}</div><strong>${value}</strong><small>Cập nhật từ cơ sở dữ liệu thực</small></div>`).join('');
 return header('Trung tâm vận hành','Quản lý công nợ, vận hành, tự động hóa và kiểm soát dữ liệu trong một không gian làm việc.')+`<div class="kpis">${cards}</div><div class="grid2">${panel('Việc cần chú ý','Chỉ số điện nước chưa nhập trong kỳ hiện tại',(s.missing_readings||[]).length?`<div class="list">${s.missing_readings.map(x=>`<div class="list-row"><strong>${esc(x.property_name)} · phòng ${esc(x.code)}</strong>Thiếu chỉ số tháng ${period()}</div>`).join('')}</div>`:'<div class="note success">Không phát hiện phòng đang thuê thiếu chỉ số tháng này.</div>')}${panel('Nâng cấp đang hoạt động','12 nhóm nghiệp vụ đã được đưa vào API và giao diện',`<div class="tile-list">${[['01','Sổ cọc & hoàn cọc'],['02','Tiền phòng theo ngày'],['03','Phí dịch vụ riêng'],['04','Người ở cùng phòng'],['05','Chỉ số hàng loạt'],['06','Hóa đơn nháp / PDF'],['07','VietQR'],['08','Bàn giao trả phòng'],['09','Nhập Excel'],['10','Phân quyền'],['11','Sao lưu, phục hồi'],['12','Lập hóa đơn lịch']].map(x=>`<div class="tile"><strong>${x[0]} · ${x[1]}</strong><p>Sử dụng từ thanh điều hướng.</p></div>`).join('')}</div>`)}</div>`;
}
function pageDeposits(){const list=state.data.balances||[], tx=state.data.deposits||[];
 return header('Quản lý tiền cọc','Theo dõi cọc theo từng hợp đồng, thu cọc còn thiếu, khấu trừ và hoàn cọc.',btn('+ Ghi giao dịch','deposit-new','','primary'))+
 `<div class="note">Số dư cọc là số đã thu trừ đi tiền hoàn/khấu trừ. Không tự coi “mức cọc hợp đồng” là khoản thực thu.</div>`+
 table(['HỢP ĐỒNG','NGƯỜI THUÊ','CỌC YÊU CẦU','ĐÃ THU','ĐANG GIỮ','THIẾU CỌC'],list.map(x=>`<tr><td><strong>${esc(x.property_name)} / ${esc(x.room_code)}</strong></td><td>${tenantIdentity(x)}</td><td class="money">${money(x.required_amount)}</td><td>${money(x.received)}</td><td class="money">${money(x.held)}</td><td>${x.missing?badge(money(x.missing),'orange'):badge('Đủ')}</td></tr>`))+
 panel('Lịch sử giao dịch cọc','Sổ quỹ chỉ bổ sung, không sửa/xóa giao dịch cũ',tx.length?tx.slice(0,30).map(x=>`<div class="list-row"><strong>${tenantIdentity(x)} · ${esc(x.room_code)} — ${money(x.amount)}</strong>${esc({receive:'Thu cọc',refund:'Hoàn cọc',deduct:'Khấu trừ'}[x.kind])} · ${esc(x.transacted_on)} · ${esc(x.note)}</div>`).join(''):'Chưa có giao dịch.');
}
function pagePrepayments(){const list=state.data.prepayments||[];
 const received=list.filter(x=>x.status==='active').reduce((v,x)=>v+Number(x.amount),0);
 return header('Tiền thuê trả trước','Thu tiền phòng theo nhiều tháng hoặc theo quý; điện, nước và dịch vụ tiếp tục lên hóa đơn từng tháng.',btn('+ Thu trước tiền phòng','prepay-new','','primary'))+
 `<div class="note success"><b>Đang phân bổ: ${money(received)}</b> · Mỗi tháng đã trả trước ghi số tiền phòng phải thu = 0. Điện, nước, dịch vụ vẫn được tính đúng tháng. Các khoản trả trước nằm ngoài sổ thanh toán hóa đơn, không cộng tiền phòng lần hai.</div>`+
 table(['PHÒNG / NGƯỜI THUÊ','THÁNG ÁP DỤNG','TIỀN PHÒNG ĐÃ THU','THỜI ĐIỂM THU','TRẠNG THÁI',''],list.map(x=>`<tr><td><strong>${esc(x.property_name)} / ${esc(x.room_code)}</strong><br><small class="muted">${tenantIdentity(x)}</small></td><td>${esc(x.period)}</td><td class="money">${money(x.amount)}</td><td>${esc(x.paid_on)} · ${esc(x.method)}</td><td>${x.status==='active'?badge('Đã trả trước'):badge('Đã hoàn','orange')}</td><td>${x.status==='active'?btn('Hoàn kỳ','prepay-refund',x.id):''}</td></tr>`));
}
function pageResidents(){const list=state.data.residents||[];
 return header('Danh sách người ở','Lưu người đại diện và những người cùng cư trú, ngày vào/ngày rời đi, số giấy tờ.',btn('+ Thêm người ở','resident-new','','primary'))+
 table(['HỢP ĐỒNG','HỌ TÊN','ĐIỆN THOẠI','CCCD','NGÀY VÀO','NGÀY RỜI','THAO TÁC'],list.map(x=>`<tr><td>${esc(x.room_code)}<br><small class="muted">${esc(x.property_name)}</small></td><td><strong>${esc(x.full_name)}</strong>${x.is_primary?' '+badge('Đại diện'):''}</td><td>${esc(x.phone)}</td><td>${esc(x.id_number)}</td><td>${esc(x.moved_in)}</td><td>${x.moved_out?esc(x.moved_out):badge('Đang ở')}</td><td><div class="actions">${!x.moved_out&&!x.is_primary?btn('Báo rời','resident-leave',x.id):''}</div></td></tr>`));
}
function pageServices(){const list=state.data.services||[],assigned=state.data.assigned||[];
 return header('Biểu phí dịch vụ','Cấu hình phí theo phòng, theo người hoặc số lượng, liên kết từng hợp đồng.',btn('+ Tạo dịch vụ','service-new','','primary')+btn('Gán cho hợp đồng','service-assign'))+
 `<div class="note">Các dịch vụ được cộng ngoài phí dịch vụ cơ sở hiện có. Mức giá được chụp vào hóa đơn khi lập để bảo toàn lịch sử.</div>`+
 table(['CƠ SỞ','TÊN DỊCH VỤ','KIỂU TÍNH','ĐƠN GIÁ','TRẠNG THÁI',''],list.map(x=>`<tr><td>${esc(x.property_name)}</td><td><strong>${esc(x.name)}</strong></td><td>${esc({flat:'Theo phòng',person:'Theo người',quantity:'Theo số lượng'}[x.charge_type])}</td><td class="money">${money(x.unit_price)}</td><td>${badge(x.active?'Đang dùng':'Tạm tắt',x.active?'':'orange')}</td><td>${btn('Sửa','service-edit',x.id)}</td></tr>`))+
 table(['HỢP ĐỒNG','DỊCH VỤ','ĐƠN GIÁ','SỐ LƯỢNG','TRẠNG THÁI',''],assigned.map(x=>`<tr><td>${esc(x.room_code)} #${x.contract_id}</td><td>${esc(x.service_name)}</td><td>${money(x.unit_price)}</td><td>${esc(x.quantity)}</td><td>${x.active?badge('Áp dụng'):badge('Đã tắt','orange')}</td><td>${x.active?btn('Ngừng','service-remove',x.id):''}</td></tr>`));
}
function monthEnd(p){const [y,m]=p.split('-').map(Number);return `${p}-${String(new Date(y,m,0).getDate()).padStart(2,'0')}`;}
function pageMeters(){const warnings=state.data.meterAlerts||[],rd=state.data.readings||[],month=state.filters.period;
 const year=state.filters.meterYear;
 const years=[...new Set([year,...rd.map(x=>Number(x.period.slice(0,4)))])].sort((a,b)=>b-a);
 const yearFilter=`<div class="field" style="max-width:190px;margin-bottom:15px"><label>Năm thống kê</label><select id="pro-meter-year">${years.map(y=>`<option value="${y}" ${y===year?'selected':''}>Cả năm ${y}</option>`).join('')}</select></div>`;
 return header('Ghi chỉ số điện nước','Ghi nhanh nhiều phòng, cảnh báo mức dùng bất thường, bổ sung ảnh công tơ.',btn('Ghi hàng loạt','meter-batch','','primary')+btn('Đổi kỳ','month-change'))+
 `<div class="note">Đang xem tất cả 12 tháng năm <b>${year}</b>. Nhập chỉ số vẫn thực hiện theo tháng, vì hóa đơn điện nước phát sinh mỗi tháng.</div>`+yearFilter+
 panel('Cảnh báo dữ liệu',`${warnings.length} cảnh báo trong kỳ`,warnings.length?warnings.map(x=>`<div class="list-row"><strong>Phòng ${esc(x.room_code)}</strong>${esc(x.message)}</div>`).join(''):'<div class="note success">Không phát hiện bất thường.</div>')+
 table(['PHÒNG / NGƯỜI THUÊ','KỲ','ĐIỆN CŨ / MỚI','NƯỚC CŨ / MỚI','ẢNH CÔNG TƠ',''],rd.filter(x=>x.period.startsWith(String(year)+'-')).map(x=>`<tr><td><strong>${esc(x.room_code)}</strong><br><small class="muted">${esc(x.property_name)} · ${tenantIdentity(x)}</small></td><td>${esc(x.period)}</td><td>${readNum(x.electric_old)} → ${readNum(x.electric_new)}</td><td>${readNum(x.water_old)} → ${readNum(x.water_new)}</td><td>${x.electric_photo?`<a href="/api/v2/files/${encodeURIComponent(x.electric_photo)}" target="_blank">Ảnh điện</a>`:'—'} ${x.water_photo?`<a href="/api/v2/files/${encodeURIComponent(x.water_photo)}" target="_blank">Ảnh nước</a>`:''}</td><td><div class="actions">${btn('Ảnh điện','meter-photo-e',x.id)}${btn('Ảnh nước','meter-photo-w',x.id)}</div></td></tr>`));
}
function pageInvoices(){const list=state.data.invoices||[],drafts=list.filter(x=>x.status==='draft');
 return header('Hóa đơn chuyên nghiệp','Thu tiền phòng kỳ này; điện/nước kỳ tiêu thụ liền trước. Admin có thể hủy và phát hành lại hóa đơn, kể cả đã thu tiền.',btn('+ Lập nháp','invoice-new','','primary')+btn('Tính theo ngày','proration')+btn('Cập nhật','reload'))+
 `<div class="note">Hóa đơn nháp không thể ghi nhận thanh toán. Nợ kỳ trước chỉ hiển thị để đối soát, không được tính lần hai vào tổng hóa đơn.</div>`+
 `<div class="kpis"><div class="kpi"><div class="hint">Chờ duyệt</div><strong>${drafts.length}</strong></div><div class="kpi"><div class="hint">Tổng hóa đơn</div><strong>${list.length}</strong></div><div class="kpi"><div class="hint">Tiền cần duyệt</div><strong style="font-size:19px">${money(drafts.reduce((a,x)=>a+x.total,0))}</strong></div></div>`+
 table(['MÃ','PHÒNG','KỲ','TIỀN THUÊ','DỊCH VỤ','TỔNG','TRẠNG THÁI','THAO TÁC'],list.slice(0,150).map(x=>`<tr><td><strong>HD-${x.id}</strong></td><td>${esc(x.property_name)} / ${esc(x.room_code)}</td><td>${esc(x.period)}</td><td>${money(x.rent)}</td><td>${money(x.services)}</td><td class="money">${money(x.total)}</td><td>${badge(x.status==='void'?'ĐÃ HỦY':x.status==='draft'?'CHỜ DUYỆT':'ĐÃ CHỐT',x.status==='draft'||x.status==='void'?'orange':'')}</td><td><div class="actions">${x.status==='draft'?btn('Sửa','invoice-edit',x.id)+btn('Chốt','invoice-publish',x.id,'primary'):x.status==='void'?badge('Đã hủy','orange'):btn('QR','invoice-qr',x.id)}${state.auth?.user?.role==='admin'?btn('Phát hành lại','invoice-reissue',x.id)+ (x.status==='void'?'':btn('Hủy','invoice-void',x.id)):''}${x.status==='void'?'':`<a class="button" href="/api/v2/invoices/${x.id}/pdf" target="_blank">PDF</a>`}</div></td></tr>`));
}
function pageHandovers(){const h=state.data.handovers||[];
 return header('Bàn giao · Trả phòng','Lưu hiện trạng, chỉ số chốt, quyết toán tiền cọc và kết thúc hợp đồng có kiểm soát.',btn('+ Biên bản mới','handover-new','','primary'))+
 `<div class="note warning">Khi tạo biên bản trả phòng, hệ thống kết thúc hợp đồng ngay, khấu trừ hư hỏng và hoàn cọc theo số bạn nhập. Vui lòng kiểm tra hóa đơn và công nợ trước khi chốt.</div>`+
 table(['PHÒNG','KHÁCH THUÊ','LOẠI','NGÀY','TIỀN HƯ HỎNG','GHI CHÚ',''],h.map(x=>`<tr><td><strong>${esc(x.property_name)} / ${esc(x.room_code)}</strong></td><td>${tenantIdentity(x)}</td><td>${badge(x.handover_type==='checkin'?'Nhận phòng':'Trả phòng',x.handover_type==='checkin'?'':'orange')}</td><td>${esc(x.handover_on)}</td><td>${money(x.damage_amount)}</td><td>${esc(x.description||'—')}</td><td><div class="actions"><a class="button" href="/api/v2/handovers/${x.id}/pdf" target="_blank">PDF</a>${btn('Ảnh','handover-photo',x.id)}</div></td></tr>`));
}
function pageImports(){return header('Nhập dữ liệu Excel','Import CSV UTF-8 hoặc Excel XLSX; xem trước tính hợp lệ rồi mới ghi vào database.')+
 panel('Nhập danh sách hàng loạt','Phòng, khách thuê, hợp đồng, chỉ số điện nước',`<div class="note warning">Nên tải đúng file mẫu. Tối đa 500 dòng / file, import nguyên lô (một dòng sai sẽ không ghi bất kỳ dòng nào). Import chỉ thêm mới, không ghi đè hồ sơ cũ.</div><form id="import-form" class="form-inline"><div class="field"><label>Loại dữ liệu</label><select name="entity" id="import-entity"><option value="rooms">Phòng</option><option value="tenants">Người thuê</option><option value="contracts">Hợp đồng</option><option value="readings">Điện nước</option></select></div><div class="field"><label>Tệp dữ liệu</label><input type="file" accept=".csv,.xlsx" name="file" required></div><button type="button" class="button" data-cmd="import-template">↓ File mẫu</button><button type="button" class="button" data-cmd="import-preview">Kiểm tra file</button><button type="submit" class="button primary">Nhập chính thức</button></form><div id="import-status" style="margin-top:12px"></div>`);
}
function pageAccess(){const list=state.data.access||[],properties=state.data.properties||[];
 return header('Phân quyền theo cơ sở','Quản lý toàn hệ thống, kế toán, thu tiền, bảo trì và nhân sự theo từng cơ sở.')+
 `<div class="note">Tài khoản Admin quản trị toàn hệ thống. Tạo tài khoản mới trong mục Nhân sự của giao diện chính, sau đó vào đây để giới hạn quyền. Đổi quyền sẽ đăng xuất phiên hiện tại của nhân viên.</div>`+
 table(['TÀI KHOẢN','VAI TRÒ','PHẠM VI','TRẠNG THÁI',''],list.map(x=>`<tr><td><strong>${esc(x.full_name)}</strong><br><small class="muted">@${esc(x.username)}</small></td><td>${esc(x.role==='admin'?'Quản trị':x.job_role)}</td><td>${x.role==='admin'?'Tất cả':x.property_ids?.length?x.property_ids.map(p=>esc(properties.find(x=>x.id===p)?.name||p)).join(', '):'Tất cả cơ sở'}</td><td>${badge(x.active?'Hoạt động':'Đã khóa',x.active?'':'red')}</td><td>${x.role!=='admin'?btn('Phân quyền','access-edit',x.id):''}</td></tr>`));
}
function pageAutomation(){const schedules=state.data.schedules||[],events=state.data.scheduleEvents||[],p=state.data.properties||[];
 return header('Lập hóa đơn tự động','Mỗi cơ sở đặt lịch lập hóa đơn nháp. Quản lý duyệt trước khi phát hành và nhận cảnh báo thiếu chỉ số.',btn('Đặt lịch','schedule-new','','primary')+btn('Chạy thử ngay','schedule-run'))+
 `<div class="note success">Bộ lịch chỉ tạo <b>hóa đơn NHÁP</b>. Không tự động chốt hay gửi tiền thu. Lịch chạy một lần/ngày theo giờ hệ thống máy chủ.</div>`+
 table(['CƠ SỞ','KÍCH HOẠT','NGÀY LẬP TRONG THÁNG','KỲ GẦN NHẤT'],schedules.map(x=>`<tr><td>${esc(x.property_name)}</td><td>${badge(x.active?'Bật':'Tắt',x.active?'':'orange')}</td><td>Ngày ${x.day_of_month}</td><td>${esc(x.last_period||'—')}</td></tr>`))+
 panel('Nhật ký cảnh báo','Phòng chưa có chỉ số và lỗi khi chạy lịch',events.length?events.slice(0,30).map(e=>`<div class="list-row"><strong>${esc(e.property_name)} · kỳ ${esc(e.period)}</strong>${esc(e.message)}</div>`).join(''):'Chưa có cảnh báo từ lịch.');
}
function pageBackups(){const list=state.data.backups||[],cfg=state.data.backupConfig||{};
 return header('Sao lưu & phục hồi','Sao lưu SQLite nhất quán, kiểm tra integrity và phục hồi sau khi khởi động lại container.',btn('Tạo backup','backup-create','','primary')+btn('Đặt lịch','backup-config'))+
 `<div class="note warning">Phục hồi là thao tác có rủi ro. Hệ thống CHỈ lên lịch và thực thi ở lúc container khởi động lại, không ghi đè database đang phục vụ người dùng. Tự sao lưu ngoài server bằng rclone/rsync theo hướng dẫn.</div>`+
 panel('Lịch sao lưu','Giờ chạy theo múi giờ container',`Giờ chạy hằng ngày: <strong>${esc(cfg.backup_hour||'03:00')}</strong> · Giữ mặc định 14 bản gần nhất.`)+
 table(['TÊN FILE','DUNG LƯỢNG','NGÀY GIỜ','THAO TÁC'],list.map(x=>`<tr><td><strong>${esc(x.name)}</strong></td><td>${Math.ceil(x.bytes/1024)} KB</td><td>${esc(x.modified.slice(0,19).replace('T',' '))}</td><td><div class="actions">${btn('Kiểm tra','backup-verify',x.name)}${btn('Khôi phục','backup-restore',x.name,'danger')}</div></td></tr>`));
}
function pageBank(){const p=state.data.properties||[];
 return header('Cấu hình VietQR','QR riêng theo hóa đơn, số tiền còn thiếu và nội dung chuyển khoản có mã HD.')+
 `<div class="note">Sử dụng dịch vụ ảnh VietQR. Mã VietQR chỉ hỗ trợ tạo yêu cầu chuyển tiền, không thay thế đối soát ngân hàng. Mỗi cơ sở có tài khoản nhận tiền riêng.</div>`+
 table(['CƠ SỞ','NGÂN HÀNG','SỐ TÀI KHOẢN','CHỦ TÀI KHOẢN',''],p.map(x=>`<tr><td><strong>${esc(x.name)}</strong></td><td>${esc(x.bank_code||'Chưa có')}</td><td>${esc(x.bank_account||'—')}</td><td>${esc(x.bank_name||'—')}</td><td>${btn('Cấu hình','bank-edit',x.id)}</td></tr>`));
}
const VIEWS={overview:pageOverview,deposits:pageDeposits,prepayments:pagePrepayments,residents:pageResidents,services:pageServices,meters:pageMeters,invoices:pageInvoices,handovers:pageHandovers,imports:pageImports,access:pageAccess,automation:pageAutomation,backups:pageBackups,bank:pageBank};
function layout(){const user=state.auth?.user||{};$('#root').innerHTML=`<div class="shell"><aside class="side"><a class="brand" href="/"><span class="brand-icon">⌂</span>TrọFlow<span style="color:#00d3a5">.</span></a><div class="side-sub">TRỌFLOW · V4.0</div>
 <div class="side-label">NGHIỆP VỤ</div>${PAGES.slice(0,9).filter(([key])=>can(pageAbility[key])).map(([key,label,icon])=>`<button class="nav ${state.page===key?'active':''}" data-page="${key}"><span class="ni">${icon}</span><span>${label}</span></button>`).join('')}
 <div class="side-label">HỆ THỐNG</div>${PAGES.slice(9).filter(([key])=>can(pageAbility[key])).map(([key,label,icon])=>`<button class="nav ${state.page===key?'active':''}" data-page="${key}"><span class="ni">${icon}</span><span>${label}</span></button>`).join('')}
 <div class="side-bottom"><a href="/">← Trở về TrọFlow cơ bản</a><div class="user-meta">${esc(user.full_name)} · ${esc(user.role)}</div></div></aside>
 <div class="main"><header class="top"><div class="route">TrọFlow / <strong>${esc(PAGES.find(x=>x[0]===state.page)?.[1]||'Pro')}</strong></div><div class="top-right"><span style="font-size:11px;color:#8090a3">Quản trị vận hành</span><span class="avatar">${esc(user.full_name?.slice(0,1)||'T')}</span><button class="button" data-cmd="reload">↻ Làm mới</button></div></header><main class="content" id="content"></main></div></div>`;}
function render(){layout();try{$('#content').innerHTML=VIEWS[state.page]()}catch(e){console.error(e);$('#content').innerHTML=header('Không thể hiển thị',e.message);}}
async function refresh(){const needed={overview:['summary'],deposits:['balances','deposits'],prepayments:['prepayments'],residents:['residents'],services:['services','assigned'],meters:['readings','meterAlerts'],invoices:['invoices'],handovers:['handovers'],imports:[],access:['access','accessCatalog'],automation:['schedules','scheduleEvents'],backups:['backups','backupConfig'],bank:['properties']};
 const paths={prepayments:'v2/prepayments',accessCatalog:'v2/access/catalog',summary:'v2/summary',balances:'v2/deposits/balances',deposits:'v2/deposits',residents:'v2/residents',services:'v2/services',assigned:'v2/contract-services',readings:'readings',meterAlerts:'v2/readings/alerts?period='+encodeURIComponent(state.filters.period),invoices:'invoices',handovers:'v2/handovers',access:'v2/access',schedules:'v2/schedules',scheduleEvents:'v2/schedules/events',backups:'v2/backups',backupConfig:'v2/backups/config',properties:'properties',rooms:'rooms',contracts:'contracts'};
 const keys=[...new Set(['properties','rooms','contracts',...(needed[state.page]||[])])];
 await Promise.all(keys.map(async k=>{try{state.data[k]=await api(paths[k]);}catch(e){if(![403,401].includes(e.status))console.warn(k,e);state.data[k]=[];}}));render();
}
function activePropertyOptions(){return pOpts()}
function selectedOptions(items,value=''){return items.map(x=>({...x,selected:String(x.value)===String(value)}));}
function runForm(title,fields,method,path,finish){form(title,fields,async data=>{await api(path,method,data);toast('Lưu dữ liệu thành công.');if(finish)finish();});}
function command(cmd,id){const sid=Number(id),d=state.data;
 if(cmd==='prepay-new'){form('Thu tiền phòng nhiều tháng',[formspec('contract_id','Người thuê · Hợp đồng','select',cOpts().filter(o=>(d.contracts||[]).find(c=>String(c.id)===o.value)?.status==='active')),
 formspec('start_period','Từ tháng','month',{},period()),formspec('duration_months','Thanh toán nhanh','select',[C('1','1 tháng'),C('3','1 quý (3 tháng)'),C('6','6 tháng'),C('12','1 năm'),C('custom','Chọn tùy ý')],'1'),formspec('end_period','Đến tháng (bao gồm tháng này)','month',{},period()),
 formspec('paid_on','Ngày nhận tiền','date',{},today()),formspec('method','Phương thức thanh toán','select',[C('transfer','Chuyển khoản'),C('cash','Tiền mặt'),C('other','Khác')]),formspec('note','Ghi chú / mã giao dịch','textarea')],
 d=>api('v2/prepayments','POST',d),'Ghi nhận tiền thuê trả trước',
 'Số tiền tự tính theo hợp đồng cho từng tháng trong khoảng đã chọn. Không thể trả trước trùng tháng hoặc kỳ đã có hóa đơn.');return;}
 if(cmd==='prepay-refund'){form('Hoàn tiền thuê trả trước',[formspec('refunded_on','Ngày hoàn','date',{},today()),formspec('reason','Lý do hoàn tiền','textarea')],
 d=>api('v2/prepayments/'+sid+'/refund','POST',d),'Xác nhận hoàn kỳ',
 'Chỉ được hoàn từng tháng chưa có hóa đơn; hệ thống lưu lịch sử và không xóa giao dịch gốc.');return;}

 if(cmd==='deposit-new'){form('Ghi nhận giao dịch tiền cọc',[
 formspec('contract_id','Hợp đồng','select',cOpts()),formspec('kind','Loại giao dịch','select',[C('receive','Thu cọc'),C('refund','Hoàn cọc'),C('deduct','Khấu trừ')]),
 formspec('amount','Số tiền (VND)','money',{},0),formspec('transacted_on','Ngày giao dịch','date',{},today()),formspec('note','Lý do / chứng từ','textarea',{},'')],d=>api('v2/deposits','POST',d));return;}
 if(cmd==='resident-new'){form('Thêm người ở cùng phòng',[
 formspec('contract_id','Hợp đồng','select',cOpts()),formspec('full_name','Họ tên','text',{},''),formspec('phone','Điện thoại'),formspec('id_number','CCCD'),formspec('hometown','Quê quán'),formspec('moved_in','Ngày vào','date',{},today()),formspec('notes','Ghi chú','textarea')],d=>api('v2/residents','POST',d));return;}
 if(cmd==='resident-leave'){form('Ghi nhận rời phòng',[formspec('moved_out','Ngày rời phòng','date',{},today())],d=>api('v2/residents/'+sid+'/leave','POST',d));return;}
 if(cmd==='service-new'||cmd==='service-edit'){const existing=cmd==='service-edit'?d.services.find(x=>x.id===sid):{};
 const fields=[formspec('property_id','Cơ sở','select',pOpts(),existing?.property_id),formspec('name','Tên dịch vụ','text',{},existing?.name||''),
 formspec('charge_type','Kiểu tính tiền','select',[C('flat','Theo phòng'),C('person','Theo người'),C('quantity','Theo số lượng')],existing?.charge_type||'flat'),
 formspec('unit_price','Đơn giá','money',{},existing?.unit_price||0),formspec('unit','Đơn vị','text',{},existing?.unit||'thang')];
 if(existing?.id){fields.shift();fields.push(formspec('active','Đang sử dụng','checkbox',{},existing.active));}
 form(existing?.id?'Sửa dịch vụ':'Tạo dịch vụ',fields,data=>api('v2/services'+(existing?.id?'/'+sid:''),existing?.id?'PUT':'POST',data));return;}
 if(cmd==='service-assign'){form('Gán dịch vụ cho hợp đồng',[formspec('contract_id','Hợp đồng','select',cOpts()),formspec('service_id','Dịch vụ','select',sOpts()),formspec('quantity','Số lượng (cho dịch vụ tính theo SL)','number',{},1)],d=>api('v2/contract-services','POST',d));return;}
 if(cmd==='service-remove'){if(confirm('Ngừng dịch vụ cho hợp đồng? Các hóa đơn cũ không thay đổi.'))act('v2/contract-services/'+sid,'DELETE');return;}
 if(cmd==='month-change'){form('Chọn kỳ điện nước',[formspec('period','Kỳ','month',{},state.filters.period)],async d=>{state.filters.period=d.period;});return;}
 if(cmd==='meter-batch'){
 const rooms=d.rooms.filter(x=>(d.contracts||[]).some(c=>c.room_id===x.id&&c.start_date<=monthEnd(state.filters.period)&&c.end_date>=state.filters.period+'-01')), month=state.filters.period;let entries=rooms.map(r=>{const old=d.readings.find(x=>x.room_id===r.id&&x.period===month);
 return `<tr><td>${esc(r.property_name)} / ${esc(r.code)}<br><small>${esc(d.contracts.find(c=>c.room_id===r.id&&c.start_date<=monthEnd(month)&&c.end_date>=month+'-01')?.tenant_name||'')}</small><input type="hidden" name="room_${r.id}" value="${r.id}"></td>${['electric_old','electric_new','water_old','water_new'].map(k=>`<td><input style="width:85px;padding:7px;border:1px solid #d7e0ea;border-radius:7px" type="number" step="any" min="0" name="${r.id}_${k}" value="${old?.[k]??0}" required></td>`).join('')}</tr>`;});
 state.form={save:async()=>{const fd=new FormData($('#pro-form'));const rows=rooms.map(x=>({room_id:x.id,...Object.fromEntries(['electric_old','electric_new','water_old','water_new'].map(k=>[k,fd.get(x.id+'_'+k)]))}));const res=await api('v2/readings/batch','POST',{period:month,entries:rows});toast(`Đã lưu ${res.updated} phòng; ${res.alerts.length} cảnh báo.`);},custom:true};
 $('#modal').innerHTML=`<div class="modal-wrap"><div class="dialog" style="width:min(1000px,100%)"><div class="dialog-head"><h2>Ghi chỉ số hàng loạt · ${esc(month)}</h2>${btn('✕','close')}</div><form id="pro-form"><div class="dialog-body"><div class="note">Điền chỉ số công tơ cũ/mới. Phòng đã phát sinh hóa đơn sẽ không được cập nhật.</div><div class="table-scroll"><table class="data"><thead><tr><th>PHÒNG</th><th>ĐIỆN CŨ</th><th>ĐIỆN MỚI</th><th>NƯỚC CŨ</th><th>NƯỚC MỚI</th></tr></thead><tbody>${entries.join('')}</tbody></table></div></div><div class="dialog-foot">${btn('Đóng','close')}<button class="button primary" type="submit">Lưu chỉ số</button></div></form></div></div>`;return;}
 if(cmd==='meter-photo-e'||cmd==='meter-photo-w'||cmd==='handover-photo'){
 state.form={file:true,category:cmd==='meter-photo-e'?'electric':cmd==='meter-photo-w'?'water':(d.handovers.find(x=>x.id===sid)?.handover_type||'checkin'),related_id:sid};
 $('#modal').innerHTML=`<div class="modal-wrap"><div class="dialog"><div class="dialog-head"><h2>Tải ảnh hiện trạng</h2>${btn('✕','close')}</div><form id="pro-form"><div class="dialog-body"><div class="note">Chỉ chấp nhận JPG, PNG hoặc WebP tối đa 3 MB. Ảnh được lưu riêng trên /opt/troflow/uploads.</div><div class="field"><label>Ảnh cần tải</label><input type="file" name="file" accept="image/png,image/jpeg,image/webp" required></div></div><div class="dialog-foot">${btn('Hủy','close')}<button type="submit" class="button primary">Lưu ảnh</button></div></form></div></div>`;return;}
 if(cmd==='invoice-new'){
 form('Lập hóa đơn nháp',[formspec('contract_id','Hợp đồng','select',cOpts()),formspec('period','Kỳ hóa đơn','month',{},period()),
 formspec('discount','Giảm giá (VND)','money',{},0),formspec('surcharge','Truy thu (VND)','money',{},0),
 formspec('adjustment','Điều chỉnh ± (VND)','number',{},0),formspec('note','Nội dung hóa đơn','textarea',{},'')],d=>api('v2/invoices/draft','POST',d),'Tạo hóa đơn nháp',
 'Điện/nước lấy tháng trước kỳ hóa đơn. Hóa đơn được tạo ở trạng thái nháp và chỉ chốt sau khi kiểm tra.');
 const footer=$('#pro-form .dialog-foot');if(footer)footer.insertAdjacentHTML('afterbegin',btn('Xem trước tiền','invoice-preview'));
 return;}
 if(cmd==='proration'){
  form('Tính tiền thuê theo ngày',[formspec('contract_id','Hợp đồng','select',cOpts()),
  formspec('enabled','Tính theo số ngày thực tế ở trong tháng','checkbox',{},true)],
  d=>{const id=d.contract_id;return api('v2/contracts/'+id+'/proration','PUT',{enabled:d.enabled});},'Lưu cách tính',
  'Hợp đồng hiện có mặc định tính tròn tháng. Chỉ các hóa đơn tạo sau thay đổi mới tính theo ngày.');return;}
 if(cmd==='invoice-preview'){
  const form=$('#pro-form'),d=Object.fromEntries(new FormData(form));
  api('v2/invoices/preview','POST',d).then(r=>{
    const text=`<div class="note success"><b>Tạm tính: ${money(r.total)}</b><div style="margin-top:8px">Tiền phòng ${money(r.rent)} · Điện ${money(r.electricity)} · Nước ${money(r.water)} · Phí ${money(r.services)}</div><small>Ở ${r.days_occupied||JSON.parse(r.calculation_json).days_occupied} ngày / ${JSON.parse(r.calculation_json).days_in_month} ngày · Nợ kỳ trước (tham khảo) ${money(r.carried_debt)}</small></div>`;
    const prev=$('#invoice-preview-result');if(prev)prev.innerHTML=text;
    else $('#pro-form .dialog-body').insertAdjacentHTML('beforeend','<div id="invoice-preview-result" style="margin-top:16px">'+text+'</div>');
  }).catch(e=>toast(e.message,true));return;
 }
 if(cmd==='invoice-reissue'){
  const i=d.invoices.find(x=>x.id===sid);form('Phát hành lại hóa đơn HD-'+sid,[
  formspec('adjustment','Điều chỉnh ± (VND)','number',{},i.adjustment||0),
  formspec('discount','Giảm giá (VND)','money',{},i.discount||0),
  formspec('surcharge','Phụ thu (VND)','money',{},i.surcharge||0),
  formspec('note','Ghi chú','textarea',{},i.note||''),
  formspec('reason','Lý do phát hành lại (bắt buộc)','textarea'),
  formspec('acknowledge_credit','Tôi xác nhận khoản thu thừa chờ đối soát, không tự hoàn tiền','checkbox',{},false)],x=>api('v10/invoices/'+sid+'/reissue','POST',x),'Phát hành lại',
  'Sẽ tính lại điện nước tháng trước và giữ mọi giao dịch. Nếu tổng mới thấp hơn số đã thu, phải tích xác nhận khoản tiền thừa cần đối soát.');return;}
 if(cmd==='invoice-void'){
  const i=d.invoices.find(x=>x.id===sid);form('Hủy hiệu lực hóa đơn HD-'+sid,[
  formspec('reason','Lý do hủy (bắt buộc)','textarea'),
  formspec('acknowledge_payments','Xác nhận giữ toàn bộ giao dịch thu để đối soát','checkbox',{},false)],
  x=>api('v10/invoices/'+sid+'/void','POST',x),'Hủy hiệu lực',
  'Không xóa dữ liệu hoặc khoản thanh toán cũ. Có thể sửa chỉ số và phát hành lại cùng ID hóa đơn.');return;}
 if(cmd==='invoice-edit'){
 const i=d.invoices.find(x=>x.id===sid);
 form('Sửa hóa đơn nháp HD-'+sid,[formspec('discount','Giảm giá (VND)','money',{},i.discount),
 formspec('surcharge','Truy thu (VND)','money',{},i.surcharge),formspec('adjustment','Điều chỉnh ±','number',{},i.adjustment),
 formspec('note','Ghi chú','textarea',{},i.note),formspec('reason','Lý do chỉnh sửa (ghi vào nhật ký)','text')],x=>api('v2/invoices/'+sid+'/draft','PUT',x));return;}
 if(cmd==='invoice-publish'){if(confirm('Chốt hóa đơn HD-'+sid+'? Sau khi chốt sẽ không thể chỉnh sửa tổng tiền.'))act('v2/invoices/'+sid+'/publish','POST',{});return;}
 if(cmd==='invoice-qr'){api('v2/invoices/'+sid+'/vietqr').then(r=>{
 $('#modal').innerHTML=`<div class="modal-wrap"><div class="dialog"><div class="dialog-head"><h2>Thanh toán VietQR · HD-${sid}</h2>${btn('✕','close')}</div><div class="dialog-body" style="text-align:center"><img src="${esc(r.url)}" alt="QR chuyển khoản VietQR" style="max-width:100%;max-height:330px"><h2>${money(r.amount)}</h2><p>${esc(r.bank_name)} · ${esc(r.bank_account)}</p><div class="code">${esc(r.transfer_note)}</div><p class="muted">${esc(r.disclaimer)}</p></div><div class="dialog-foot">${btn('Đóng','close')}</div></div></div>`;
 }).catch(e=>toast(e.message,true));return;}
 if(cmd==='handover-new'){form('Lập biên bản bàn giao / trả phòng',[
 formspec('contract_id','Hợp đồng','select',cOpts()),formspec('handover_type','Loại bàn giao','select',[C('checkin','Nhận phòng'),C('checkout','Trả phòng')]),
 formspec('handover_on','Ngày bàn giao','date',{},today()),formspec('damage_amount','Khấu trừ hư hỏng','money',{},0),
 formspec('refund_amount','Hoàn cọc ngay khi trả phòng','money',{},0),formspec('ack_debt','Tôi đã đối chiếu và ghi nhận công nợ chưa thanh toán','checkbox',{},false),formspec('electric_final','Chỉ số điện cuối','number'),formspec('water_final','Chỉ số nước cuối','number'),
 formspec('confirmed_by','Người xác nhận'),formspec('description','Hiện trạng phòng, thiết bị, công nợ còn lại','textarea')],d=>api('v2/handovers','POST',d),'Lưu biên bản',
 'Biên bản trả phòng sẽ kết thúc hợp đồng và thực hiện khấu trừ/hoàn cọc trong cùng giao dịch.');return;}
 if(cmd==='access-edit'){
 const x=d.access.find(x=>x.id===sid),catalog=d.accessCatalog;
 if(!x||!catalog?.groups){toast('Không tải được danh sách chức năng.',true);return;}
 const roles=[C('manager','Quản lý'),C('accountant','Kế toán'),C('collector','Thu tiền'),C('maintenance','Bảo trì'),C('viewer','Chỉ xem')];
 const groupRows=catalog.groups.map(g=>{const checked=g.actions.filter(a=>x.permissions?.[a.key]).length;
  return `<details class="perm-section" data-perm-section="${esc(g.id)}" ${!g.admin_only?'open':''}><summary><span class="perm-name">${esc(g.label)} ${g.admin_only?'<small>Khóa Admin</small>':''}</span><span class="perm-count">${checked}/${g.actions.length}</span></summary><div class="perm-actions">${g.actions.map(a=>`<label class="perm-toggle"><span>${esc(a.label)}</span><input type="checkbox" data-permission="${esc(a.key)}" ${x.permissions?.[a.key]?'checked':''} ${a.locked?'disabled':''}><i aria-hidden="true"></i></label>`).join('')}</div></details>`}).join('');
 state.form={access:true,userId:sid};
 $('#modal').innerHTML=`<div class="modal-wrap"><div class="dialog perm-dialog" role="dialog" aria-modal="true" aria-label="Phân quyền tài khoản"><div class="dialog-head"><div><h2>Phân quyền · ${esc(x.full_name)}</h2><p class="muted">@${esc(x.username)} · Thiết lập riêng từng tính năng</p></div>${btn('✕','close')}</div><form id="pro-form"><div class="dialog-body"><div class="perm-profile"><div class="field"><label>Vai trò mẫu</label><select name="job_role" id="perm-role">${roles.map(o=>`<option value="${o.value}" ${x.job_role===o.value?'selected':''}>${o.label}</option>`).join('')}</select></div><div class="perm-status"><strong id="perm-total">0 quyền được cấp</strong><small>Lưu thay đổi sẽ đăng xuất các phiên của nhân viên.</small></div></div><div class="perm-scope"><strong>Phạm vi cơ sở</strong><label class="perm-check"><input id="perm-all-properties" type="checkbox" ${x.property_ids?.length===0?'checked':''}> Cho phép tất cả cơ sở</label><div class="perm-properties" id="perm-properties">${d.properties.map(p=>`<label class="perm-check"><input type="checkbox" name="prop" value="${p.id}" ${x.property_ids?.includes(p.id)?'checked':''}> ${esc(p.name)}</label>`).join('')}</div></div><div class="perm-bar"><strong>Quyền thao tác chi tiết</strong><div><button type="button" class="button" data-cmd="perm-all">Chọn tất cả</button><button type="button" class="button" data-cmd="perm-none">Bỏ chọn</button></div></div><div class="field"><input id="perm-search" type="search" placeholder="Tìm chức năng..." aria-label="Tìm quyền"></div><div class="perm-list">${groupRows}</div><div class="note">Các quyền quản trị tài khoản, phân quyền, sao lưu/khôi phục, ngân hàng và nhật ký chỉ dành cho Admin và không thể cấp cho nhân viên.</div></div><div class="dialog-foot"><button type="button" class="button" data-cmd="close">Hủy</button><button class="button primary" type="submit">✓ Lưu phân quyền</button></div></form></div></div>`;
 syncPermissionsUI();return;}
 if(cmd==='schedule-new'||cmd==='schedule-run'){
 form(cmd==='schedule-run'?'Chạy lịch ngay (tạo nháp)':'Cài lịch hóa đơn',[
 formspec('property_id','Cơ sở','select',pOpts()),...(cmd==='schedule-run'?[formspec('period','Kỳ','month',{},period())]:[
 formspec('day_of_month','Ngày lập trong tháng (1–28)','number',{},1),formspec('active','Bật lịch','checkbox',{},true)])],d=>{const pid=d.property_id;delete d.property_id;return api(cmd==='schedule-run'?'v2/schedules/run/'+pid:'v2/schedules/'+pid,cmd==='schedule-run'?'POST':'PUT',d);});return;}
 if(cmd==='backup-create'){act('v2/backups/create','POST',{});return;}
 if(cmd==='backup-verify'){api('v2/backups/verify','POST',{name:id}).then(r=>toast(r.valid?'Backup hợp lệ: '+id:'Backup bị lỗi! '+r.check,!r.valid)).catch(e=>toast(e.message,true));return;}
 if(cmd==='backup-restore'){
 form('Xác nhận phục hồi backup',[formspec('name','Tên bản backup','text',{},id),formspec('confirm','Gõ KHOI PHUC để xác nhận','text')],d=>api('v2/backups/restore','POST',d),'Lên lịch phục hồi',
 'RỦI RO CAO: Dữ liệu hiện tại sẽ thay bằng dữ liệu backup ở lần khởi động lại container. Phải tải/sao lưu thêm bản hiện tại.');return;}
 if(cmd==='backup-config'){form('Thời gian sao lưu tự động',[formspec('backup_hour','Giờ chạy hằng ngày (HH:MM)','time',{},d.backupConfig?.backup_hour||'03:00')],x=>api('v2/backups/config','PUT',x));return;}
 if(cmd==='bank-edit'){
 const x=d.properties.find(x=>x.id===sid);
 form('Tài khoản VietQR · '+x.name,[formspec('bank_code','Mã ngân hàng (BIN hoặc mã viết tắt)','text',{},x.bank_code||''),
 formspec('bank_account','Số tài khoản','text',{},x.bank_account||''),formspec('bank_name','Tên chủ tài khoản','text',{},x.bank_name||'')],y=>api('v2/properties/'+sid+'/bank','PUT',y));return;}
}
function syncPermissionsUI(){const checks=$$('[data-permission]');let n=checks.filter(x=>x.checked&&!x.disabled).length;
 const counter=$('#perm-total');if(counter)counter.textContent=n+' quyền được cấp';
 for(const group of $$('[data-perm-section]')){const inputs=$$('[data-permission]',group);const box=group.querySelector('.perm-count');if(box)box.textContent=inputs.filter(x=>x.checked).length+'/'+inputs.length;}
 const scope=$('#perm-all-properties');if(scope){for(const x of $$('#perm-properties input'))x.disabled=scope.checked;}
}
function applyRolePreset(job){const cfg=state.data.accessCatalog?.role_defaults?.[job]||{};
 for(const check of $$('[data-permission]'))if(!check.disabled)check.checked=Boolean(cfg[check.dataset.permission]);
 syncPermissionsUI();}
async function act(path,method='POST',data){try{const result=await api(path,method,data);toast(result.message||'Đã thực hiện thành công.');await refresh();}catch(e){toast(e.message,true);}}
document.addEventListener('click',async e=>{
 if(e.target.matches('.modal-wrap')){close();return;}
 const target=e.target.closest('[data-page],[data-cmd]');if(!target)return;
 if(target.dataset.page){if(!can(pageAbility[target.dataset.page]))return;state.page=target.dataset.page;await refresh();window.scrollTo(0,0);return;}
 const cmd=target.dataset.cmd,id=target.dataset.id;if(cmdAbility[cmd]&&!can(cmdAbility[cmd]))return;
 if(cmd==='perm-all'||cmd==='perm-none'){for(const c of $$('[data-permission]'))if(!c.disabled)c.checked=cmd==='perm-all';syncPermissionsUI();return;}
 if(cmd==='close'){close();return;}if(cmd==='reload'){await refresh();toast('Đã làm mới dữ liệu.');return;}
 if(cmd==='import-template'){window.location.href='/api/v2/imports/template/'+$('#import-entity').value;return;}
 if(cmd==='import-preview'){
  const form=$('#import-form'),ent=form.elements.entity.value,f=form.elements.file.files[0];if(!f){toast('Chọn file Excel hoặc CSV trước.',true);return;}
  const fd=new FormData();fd.append('file',f);try{const r=await api('v2/imports/'+ent+'?dry_run=true','POST',fd);$('#import-status').innerHTML=`<div class="note success">Hợp lệ: ${r.rows} dòng. Chưa ghi vào database.</div>`;}catch(err){toast(err.message,true);}return;
 }
 command(cmd,id);
});
document.addEventListener('change',e=>{
 if(e.target.closest('#pro-form')&&['duration_months','start_period'].includes(e.target.name)){
  const f=e.target.form,months=f?.elements.duration_months?.value,first=f?.elements.start_period?.value;
  if(first&&months&&months!=='custom'){
   const [y,m]=first.split('-').map(Number),d=Number(months)-1;
   f.elements.end_period.value=`${y+Math.floor((m-1+d)/12)}-${String((m-1+d)%12+1).padStart(2,'0')}`;
  }
  return;
 }
 if(e.target.id==='perm-role'){if(confirm('Áp dụng quyền mặc định theo vai trò mới? Các ô hiện tại sẽ thay đổi.'))applyRolePreset(e.target.value);return;}
 if(e.target.id==='perm-all-properties'||e.target.dataset.permission||e.target.name==='prop'){syncPermissionsUI();return;}
 if(e.target.id==='pro-meter-year'){state.filters.meterYear=Number(e.target.value);render();}
});
document.addEventListener('input',e=>{if(e.target.id==='perm-search'){
 const q=e.target.value.trim().toLocaleLowerCase('vi');for(const g of $$('[data-perm-section]'))g.style.display=g.textContent.toLocaleLowerCase('vi').includes(q)?'':'none';
}});
document.addEventListener('submit',async e=>{
 if(e.target.id==='import-form'){
  e.preventDefault();if(!confirm('Xác nhận ghi toàn bộ file vào database?'))return;
  const el=e.target,fd=new FormData(),file=el.elements.file.files[0];if(!file){toast('Chưa chọn file.',true);return;}fd.append('file',file);
  try{const r=await api('v2/imports/'+el.elements.entity.value+'?dry_run=false','POST',fd);toast('Đã nhập '+r.rows+' dòng thành công.');await refresh();}
  catch(err){toast(err.message,true);}return;
 }
 if(e.target.id!=='pro-form')return;e.preventDefault();if(state.busy)return;state.busy=true;
 try{
  if(state.form?.file){const fd=new FormData(e.target);fd.append('category',state.form.category);fd.append('related_id',state.form.related_id);await api('v2/files','POST',fd);toast('Đã lưu ảnh thành công.');}
  else if(state.form?.access){const fd=new FormData(e.target);
   const permissions=Object.fromEntries($$('[data-permission]',e.target).map(x=>[x.dataset.permission,Boolean(x.checked)]));
   const properties=$('#perm-all-properties')?.checked?[]:fd.getAll('prop').map(Number);
   if(!$('#perm-all-properties')?.checked&&!properties.length)throw Error('Hãy chọn ít nhất một cơ sở hoặc tất cả cơ sở.');
   await api('v2/access/'+state.form.userId,'PUT',{job_role:fd.get('job_role'),property_ids:properties,permissions});
   toast('Đã lưu quyền và cập nhật phiên đăng nhập nhân viên.');}
  else if(state.form?.custom){await state.form.save();}
  else if(state.form?.save){const fd=new FormData(e.target);const data=Object.fromEntries(fd.entries());for(const input of e.target.querySelectorAll('input[type=checkbox]'))data[input.name]=input.checked;
    const res=await state.form.save(data);toast(res?.message||'Thao tác thành công.');}
  close();await refresh();
 }catch(err){toast(err.message,true);}finally{state.busy=false;}
});
(async function init(){try{
 const a=await fetch('/api/auth/me',{credentials:'same-origin'});if(!a.ok){$('#root').innerHTML='<div class="boot">Bạn cần <a href="/">đăng nhập TrọFlow</a> trước.</div>';return;}
 const auth=await a.json();state.auth=auth;state.csrf=auth.csrf;if(!can(pageAbility[state.page]))state.page=PAGES.find(([key])=>can(pageAbility[key]))?.[0]||'overview';await refresh();
 }catch(e){$('#root').innerHTML=`<div class="boot">Không thể kết nối máy chủ: ${esc(e.message)} <a href="/">Trở về</a></div>`;}})();
