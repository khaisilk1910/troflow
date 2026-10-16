'use strict';
const $=(q,root=document)=>root.querySelector(q);
const $$=(q,root=document)=>[...root.querySelectorAll(q)];
const esc=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const amount=v=>Math.round(Number(v)||0).toLocaleString('en-US')+' ₫';
const compact=v=>{const n=Number(v)||0;return n>=1e9?(n/1e9).toLocaleString('en-US',{maximumFractionDigits:1})+' tỷ':n>=1e6?(n/1e6).toLocaleString('en-US',{maximumFractionDigits:1})+' tr':n.toLocaleString('en-US')};
const dateVN=s=>s?String(s).slice(0,10).split('-').reverse().join('/'):'—';
const today=()=>{const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-')};
const thisMonth=()=>today().slice(0,7);
const monthVN=s=>{if(!s)return '—';const [y,m]=s.split('-');return `Tháng ${Number(m)}/${y}`};
const initials=s=>String(s||'TF').split(' ').filter(Boolean).slice(-2).map(x=>x[0]).join('').toUpperCase();
const num=v=>Number(v)||0;
const readNum=v=>Number(v||0).toLocaleString('en-US',{maximumFractionDigits:3});
const iconPaths={
 home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M9 21v-8h6v8"/>',
 dashboard:'<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
 building:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 21v-5h6v5M8 7h1m6 0h1M8 11h1m6 0h1"/>',
 door:'<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M10 13h.01M4 20h16"/>',
 users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
 user:'<circle cx="12" cy="8" r="4"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>',
 contract:'<path d="M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8l-5-5H8"/><path d="M16 3v5h5M7 13h10M7 17h7"/>',
 meter:'<path d="M4 16a8 8 0 1 1 16 0"/><path d="m12 13 4-4M6 19h12"/><circle cx="12" cy="16" r="1"/>',
 receipt:'<path d="M4 3v18l4-2 4 2 4-2 4 2V3l-4 2-4-2-4 2zM8 10h8M8 14h6"/>',
 wallet:'<rect x="3" y="5" width="18" height="15" rx="3"/><path d="M3 9h18M16 15h2"/>',
 expense:'<path d="M12 3v12m-4-4 4 4 4-4M4 19h16"/>',
 wrench:'<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4l-6.8 6.8a2.1 2.1 0 0 0 3 3l6.8-6.8a4 4 0 0 0 5.4-5.4l-2.9 2.9-3-3z"/>',
 report:'<path d="M3 3v18h18M8 16v-5M13 16V7M18 16v-9"/>',
 settings:'<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.1 2.1-.06-.06A1.7 1.7 0 0 0 15.76 19a1.7 1.7 0 0 0-1.01 1.57V21h-3v-.43A1.7 1.7 0 0 0 10.7 19a1.7 1.7 0 0 0-1.88.34l-.06.06-2.1-2.1.06-.06A1.7 1.7 0 0 0 7.05 15a1.7 1.7 0 0 0-1.57-1.01H5v-3h.43A1.7 1.7 0 0 0 7.05 10a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.1-2.1.06.06A1.7 1.7 0 0 0 10.7 6a1.7 1.7 0 0 0 1.01-1.57V4h3v.43A1.7 1.7 0 0 0 15.76 6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.1 2.1-.06.06A1.7 1.7 0 0 0 19.4 10a1.7 1.7 0 0 0 1.57 1.01H21v3h-.43A1.7 1.7 0 0 0 19.4 15z"/>',
 search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
 bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 chevron:'<path d="m9 18 6-6-6-6"/>',
 down:'<path d="m6 9 6 6 6-6"/>',
 edit:'<path d="m16 4 4 4M4 20l4-.6L20.5 7a2.8 2.8 0 0 0-4-4L4 15.5z"/>',
 trash:'<path d="M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
 eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
 x:'<path d="M18 6 6 18M6 6l12 12"/>',
 download:'<path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4"/>',
 check:'<path d="m4 12 5 5L20 6"/>',
 calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 arrowup:'<path d="m12 19 0-14m-6 6 6-6 6 6"/>',
 arrowdown:'<path d="m12 5 0 14m-6-6 6 6 6-6"/>',
 alert:'<path d="m10.3 3.9-8.5 15a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3l-8.5-15a2 2 0 0 0-3.4 0zM12 9v5m0 4h.01"/>',
 menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
 logout:'<path d="M10 17l5-5-5-5M15 12H3M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7"/>',
 print:'<path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 15h12v7H6zM18 12h.01"/>',
 layers:'<path d="m12 2 9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5"/>',
 shield:'<path d="m12 2 8 4v6c0 5-3 8-8 10-5-2-8-5-8-10V6zM9 12l2 2 4-4"/>',
 filter:'<path d="M4 7h16M7 12h10M10 17h4"/>',
 dots:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
 refresh:'<path d="M21 10a9 9 0 0 0-16-4L3 8M3 3v5h5M3 14a9 9 0 0 0 16 4l2-2m0 5v-5h-5"/>',
 info:'<circle cx="12" cy="12" r="10"/><path d="M12 11v6M12 7h.01"/>'};
const ic=(name,size)=>`<svg class="icon" ${size?`style="width:${size}px;height:${size}px"`:''} viewBox="0 0 24 24" aria-hidden="true">${iconPaths[name]||iconPaths.info}</svg>`;

const views={dashboard:'Tổng quan',properties:'Cơ sở',utilitymeters:'Công tơ điện nước',rooms:'Phòng trọ',tenants:'Người thuê',contracts:'Hợp đồng',readings:'Điện & nước',invoices:'Hóa đơn',payments:'Thanh toán',expenses:'Thu chi',tickets:'Sự cố',reports:'Báo cáo',settings:'Cài đặt',tenantApprovals:'Duyệt chỉ số khách thuê',users:'Nhân sự',audit:'Nhật ký',deposits:'Tiền cọc',prepayments:'Thuê trả trước',residents:'Người ở',services:'Phí dịch vụ',handovers:'Bàn giao phòng',imports:'Nhập Excel',access:'Phân quyền',automation:'Lịch hóa đơn',backups:'Sao lưu',bank:'VietQR',bankaccounts:'Tài khoản ngân hàng & QR',zalo:'Thông báo Zalo',meterTools:'Điện nước nâng cao',invoiceTools:'Hóa đơn nâng cao'};
const integratedPages={deposits:'deposits',prepayments:'prepayments',residents:'residents',services:'services',handovers:'handovers',imports:'imports',access:'access',automation:'automation',backups:'backups',bank:'bank',meterTools:'meters',invoiceTools:'invoices'};
const standalonePages={bankaccounts:'banks',zalo:'zalo'};
const embeddedAbility={deposits:'deposits.view',prepayments:'prepayments.view',residents:'residents.view',services:'services.view',handovers:'handovers.view',imports:'imports.view',access:'access.view',automation:'schedules.view',backups:'backups.view',bank:'bank.view',meterTools:'readings.view',invoiceTools:'invoices.view'};
const statuses={void:'Đã hủy · chờ đối soát',occupied:'Đang thuê',ready:'Còn trống',maintenance:'Bảo trì',inactive:'Ngừng dùng',active:'Hiệu lực',ended:'Đã kết thúc',new:'Mới tiếp nhận',in_progress:'Đang xử lý',done:'Đã hoàn thành',paid:'Đã thanh toán',partial:'Thanh toán một phần',unpaid:'Chưa thanh toán',overdue:'Quá hạn',low:'Thấp',medium:'Trung bình',high:'Cao'};
const categories={repair:'Sửa chữa',utilities:'Điện nước',supplies:'Vật tư',operations:'Vận hành',salary:'Nhân công',other:'Khác',electric:'Điện',water:'Nước',internet:'Internet',furniture:'Nội thất'};
const methods={transfer:'Chuyển khoản',cash:'Tiền mặt',other:'Khác'};
const badge=(value)=>`<span class="badge-status status-${esc(value)}">${esc(statuses[value]||value||'—')}</span>`;
const state={user:null,csrf:'',view:'dashboard',data:{},search:'',propertyFilter:'',period:thisMonth(),report:null,reportProperty:'',roomMode:'cards',sidebar:false,invoicesYear:Number(today().slice(0,4)),readingsYear:Number(today().slice(0,4)),utilityYear:Number(today().slice(0,4))};
const ENTITY_API={properties:'properties',rooms:'rooms',tenants:'tenants',contracts:'contracts',readings:'readings',invoices:'invoices',payments:'payments',expenses:'expenses',tickets:'tickets',users:'users'};
let busy=false;
const can=(key)=>state.user?.role==='admin'||Boolean(state.user?.permissions?.[key]);
const canPage=(view)=>view in standalonePages?state.user?.role==='admin':view in integratedPages?can(embeddedAbility[view]):view==='tenantApprovals'?can('readings.view'):['settings','users','audit'].includes(view)?state.user?.role==='admin':can(view+'.view');
const firstPage=()=>Object.keys(views).find(canPage)||null;


async function api(path,method='GET',payload){
 const headers={};if(method!=='GET'&&method!=='HEAD'){headers['Content-Type']='application/json';if(state.csrf)headers['X-CSRF-Token']=state.csrf;}
 let res;try{res=await fetch('/api/'+path,{method,headers,credentials:'same-origin',body:payload===undefined?undefined:JSON.stringify(payload)});}catch(e){throw Error('Không kết nối được máy chủ. Kiểm tra kết nối và Docker.');}
 let out;try{out=await res.json();}catch(e){out={};}
 if(!res.ok){if(res.status===401&&state.user){state.user=null;renderAuth(false);}const err=Error(typeof out.detail==='string'?out.detail:'Yêu cầu không thành công.');err.status=res.status;throw err;}
 return out;
}
function toast(message,error=false){const root=$('#toast-root');if(!root)return;const el=document.createElement('div');el.className='toast'+(error?' error':'');el.innerHTML=ic(error?'alert':'check')+`<span>${esc(message)}</span>`;root.append(el);setTimeout(()=>el.remove(),4800);}
async function init(){try{const s=await api('auth/status');if(!s.initialized){if(s.setup_via_cli){$('#app').innerHTML='<main class="auth-screen"><section class="auth-panel"><div class="auth-inner"><h2>TrọFlow đang chờ khởi tạo quản trị viên</h2><p>Vì máy chủ được cấu hình public Internet, tài khoản Admin đầu tiên phải được tạo trực tiếp trên Ubuntu Server bởi chủ nhà.</p><p>Chạy lệnh: <code>docker exec -it troflow python scripts/bootstrap_admin.py</code></p><button class="btn btn-primary" data-action="reload">Tải lại sau khi khởi tạo</button></div></section></main>';return;}return renderAuth(true);}try{const a=await api('auth/me');state.user=a.user;state.csrf=a.csrf;state.view=canPage('dashboard')?'dashboard':firstPage()||'dashboard';renderShell();await refresh();}catch{renderAuth(false);}}catch(e){$('#app').innerHTML=`<div class="startup">${ic('alert',40)}<h2>Không kết nối được máy chủ</h2><p>${esc(e.message)}</p><button class="btn btn-primary" data-action="reload">Thử lại</button></div>`;}}
function renderAuth(first){
 state.user=null;state.csrf='';document.title=(first?'Thiết lập':'Đăng nhập')+' · TrọFlow';
 $('#app').innerHTML=`<main class="auth-screen"><section class="auth-panel"><div class="auth-inner">
 <div class="auth-brand"><span class="brand-symbol">${ic('home')}</span>TrọFlow<span style="color:#1cae9d">.</span></div>
 <div class="auth-overline">${first?'BẮT ĐẦU VỚI TRỌFLOW':'CHÀO MỪNG TRỞ LẠI'}</div>
 <h1>${first?'Thiết lập hệ thống quản lý':'Chào mừng trở lại 👋'}</h1>
 <p class="auth-lead">${first?'Tạo tài khoản quản trị đầu tiên để bắt đầu quản lý nhà trọ, khách thuê và dòng tiền.':'Đăng nhập để tiếp tục quản lý cơ sở, phòng trọ và các khoản thu chi của bạn.'}</p>
 <form id="auth-form">
 ${first?`<div class="field"><label for="full_name">Tên của bạn</label><input required maxlength="100" id="full_name" name="full_name" placeholder="Nguyễn Văn A" autocomplete="name"></div>`:''}
 <div class="field"><label for="username">Tên đăng nhập</label><input required id="username" name="username" minlength="3" maxlength="40" placeholder="Ví dụ: admin" autocomplete="username"></div>
 <div class="field"><label for="password">Mật khẩu</label><input required id="password" name="password" type="password" ${first?'minlength="10"':''} placeholder="${first?'Tối thiểu 10 ký tự':'Nhập mật khẩu của bạn'}" autocomplete="${first?'new-password':'current-password'}"></div>
 ${first?`<p class="meta-note" style="margin:0 0 20px">Dữ liệu chỉ được lưu trên máy chủ của bạn. Tài khoản này có toàn quyền quản trị.</p>`:''}
 <button type="submit" class="btn btn-primary btn-wide">${first?'Tạo tài khoản quản trị':'Đăng nhập hệ thống'} ${ic('chevron')}</button>
 </form>${!first?`<p class="meta-note" style="margin-top:16px">Bạn là khách thuê? <a href="/tenant">Đăng nhập cổng khách thuê</a></p>`:''}<div class="auth-prompt">TRỌFLOW • PRIVATE & SELF-HOSTED</div></div></section>
 <aside class="auth-art"><span class="auth-art-top">PROPERTY MANAGEMENT, SIMPLIFIED</span><div><h2>Quản lý tốt hơn.<br>Vận hành nhẹ hơn.</h2><p>Mọi căn phòng, hợp đồng, khoản thu và công việc bảo trì trong một không gian đơn giản, rõ ràng.</p></div><div class="auth-art-cards"><div class="auth-art-card"><strong>01</strong><span>Một nơi quản lý tất cả</span></div><div class="auth-art-card"><strong>24/7</strong><span>Truy cập trên mọi thiết bị</span></div><div class="auth-art-card"><strong>100%</strong><span>Dữ liệu bạn kiểm soát</span></div></div></aside></main>`;
 $('#auth-form').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;busy=true;const button=$('button[type=submit]',e.currentTarget);button.disabled=true;const fd=Object.fromEntries(new FormData(e.currentTarget));try{const result=await api(first?'auth/setup':'auth/login','POST',fd);state.user=result.user;state.csrf=result.csrf;state.view=canPage('dashboard')?'dashboard':firstPage()||'dashboard';renderShell();await refresh();toast('Chào mừng đến với TrọFlow!');}catch(err){toast(err.message,true);button.disabled=false;}finally{busy=false;}});
}
function navItem(view,name,icon,badgeValue=''){
 if(!canPage(view))return '';
 return `<button class="nav-item ${state.view===view?'active':''}" data-nav="${view}">${ic(icon)}<span>${name}</span>${badgeValue?`<span class="nav-badge">${badgeValue}</span>`:''}</button>`;
}
function renderShell(){
 document.title='TrọFlow — Quản lý nhà trọ';
 const admin=state.user?.role==='admin';
 $('#app').innerHTML=`<div class="layout"><div class="sidebar-overlay" id="side-overlay"></div><aside class="sidebar" id="sidebar">
  <a href="/" class="brand" data-nav="dashboard"><span class="brand-symbol">${ic('home')}</span>TrọFlow<span style="color:#41dac0">.</span></a>
  <div class="nav-label">TỔNG QUAN</div>${navItem('dashboard','Bảng điều khiển','dashboard')}
  <div class="nav-label">QUẢN LÝ CHO THUÊ</div>${navItem('properties','Cơ sở / Tòa nhà','building')}${navItem('rooms','Danh sách phòng','door')}${navItem('tenants','Khách thuê','users')}${navItem('contracts','Hợp đồng','contract')}
  <div class="nav-label">TÀI CHÍNH</div>${navItem('utilitymeters','Công tơ điện nước tổng','meter')}${navItem('readings','Chỉ số điện nước','meter')}${navItem('invoices','Hóa đơn tiền trọ','receipt')}${navItem('payments','Lịch sử thanh toán','wallet')}${navItem('expenses','Chi phí vận hành','expense')}
  ${navItem('deposits','Sổ tiền cọc','wallet')}${navItem('prepayments','Tiền thuê trả trước','calendar')}${navItem('services','Phí dịch vụ','layers')}${navItem('invoiceTools','Hóa đơn nháp & VietQR','receipt')}
  <div class="nav-label">VẬN HÀNH</div>${navItem('residents','Người cùng phòng','users')}${navItem('meterTools','Điện nước nâng cao','meter')}${navItem('tenantApprovals','Duyệt chỉ số khách thuê','check')}${navItem('handovers','Bàn giao & Trả phòng','contract')}${navItem('tickets','Yêu cầu sửa chữa','wrench')}${navItem('reports','Báo cáo thống kê','report')}${navItem('imports','Nhập dữ liệu Excel','download')}
  <div class="nav-label">HỆ THỐNG</div>${navItem('access','Phân quyền nhân viên','shield')}${navItem('automation','Hóa đơn định kỳ','clock')}${navItem('backups','Sao lưu / Phục hồi','settings')}${navItem('bankaccounts','Tài khoản ngân hàng & QR','wallet')}${navItem('zalo','Thông báo Zalo','bell')}${navItem('settings','Cài đặt','settings')}${admin?navItem('users','Quản lý tài khoản','users')+navItem('audit','Nhật ký thao tác','shield'):''}
  <div class="side-bottom"><div class="side-help">${ic('info')} <strong>TrọFlow Self-hosted</strong><p>Dữ liệu lưu an toàn trong Docker volume của riêng bạn.</p></div><div class="user-pill"><div class="avatar">${esc(initials(state.user?.full_name))}</div><div style="min-width:0"><strong>${esc(state.user?.full_name)}</strong><span>${admin?'Quản trị viên':'Nhân viên'}</span></div><button class="icon-btn" data-action="logout" title="Đăng xuất" style="margin-left:auto;background:transparent;color:#acbbcc;border:0">${ic('logout')}</button></div></div>
 </aside><div class="main-shell"><header class="topbar"><div class="topbar-left"><button class="icon-btn menu-trigger" data-action="menu" aria-label="Mở menu">${ic('menu')}</button><span class="breadcrumbs">TrọFlow &nbsp; / &nbsp; <b id="breadcrumb">${views[state.view]}</b></span></div><div class="topbar-right"><label class="top-search">${ic('search')}<input id="global-search" type="search" placeholder="Tìm trong trang hiện tại..." aria-label="Tìm kiếm"></label>${canPage('tickets')?`<button class="icon-btn" data-nav="tickets" title="Sự cố chưa xử lý">${ic('bell')}</button>`:''}<button class="icon-btn" data-action="refresh" title="Làm mới dữ liệu">${ic('refresh')}</button><div class="avatar" title="${esc(state.user?.full_name)}">${esc(initials(state.user?.full_name))}</div></div></header><main class="content" id="view-content"></main></div></div>`;
}
async function refresh(){try{
 const keys=['properties','rooms','tenants','contracts','readings','invoices','payments','expenses','tickets','dashboard'];
 const values=await Promise.all(keys.map(async x=>{try{return await api(x);}catch(e){if(e.status===403)return x==='dashboard'?{}:[];throw e;}}));
 keys.forEach((k,i)=>state.data[k]=values[i]);
 if(state.view==='tenantApprovals')await loadTenantApprovals();
 if(state.view==='reports')await loadReport();
 if(state.view==='utilitymeters')await loadUtilityData();
 if(['users','audit'].includes(state.view))await loadAdminPage();
 renderPage();
 }catch(e){toast(e.message,true);}
}
async function loadReport(){const params=new URLSearchParams({period:state.period});if(state.reportProperty)params.set('property_id',state.reportProperty);state.report=await api('reports?'+params);}
async function loadAdminPage(){if(state.view==='users')state.data.users=await api('users');if(state.view==='audit')state.data.audit=await api('audit');}
async function navigate(view){if(!views[view]||!canPage(view))return;
 state.view=view;state.search='';state.propertyFilter='';const input=$('#global-search');if(input)input.value='';
 $$('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.nav===view));const crumb=$('#breadcrumb');if(crumb)crumb.textContent=views[view];closeMenu();
 if(view==='tenantApprovals')await loadTenantApprovals();if(view==='reports')await loadReport();if(view==='utilitymeters')await loadUtilityData();if(['users','audit'].includes(view))await loadAdminPage();renderPage();window.scrollTo(0,0);
}
function closeMenu(){state.sidebar=false;$('#sidebar')?.classList.remove('open');$('#side-overlay')?.classList.remove('show')}
function heading(label,description,actions='',eyebrow='TRỌFLOW WORKSPACE'){
 return `<div class="page-heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${label}</h1><p>${description}</p></div><div class="page-actions">${actions}</div></div>`;
}
const addBtn=(entity,label)=>can(entity+'.'+(entity==='readings'?'record':entity==='payments'?'record':'create'))?`<button class="btn btn-primary" data-add="${entity}">${ic('plus')}${label}</button>`:'';
const exportBtn=entity=>can('export.execute')&&can(entity+'.view')?`<a class="btn btn-outline" href="/api/export/${entity}" title="Xuất dữ liệu CSV">${ic('download')} Xuất CSV</a>`:'';
const actionButtons=(entity,id,{view=false,edit=true,del=true,extra=''}={})=>`<div class="table-actions">${extra}${view?`<button data-view="${entity}" data-id="${id}" title="Xem chi tiết">${ic('eye')}</button>`:''}${edit&&can(entity+'.'+('edit'))?`<button data-edit="${entity}" data-id="${id}" title="Chỉnh sửa">${ic('edit')}</button>`:''}${del&&can(entity+'.'+(entity==='payments'?'delete':'delete'))?`<button class="delete" data-delete="${entity}" data-id="${id}" title="Xóa">${ic('trash')}</button>`:''}</div>`;
const filter=(items,keys)=>items.filter(row=>(!state.propertyFilter||String(row.property_id)===String(state.propertyFilter))&&(!state.search||keys.some(k=>String(row[k]??'').toLowerCase().includes(state.search.toLowerCase()))));
const propFilter=()=>`<select data-control="property" aria-label="Lọc cơ sở"><option value="">Tất cả cơ sở</option>${state.data.properties.map(p=>`<option value="${p.id}" ${String(state.propertyFilter)===String(p.id)?'selected':''}>${esc(p.name)}</option>`).join('')}</select>`;
const toolbar=(left,right,count)=>`<div class="toolbar"><div class="toolbar-left">${left}</div><div class="toolbar-right">${right||''}<span class="count">${count} mục</span></div></div>`;
const table=(head,body,count,empty='Chưa có dữ liệu',prompt='Bắt đầu bằng cách thêm mục đầu tiên.')=>body.length?`<div class="table-wrap"><table class="data-table"><thead><tr>${head.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${body.join('')}</tbody></table></div><div class="table-footer">Hiển thị ${count} bản ghi</div>`:emptyState(empty,prompt);
const emptyState=(title,description,action='')=>`<div class="empty-state"><div class="empty-icon">${ic('layers')}</div><h3>${esc(title)}</h3><p>${esc(description)}</p>${action}</div>`;
function renderPage(){const el=$('#view-content');if(!el||!state.user)return;
 if(standalonePages[state.view]){el.innerHTML=`<iframe title="${esc(views[state.view])}" class="feature-frame" src="/integrations?page=${standalonePages[state.view]}"></iframe>`;return;}
 if(integratedPages[state.view]){el.innerHTML=`<iframe title="${esc(views[state.view])}" class="feature-frame" src="/advanced?embedded=1&page=${integratedPages[state.view]}"></iframe>`;return;}
 try{const viewsRender={dashboard:pageDashboard,properties:pageProperties,utilitymeters:pageUtilityMeters,rooms:pageRooms,tenants:pageTenants,contracts:pageContracts,readings:pageReadings,invoices:pageInvoices,payments:pagePayments,expenses:pageExpenses,tickets:pageTickets,reports:pageReports,settings:pageSettings,tenantApprovals:pageTenantApprovals,users:pageUsers,audit:pageAudit};el.innerHTML=viewsRender[state.view]();}catch(e){console.error(e);el.innerHTML=emptyState('Không thể hiển thị trang',e.message);}
}
function pageDashboard(){const d=state.data.dashboard||{};const total=d.rooms_total||0;const occupied=d.occupied||0;const occupancy=total?Math.round(occupied/total*100):0;
 const max=Math.max(1,...(d.trends||[]).flatMap(x=>[x.income,x.expense]));
 const bars=(d.trends||[]).map(x=>`<div class="bar-group"><div class="bar" title="Thu ${amount(x.income)}" style="--h:${Math.max(1,Math.round(x.income/max*100))}%"></div><div class="bar expense" title="Chi ${amount(x.expense)}" style="--h:${Math.max(1,Math.round(x.expense/max*100))}%"></div><span class="bar-month">T${Number(x.period.slice(-2))}</span></div>`).join('');
 return heading(`Xin chào, ${esc(state.user.full_name)} 👋`,'Đây là bức tranh tổng quan hoạt động nhà trọ của bạn hôm nay.',`<button class="btn btn-outline" data-nav="reports">${ic('calendar')} ${monthVN(d.period)}</button>${addBtn('rooms','Thêm phòng')}`,'BẢNG ĐIỀU KHIỂN')+
 `<div class="dashboard-focus"> <section class="card card-padded"><div class="card-header"><div><h2>Công việc cần chú ý</h2><p>Những việc nên xử lý sớm</p></div></div><div class="alerts-list">${d.overdue?`<div class="alert-row">${ic('alert')} <span><b>${d.overdue} hóa đơn quá hạn.</b> Kiểm tra công nợ và liên hệ khách thuê.</span></div>`:''}${d.open_tickets?`<div class="alert-row">${ic('wrench')} <span><b>${d.open_tickets} yêu cầu sửa chữa</b> đang chờ xử lý.</span></div>`:''}${d.alerts?.map(x=>`<div class="alert-row">${ic('calendar')} <span>Hợp đồng <b>phòng ${esc(x.room_code)}</b> — ${x.tenant_photo_path?`<img class="tenant-photo" style="width:26px;height:26px;vertical-align:middle" src="/api/v2/files/${encodeURIComponent(x.tenant_photo_path)}" alt="Ảnh khách">`:''} <b>${esc(x.tenant_name)}</b> ${x.tenant_phone?' · '+esc(x.tenant_phone):''}${x.tenant_id_number?' · CCCD: '+esc(x.tenant_id_number):''} hết hạn ${dateVN(x.end_date)}.</span></div>`).join('')||''}${!d.overdue&&!d.open_tickets&&!d.alerts?.length?`<div class="empty-mini">${ic('check')} Không có cảnh báo cần xử lý.</div>`:''}</div><div class="separator"></div><div class="card-header"><h2>Thao tác nhanh</h2></div><div class="quick-actions"><button class="quick-action" data-add="contracts" ${can('contracts.create')?'':'disabled'}>${ic('contract')} Ký hợp đồng</button><button class="quick-action" data-add="readings" ${can('readings.record')?'':'disabled'}>${ic('meter')} Ghi điện nước</button><button class="quick-action" data-action="generate" ${can('invoices.publish')?'':'disabled'}>${ic('receipt')} Lập hóa đơn</button><button class="quick-action" data-add="payments" ${can('payments.record')?'':'disabled'}>${ic('wallet')} Ghi thu tiền</button></div></section></div><div class="metrics-grid">
 ${metric('TỔNG SỐ PHÒNG',total,'door',`${occupied} phòng đang có người thuê`)}
 ${metric('TỶ LỆ LẤP ĐẦY',occupancy+'%','users',`${Math.max(0,total-occupied)} phòng chưa có người thuê`,'purple')}
 ${metric('THỰC THU THÁNG NÀY',compact(d.cash_in)+' ₫','wallet',`Đã lập hóa đơn ${compact(d.billed)} ₫`,'orange')}
 ${metric('CHỜ XỬ LÝ',d.open_tickets||0,'wrench',`${d.overdue||0} hóa đơn quá hạn`,'rose')}
 </div><div class="dashboard-grid">
 <section class="card card-padded"><div class="card-header"><div><h2>Dòng tiền 6 tháng gần đây</h2><p>So sánh tổng thu và tổng chi thực tế</p></div><div class="chart-legend"><span><i class="legend-dot"></i> Thu</span><span><i class="legend-dot expense"></i> Chi</span></div></div><div class="bars">${bars}</div><div class="chart-summary"><div><strong>${amount(d.cash_in)}</strong><span>Tổng thu ${monthVN(d.period)}</span></div><div><strong>${amount(d.cash_out)}</strong><span>Tổng chi ${monthVN(d.period)}</span></div></div></section>
 <section class="card card-padded"><div class="card-header"><div><h2>Tình trạng phòng</h2><p>Hiệu suất khai thác hiện tại</p></div><button class="btn btn-outline btn-sm" data-nav="rooms">Chi tiết ${ic('chevron')}</button></div><div class="occupancy-donut" style="--pct:${occupancy}%"><div class="donut-hole"><strong>${occupancy}%</strong><span>Đã lấp đầy</span></div></div><div class="occupancy-legend"><span><i class="legend-dot"></i>Đang thuê <b>${occupied}</b></span><span><i class="legend-dot expense"></i>Chưa thuê <b>${Math.max(0,total-occupied)}</b></span></div><div class="separator"></div>${(d.properties||[]).length?d.properties.slice(0,3).map(p=>`<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:13px;font-size:11px"><span style="color:#748197;max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(p.name)}</span><strong>${p.occupied||0}/${p.total} phòng</strong></div>`).join(''):'<div class="empty-mini">Chưa có cơ sở nào</div>'}</section>
 </div><div class="dash-bottom"><section class="card card-padded"><div class="card-header"><div><h2>Thanh toán gần đây</h2><p>Các giao dịch được ghi nhận mới nhất</p></div><button class="btn btn-outline btn-sm" data-nav="payments">Xem tất cả ${ic('chevron')}</button></div>${d.recent_payments?.length?d.recent_payments.map(x=>`<div class="list-row"><div class="list-main">${x.tenant_photo_path?`<img class="tenant-photo" src="/api/v2/files/${encodeURIComponent(x.tenant_photo_path)}" alt="Ảnh khách thuê">`:`<div class="list-avatar">${esc(initials(x.tenant_name))}</div>`}<div><strong>${esc(x.tenant_name)}</strong><small>${esc(x.property_name)} · Phòng ${esc(x.room_code)}${x.tenant_phone?' · '+esc(x.tenant_phone):''}${x.tenant_id_number?' · CCCD: '+esc(x.tenant_id_number):''}</small></div></div><div class="list-right"><strong class="positive">+${amount(x.amount)}</strong><small>${dateVN(x.paid_at)}</small></div></div>`).join(''):'<div class="empty-mini">Chưa có giao dịch thanh toán.</div>'}</section>
</div>`;
}
function metric(label,value,iconName,foot,color=''){return `<section class="metric-card"><div class="metric-head"><span>${label}</span><div class="metric-icon ${color}">${ic(iconName)}</div></div><div class="metric-num">${esc(value)}</div><div class="metric-foot">${esc(foot)}</div></section>`}
function pageProperties(){let arr=filter(state.data.properties,['name','address','manager_phone']);const admin=state.user.role==='admin';
 return heading('Cơ sở & Tòa nhà','Quản lý nhiều khu trọ trên cùng một nền tảng.',`${exportBtn('properties')}${admin?addBtn('properties','Thêm cơ sở'):''}`)+
 (arr.length?`<div class="property-stack">${arr.map(p=>`<div class="card property-card"><div style="display:flex;justify-content:space-between;align-items:flex-start"><div class="property-letter">${esc(initials(p.name))}</div>${admin?actionButtons('properties',p.id,{del:!p.room_count}).replace('class="table-actions"','class="table-actions"'):''}</div><h3 style="margin:18px 0 6px;font-size:16px">${esc(p.name)}</h3><p class="muted" style="min-height:32px;font-size:11px;line-height:1.5">${ic('building',14)} ${esc(p.address||'Chưa cập nhật địa chỉ')}</p><div class="progress" style="margin-top:19px"><div style="width:${p.room_count?Math.round(p.occupied_count/p.room_count*100):0}%"></div></div><div class="property-foot"><span>${p.occupied_count} / ${p.room_count} phòng đã thuê</span><b>${p.room_count?Math.round(p.occupied_count/p.room_count*100):0}%</b></div><div class="separator"></div><div class="config-row"><span>Giá điện</span><strong>${amount(p.electric_rate)}/kWh</strong></div><div class="config-row"><span>Giá nước</span><strong>${amount(p.water_rate)}/m³</strong></div><div class="config-row"><span>Phí dịch vụ / phòng</span><strong>${amount(p.service_fee)}</strong></div></div>`).join('')}</div>`:emptyState('Chưa có cơ sở','Tạo cơ sở đầu tiên để bắt đầu thêm phòng trọ.',admin?addBtn('properties','Thêm cơ sở'):''));
}
function pageRooms(){const arr=filter(state.data.rooms,['code','floor','property_name','tenant_name','status']);
 return heading('Danh sách phòng','Theo dõi phòng trống, đang cho thuê và tình trạng vận hành.',`${exportBtn('rooms')}${addBtn('rooms','Thêm phòng')}`)+`<div class="card" style="margin-bottom:20px">${toolbar(propFilter()+`<select data-control="roomMode" aria-label="Kiểu hiển thị"><option value="cards" ${state.roomMode==='cards'?'selected':''}>Dạng thẻ</option><option value="table" ${state.roomMode==='table'?'selected':''}>Dạng bảng</option></select>`,'',arr.length)}</div>`+
 (state.roomMode==='cards'?arr.length?`<div class="room-grid">${arr.map(r=>`<div class="room-card"><div class="room-top"><div class="room-mark">${ic('door',22)}</div>${badge(r.status)}</div><h3>Phòng ${esc(r.code)}</h3><p>${esc(r.property_name)}${r.floor?' · Tầng '+esc(r.floor):''} · ${num(r.area)} m²</p><div style="min-height:23px;font-size:11px;color:#667993">${r.tenant_name?`${tenantLabel(r)}`:`${ic('info',14)} Chưa có khách thuê`}</div><div class="room-split"><div><small>Giá thuê / tháng</small><strong style="display:block;margin-top:5px">${amount(r.rent)}</strong></div>${actionButtons('rooms',r.id)}</div></div>`).join('')}</div>`:emptyState('Chưa có phòng phù hợp','Hãy thêm phòng mới hoặc thay đổi bộ lọc.',addBtn('rooms','Thêm phòng')):
 `<div class="card">${table(['PHÒNG','CƠ SỞ','DIỆN TÍCH','GIÁ THUÊ','KHÁCH THUÊ','TRẠNG THÁI',''],arr.map(r=>`<tr><td><div class="cell-name">${esc(r.code)}</div><div class="cell-sub">${esc(r.floor)}</div></td><td>${esc(r.property_name)}</td><td>${num(r.area)} m²</td><td class="cell-name">${amount(r.rent)}</td><td>${tenantLabel(r)}</td><td>${badge(r.status)}</td><td>${actionButtons('rooms',r.id)}</td></tr>`),arr.length)}</div>`);
}
function pageTenants(){const arr=filter(state.data.tenants,['full_name','phone','email','id_number','room_codes']);
 return heading('Khách thuê','Thông tin liên hệ và hồ sơ người thuê.',`${exportBtn('tenants')}${addBtn('tenants','Thêm khách thuê')}`)+`<div class="card">${toolbar('Danh sách khách thuê','',arr.length)}${table(['KHÁCH THUÊ','LIÊN HỆ','CCCD','PHÒNG ĐANG THUÊ','TRẠNG THÁI',''],arr.map(t=>`<tr><td><div class="list-main">${t.photo_path?`<img class="tenant-photo" src="/api/v2/files/${encodeURIComponent(t.photo_path)}" alt="Ảnh ${esc(t.full_name)}">`:`<div class="list-avatar">${esc(initials(t.full_name))}</div>`}<div><strong>${esc(t.full_name)}</strong><small>Thêm ngày ${dateVN(t.created_at)}</small></div></div></td><td>${esc(t.phone)}<div class="cell-sub">${esc(t.email||'')}</div></td><td>${esc(t.id_number||'—')}</td><td>${esc(t.room_codes||'—')}</td><td>${t.active_contracts?badge('active'):badge('ended')}</td><td>${actionButtons('tenants',t.id,{del:!t.active_contracts})}</td></tr>`),arr.length,'Chưa có khách thuê','Thêm khách thuê trước khi tạo hợp đồng.')}</div>`;
}
function tenantLabel(item){
 const name=item.tenant_name||item.full_name;
 if(!name)return '<span class="muted">Chưa có khách thuê</span>';
 const photo=item.tenant_photo_path||item.photo_path;
 const phone=item.tenant_phone||item.phone;
 const id=item.tenant_id_number||item.id_number;
 return `<div class="list-main tenant-identity">${photo?`<img class="tenant-photo" src="/api/v2/files/${encodeURIComponent(photo)}" alt="Ảnh người thuê">`:`<div class="list-avatar">${esc(initials(name))}</div>`}<div><strong>${esc(name)}</strong><small>${esc(phone||'Chưa có SĐT')}${id?' · CCCD: '+esc(id):''}</small></div></div>`;
}
function pageContracts(){const arr=filter(state.data.contracts,['tenant_name','room_code','property_name','status']);
 return heading('Hợp đồng thuê','Quản lý thời hạn, giá thuê, tiền cọc và khách thuê.',`${exportBtn('contracts')}${addBtn('contracts','Tạo hợp đồng')}`)+`<div class="card">${toolbar(propFilter(),'',arr.length)}${table(['MÃ HỢP ĐỒNG','PHÒNG & CƠ SỞ','KHÁCH THUÊ','THỜI HẠN','GIÁ THUÊ','TRẠNG THÁI',''],arr.map(c=>`<tr><td class="cell-name">HĐ-${String(c.id).padStart(4,'0')}</td><td><div class="cell-name">${esc(c.room_code)}</div><div class="cell-sub">${esc(c.property_name)}</div></td><td>${tenantLabel(c)}</td><td>${dateVN(c.start_date)}<div class="cell-sub">đến ${dateVN(c.end_date)}</div></td><td class="cell-name">${amount(c.monthly_rent)}</td><td>${badge(c.status)}</td><td><div class="table-actions">${c.status==='active'?`${can('contracts.edit')?`<button data-edit="contracts" data-id="${c.id}" title="Sửa hợp đồng">${ic('edit')}</button>`:''}${can('contracts.end')?`<button data-end="${c.id}" title="Kết thúc hợp đồng">${ic('check')}</button>`:''}`:''}${can('contracts.delete')?`<button class="delete" data-delete="contracts" data-id="${c.id}" title="Xóa hợp đồng chưa phát sinh giao dịch">${ic('trash')}</button>`:''}</div></td></tr>`),arr.length,'Chưa có hợp đồng','Bạn cần có phòng và khách thuê để tạo hợp đồng mới.')}</div>`;
}
function pageReadings(){const arr=filter(state.data.readings.filter(x=>String(x.period).startsWith(String(state.readingsYear)+'-')),['room_code','property_name','tenant_name','period']);
 const years=[...new Set([state.readingsYear,...(state.data.readings||[]).map(x=>Number(x.period.slice(0,4))),Number(today().slice(0,4))])].sort((a,b)=>b-a);
 const yearInput=`<select data-control="readingsYear" aria-label="Năm thống kê">${years.map(y=>`<option value="${y}" ${state.readingsYear===y?'selected':''}>Cả năm ${y}</option>`).join('')}</select>`;
 return heading('Chỉ số điện & nước','Chốt chỉ số tiêu thụ làm cơ sở tính hóa đơn hằng tháng.',`${exportBtn('readings')}${addBtn('readings','Ghi chỉ số')}`)+`<div class="info-banner">${ic('info')} Mỗi phòng ghi một bộ chỉ số theo kỳ. Chỉ số đã phát hành hóa đơn sẽ được khóa để bảo vệ số liệu.</div><div class="card">${toolbar(propFilter()+yearInput,'',arr.length)}${table(['PHÒNG / NGƯỜI THUÊ','ĐIỆN CŨ / MỚI','ĐIỆN TIÊU THỤ','NƯỚC CŨ / MỚI','NƯỚC TIÊU THỤ','KỲ',''],arr.map(x=>`<tr><td><div class="cell-name">${esc(x.room_code)}</div><div class="cell-sub">${esc(x.property_name)}</div><div class="cell-sub">${tenantLabel(x)}</div></td><td>${readNum(x.electric_old)} → <b>${readNum(x.electric_new)}</b></td><td class="cell-name">${readNum(x.electric_usage)} kWh</td><td>${readNum(x.water_old)} → <b>${readNum(x.water_new)}</b></td><td class="cell-name">${readNum(x.water_usage)} m³</td><td>${monthVN(x.period)}<div class="reading-thumbs">${x.electric_photo?`<a href="/api/v2/files/${encodeURIComponent(x.electric_photo)}" target="_blank" rel="noopener"><img src="/api/v2/files/${encodeURIComponent(x.electric_photo)}" alt="Ảnh công tơ điện"></a>`:''}${x.water_photo?`<a href="/api/v2/files/${encodeURIComponent(x.water_photo)}" target="_blank" rel="noopener"><img src="/api/v2/files/${encodeURIComponent(x.water_photo)}" alt="Ảnh công tơ nước"></a>`:''}</div></td><td>${actionButtons('readings',x.id,{del:true})}</td></tr>`),arr.length,'Chưa ghi số điện nước','Hãy ghi số điện nước trước khi phát hành hóa đơn.')}</div>`;
}
function invoiceStatus(x){if(x.status==='void')return 'void';if(x.status==='draft')return 'unpaid';if(x.balance<=0)return 'paid';if(x.due_date<today())return 'overdue';if(x.paid>0)return 'partial';return 'unpaid'}
function periodInput(){return `<input type="month" data-control="period" value="${state.period}" aria-label="Chọn tháng">`}
function invoiceYearInput(){const years=[...new Set([state.invoicesYear,Number(today().slice(0,4)),...(state.data.invoices||[]).map(x=>Number(x.period.slice(0,4)) )])].sort((a,b)=>b-a);return `<select data-control="invoicesYear" aria-label="Năm hóa đơn">${years.map(y=>`<option value="${y}" ${state.invoicesYear===y?'selected':''}>Cả năm ${y}</option>`).join('')}</select>`;}
function pageInvoices(){const arr=filter(state.data.invoices.filter(x=>String(x.period).startsWith(String(state.invoicesYear)+'-')),['tenant_name','room_code','property_name','period']);
 return heading('Hóa đơn tiền trọ','Thu tiền phòng tháng lập hóa đơn; điện nước là kỳ tiêu thụ tháng trước.',`${exportBtn('invoices')}${can('invoices.publish')?`<button class="btn btn-primary" data-action="generate">${ic('plus')} Lập hóa đơn</button>`:''}`)+
 `<div class="info-banner">Tiền phòng tháng 10/2026 + điện/nước tháng 09/2026. Kỳ điện nước của hóa đơn cũ vẫn giữ nguyên cho đến khi Admin phát hành lại; không tự dịch chuyển số liệu đã chốt.</div><div class="card">${toolbar(propFilter()+invoiceYearInput(),'',arr.length)}${table(['HÓA ĐƠN','KHÁCH / PHÒNG','TỔNG TIỀN','ĐÃ THU','CÒN NỢ','HẠN THU','TRẠNG THÁI',''],arr.map(x=>`<tr><td><div class="cell-name">HD-${String(x.id).padStart(5,'0')}</div><div class="cell-sub">Tiền phòng: ${monthVN(x.period)}<br>Điện/nước: ${monthVN(x.utility_period||x.period)}</div></td><td>${tenantLabel(x)}<div class="cell-sub">${esc(x.property_name)} · P.${esc(x.room_code)}</div></td><td class="cell-name">${amount(x.total)}</td><td class="positive">${amount(x.paid)}${x.unapplied_credit>0?`<div class="cell-sub negative">Thu thừa ${amount(x.unapplied_credit)}</div>`:''}</td><td class="${x.balance?'negative':''}">${amount(x.balance)}</td><td>${dateVN(x.due_date)}</td><td>${badge(invoiceStatus(x))}</td><td><div class="table-actions"><button data-view="invoices" data-id="${x.id}" title="Xem & in">${ic('eye')}</button>${x.balance>0&&x.status==='published'&&can('payments.record')?`<button data-pay="${x.id}" title="Ghi nhận thu tiền">${ic('wallet')}</button>`:''}${state.user?.role==='admin'?`<button type="button" data-invoice-reissue="${x.id}" title="Sửa kỳ điện nước và phát hành lại">${ic('edit')}</button>${x.status!=='void'?`<button type="button" class="delete" data-invoice-void="${x.id}" title="Hủy hóa đơn, giữ nguyên thanh toán">${ic('trash')}</button>`:''}`:''}${state.user?.role!=='admin'&&!x.paid&&x.status!=='void'&&can('invoices.delete')?`<button class="delete" data-delete="invoices" data-id="${x.id}" title="Xóa hóa đơn">${ic('trash')}</button>`:''}</div></td></tr>`),arr.length,'Chưa có hóa đơn kỳ này','Ghi điện nước, sau đó chọn “Lập hóa đơn”.')}</div>`;
}
function pagePayments(){const arr=filter(state.data.payments,['tenant_name','room_code','property_name','period','method']);
 return heading('Lịch sử thanh toán','Các giao dịch tiền mặt và chuyển khoản đã được ghi nhận.',`${exportBtn('payments')}${addBtn('payments','Ghi nhận thu tiền')}`)+`<div class="card">${toolbar(propFilter(),'',arr.length)}${table(['MÃ GIAO DỊCH','KHÁCH THUÊ','HÓA ĐƠN','SỐ TIỀN','HÌNH THỨC','NGÀY THU',''],arr.map(x=>`<tr><td class="cell-name">TT-${String(x.id).padStart(5,'0')}</td><td>${tenantLabel(x)}<div class="cell-sub">${esc(x.property_name)} · ${esc(x.room_code)}</div></td><td>${monthVN(x.period)}</td><td class="cell-name positive">+${amount(x.amount)}</td><td>${esc(methods[x.method]||x.method)}</td><td>${dateVN(x.paid_at)}</td><td>${actionButtons('payments',x.id)}</td></tr>`),arr.length,'Chưa có giao dịch','Thu tiền theo hóa đơn để theo dõi công nợ chính xác.')}</div>`;
}
function pageExpenses(){const arr=filter(state.data.expenses,['property_name','category','description','spent_on']);
 return heading('Chi phí vận hành','Theo dõi các khoản chi để biết lợi nhuận thực tế.',`${exportBtn('expenses')}${addBtn('expenses','Thêm khoản chi')}`)+`<div class="card">${toolbar(propFilter(),'',arr.length)}${table(['NGÀY CHI','CƠ SỞ','LOẠI CHI','NỘI DUNG','SỐ TIỀN',''],arr.map(x=>`<tr><td>${dateVN(x.spent_on)}</td><td class="cell-name">${esc(x.property_name)}</td><td>${esc(categories[x.category]||x.category)}</td><td>${esc(x.description||'—')}</td><td class="cell-name negative">-${amount(x.amount)}</td><td>${actionButtons('expenses',x.id)}</td></tr>`),arr.length,'Chưa ghi nhận chi phí','Bổ sung các khoản chi vận hành để báo cáo phản ánh đúng dòng tiền.')}</div>`;
}
function pageTickets(){const arr=filter(state.data.tickets,['title','room_code','property_name','description','category','status']);
 return heading('Yêu cầu sửa chữa','Tiếp nhận, ưu tiên và theo dõi tiến độ xử lý sự cố.',`${exportBtn('tickets')}${addBtn('tickets','Tạo yêu cầu')}`)+`<div class="card">${toolbar(propFilter(),'',arr.length)}${table(['SỰ CỐ','PHÒNG','DANH MỤC','ƯU TIÊN','NGÀY BÁO','TRẠNG THÁI',''],arr.map(x=>`<tr><td><div class="cell-name">${esc(x.title)}</div><div class="cell-sub" style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(x.description||'Không có mô tả')}</div>${x.reported_by_tenant_id?'<div class="cell-sub" style="color:#0a9486">Khách thuê gửi</div>':''}<button type="button" class="btn btn-outline" data-ticket-photos="${x.id}">${ic('images')} Xem ảnh</button></td><td><div class="cell-name">${esc(x.room_code)}</div><div class="cell-sub">${esc(x.property_name)}</div></td><td>${esc(categories[x.category]||x.category)}</td><td>${badge(x.priority)}</td><td>${dateVN(x.reported_at)}</td><td>${badge(x.status)}</td><td>${actionButtons('tickets',x.id)}</td></tr>`),arr.length,'Không có sự cố','Thêm sự cố khi có hạng mục cần sửa chữa.')}</div>`;
}
function pageReports(){const r=state.report;if(!r)return heading('Báo cáo tài chính','Dữ liệu đang được tải...');
 const arr=r.invoices||[];
 const categoriesHTML=r.expenses_by_category.length?`<div class="card card-padded"><div class="card-header"><h2>Chi phí theo hạng mục</h2></div>${r.expenses_by_category.map(x=>{const pct=r.cash_out?Math.round(x.amount/r.cash_out*100):0;return `<div style="margin-bottom:18px"><div class="property-foot" style="margin:0 0 9px"><span>${esc(categories[x.category]||x.category)}</span><b>${amount(x.amount)} · ${pct}%</b></div><div class="progress"><div style="width:${pct}%"></div></div></div>`}).join('')}</div>`:`<div class="card card-padded"><div class="card-header"><h2>Chi phí theo hạng mục</h2></div><div class="empty-mini">Chưa có chi phí trong tháng này.</div></div>`;
 return heading('Báo cáo & Phân tích','Báo cáo theo kỳ hóa đơn và dòng tiền theo ngày giao dịch.',`${exportBtn('invoices')}<button class="btn btn-outline" data-action="refresh">${ic('refresh')} Cập nhật</button>`)+
 `<div class="card" style="margin-bottom:20px">${toolbar(`<select data-control="reportProperty" aria-label="Lọc cơ sở"><option value="">Tất cả cơ sở</option>${state.data.properties.map(p=>`<option value="${p.id}" ${String(state.reportProperty)===String(p.id)?'selected':''}>${esc(p.name)}</option>`).join('')}</select>`+periodInput(),`<span class="count">Dữ liệu ${monthVN(state.period)}</span>`,r.invoice_count)}</div>
 <div class="report-cards"><div class="card report-card"><div class="label">TỔNG HÓA ĐƠN ĐÃ LẬP</div><strong>${amount(r.billed)}</strong><small>${r.invoice_count} hóa đơn trong kỳ</small></div><div class="card report-card"><div class="label">DÒNG TIỀN THỰC THU</div><strong class="positive">${amount(r.cash_in)}</strong><small>Tiền nhận trong ${monthVN(state.period)}</small></div><div class="card report-card"><div class="label">DÒNG TIỀN THỰC CHI</div><strong class="negative">${amount(r.cash_out)}</strong><small>Chi phí phát sinh trong kỳ</small></div></div>
 <div class="dashboard-grid"><div class="card card-padded"><div class="card-header"><h2>Tổng kết công nợ & kết quả thu chi</h2></div><div class="kpi-strip"><div><strong>${amount(r.paid_for_period)}</strong><span>Đã thu cho hóa đơn kỳ này</span></div><div><strong class="negative">${amount(r.remaining)}</strong><span>Công nợ chưa thu của kỳ</span></div><div><strong class="${r.net_cashflow<0?'negative':'positive'}">${amount(r.net_cashflow)}</strong><span>Dòng tiền thuần trong tháng</span></div></div><div class="separator"></div><div class="info-banner" style="margin:0">${ic('info')} “Thực thu” và “thực chi” ghi nhận theo ngày giao dịch; “đã thu cho hóa đơn kỳ này” tính theo kỳ hóa đơn, có thể khác nhau.</div></div>${categoriesHTML}</div>
 <div class="card"><div class="toolbar"><strong style="font-size:13px">Đối soát hóa đơn ${monthVN(state.period)}</strong><span class="count">${r.unpaid_count} hóa đơn còn dư nợ</span></div>${table(['PHÒNG','KHÁCH THUÊ','TỔNG','ĐÃ THU','CÒN NỢ','TRẠNG THÁI'],arr.map(x=>`<tr><td class="cell-name">${esc(x.room_code)}</td><td>${tenantLabel(x)}</td><td>${amount(x.total)}</td><td class="positive">${amount(x.paid)}${x.unapplied_credit>0?`<div class="cell-sub negative">Thu thừa ${amount(x.unapplied_credit)}</div>`:''}</td><td class="${x.balance?'negative':''}">${amount(x.balance)}</td><td>${badge(invoiceStatus(x))}</td></tr>`),arr.length,'Không có hóa đơn kỳ này','Chọn kỳ khác hoặc lập hóa đơn để bắt đầu đối soát.')}</div>`;
}
function pageSettings(){const admin=state.user.role==='admin';
 return heading('Cài đặt & Sao lưu','Quản lý dữ liệu, bảo mật và cấu hình hệ thống.',`<button class="btn btn-outline" data-action="password">${ic('shield')} Đổi mật khẩu</button>`)+
 `${admin?`<section class="card settings-tile" style="margin-bottom:20px"><div class="card-header"><h2>Thông tin chủ cho thuê cho khách thuê</h2></div><p>Họ tên, giới tính, tuổi, ảnh, địa chỉ, số điện thoại, email. Chọn cơ sở và bật/tắt riêng từng thông tin hiển thị trong cổng khách thuê.</p><button class="btn btn-primary" data-action="owner-settings">${ic('settings')} Cấu hình chủ cho thuê</button></section>`:''}<div class="settings-grid"><section class="card settings-tile"><div class="card-header"><h2>Xuất dữ liệu ra CSV</h2></div><p>Tải danh sách để lưu trữ, kiểm tra đối soát hoặc mở bằng Excel. File được mã hóa UTF-8 để hiển thị tiếng Việt.</p><div class="export-grid">${[['properties','Cơ sở'],['rooms','Phòng trọ'],['tenants','Khách thuê'],['contracts','Hợp đồng'],['readings','Điện nước'],['invoices','Hóa đơn'],['payments','Thanh toán'],['expenses','Chi phí'],['tickets','Sự cố']].map(([k,label])=>`<a class="export-item" href="/api/export/${k}">${esc(label)} ${ic('download',15)}</a>`).join('')}</div></section>
 <section class="card settings-tile"><div class="card-header"><h2>Sao lưu dữ liệu</h2></div><p>Tạo bản sao SQLite đầy đủ gồm thông tin cơ sở, khách thuê, hợp đồng, hóa đơn, thanh toán và tài khoản. File sao lưu chứa dữ liệu cá nhân, hãy bảo quản an toàn.</p>${admin?`<a class="btn btn-primary" href="/api/backup">${ic('download')} Tải bản sao lưu .sqlite3</a>`:`<div class="info-banner">${ic('shield')} Chỉ tài khoản quản trị được sao lưu toàn bộ hệ thống.</div>`}<div class="separator"></div><div class="config-row"><span>Hệ thống</span><strong>TrọFlow 4.0</strong></div><div class="config-row"><span>Cơ sở dữ liệu</span><strong>SQLite / Docker volume</strong></div><div class="config-row"><span>Quyền đang dùng</span><strong>${admin?'Quản trị viên':'Nhân viên'}</strong></div></section>
 <section class="card settings-tile"><div class="card-header"><h2>Bảo mật & vận hành</h2></div><p>TrọFlow sử dụng phiên đăng nhập có hạn, băm mật khẩu và phân quyền. Khi truy cập từ internet, cần bật HTTPS qua reverse proxy và cấu hình COOKIE_SECURE=1.</p><button class="btn btn-outline" data-action="password">${ic('shield')} Thay đổi mật khẩu</button></section>
 <section class="card settings-tile"><div class="card-header"><h2>Thiết lập đơn giá</h2></div><p>Giá điện, nước và phí dịch vụ được thiết lập riêng theo từng cơ sở. Các hóa đơn đã phát hành giữ nguyên giá trị ban đầu.</p><button class="btn btn-outline" data-nav="properties">${ic('building')} Quản lý giá theo cơ sở</button></section></div>`;
}
function pageUsers(){const arr=state.data.users||[];return heading('Tài khoản & Phân quyền','Quản trị viên được quyền thay đổi cấu hình, quản lý tài khoản và xóa dữ liệu.',addBtn('users','Thêm tài khoản'))+`<div class="card">${table(['HỌ TÊN','TÊN ĐĂNG NHẬP','QUYỀN','TRẠNG THÁI','NGÀY TẠO',''],arr.map(x=>`<tr><td class="cell-name">${esc(x.full_name)}</td><td>${esc(x.username)}</td><td>${x.role==='admin'?'Quản trị viên':'Nhân viên'}</td><td>${badge(x.active?'active':'inactive')}</td><td>${dateVN(x.created_at)}</td><td>${actionButtons('users',x.id,{del:false})}</td></tr>`),arr.length)}</div>`;}
function pageAudit(){const arr=state.data.audit||[];const actions={create:'Tạo mới',update:'Chỉnh sửa',delete:'Xóa',end:'Kết thúc',change_password:'Đổi mật khẩu'};
 return heading('Nhật ký thao tác','100 thao tác gần đây giúp truy vết các thay đổi trong hệ thống.',`<button class="btn btn-outline" data-action="refresh">${ic('refresh')} Làm mới</button>`)+`<div class="card">${table(['THỜI GIAN','NGƯỜI THỰC HIỆN','THAO TÁC','ĐỐI TƯỢNG','CHI TIẾT'],arr.map(x=>`<tr><td>${dateVN(x.created_at)} <span class="muted">${esc(String(x.created_at).slice(11,16))}</span></td><td class="cell-name">${esc(x.actor||'Hệ thống')}</td><td>${esc(actions[x.action]||x.action)}</td><td>${esc(x.entity)} #${x.entity_id??'—'}</td><td>${esc(x.details||'—')}</td></tr>`),arr.length,'Chưa có lịch sử','Nhật ký xuất hiện khi có thao tác quản lý.')}</div>`;
}

let modalContext=null;
let confirmAction=null;
function openModal(title,body,footer='',large=false){
 $('#modal-root').innerHTML=`<div class="modal-backdrop" id="modal-backdrop"><div class="modal ${large?'large':''}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal-header"><h2>${esc(title)}</h2><button class="icon-btn" data-action="close-modal" aria-label="Đóng">${ic('x')}</button></div><div class="modal-body">${body}</div>${footer?`<div class="modal-footer">${footer}</div>`:''}</div></div>`;
 const first=$('.modal-body input:not([type=hidden]),.modal-body select,.modal-body textarea');if(first)first.focus();
}
function closeModal(){const root=$('#modal-root');if(root)root.innerHTML='';if($('#print-root'))$('#print-root').innerHTML='';modalContext=null;confirmAction=null;}
const opt=(value,label)=>({value:String(value),label:String(label)});
const propertyOptions=()=>state.data.properties.map(x=>opt(x.id,x.name));
const roomOptions=(available=false,occupied=false)=>state.data.rooms.filter(x=>!available||x.status==='ready').filter(x=>!occupied||activeTenantFor(x.id,state.period)).map(x=>opt(x.id,`${x.property_name} · Phòng ${x.code}${x.tenant_name?' — '+x.tenant_name+(x.tenant_phone?' · '+x.tenant_phone:'')+(x.tenant_id_number?' · CCCD '+x.tenant_id_number:''):''}`));
const activeTenantFor=(roomId,billingPeriod)=>{const [y,m]=String(billingPeriod||thisMonth()).split('-').map(Number);if(!y||!m)return null;const first=`${y}-${String(m).padStart(2,'0')}-01`,last=`${y}-${String(m).padStart(2,'0')}-${String(new Date(y,m,0).getDate()).padStart(2,'0')}`;return (state.data.contracts||[]).find(c=>c.room_id===Number(roomId)&&c.start_date<=last&&c.end_date>=first)||null};
function updateReadingRooms(form){
 if(!form?.elements.room_id||!form.elements.period)return;
 const select=form.elements.room_id,chosen=select.value,period=form.elements.period.value;
 const candidates=(state.data.rooms||[]).filter(room=>activeTenantFor(room.id,period));
 select.innerHTML=candidates.length?candidates.map(room=>{
  const tenant=activeTenantFor(room.id,period);
  return `<option value="${room.id}">${esc(room.property_name)} · Phòng ${esc(room.code)} — ${esc(tenant.tenant_name)}</option>`;
 }).join(''):'<option value="">Không có phòng có người thuê kỳ này</option>';
 if(candidates.some(room=>String(room.id)===chosen))select.value=chosen;
 syncMeterTenant(form);
}
function syncMeterTenant(form){if(!form||!form.elements.room_id)return;const roomId=Number(form.elements.room_id.value),p=form.elements.period.value,c=activeTenantFor(roomId,p);const info=$('#reading-tenant');if(info)info.innerHTML=c?`Người thuê: <b>${esc(c.tenant_name)}</b> · HĐ-${c.id} · ${esc(c.start_date)} đến ${esc(c.end_date)}`:'<b style="color:#c64755">Phòng chưa có hợp đồng / người thuê trong kỳ này. Không thể tạo chỉ số.</b>';const save=document.querySelector('button[form="entity-form"]');if(save)save.disabled=!c;}

const tenantOptions=()=>state.data.tenants.map(x=>opt(x.id,`${x.full_name} · ${x.phone}${x.id_number?' · CCCD: '+x.id_number:''}`));
const invoiceOptions=()=>state.data.invoices.filter(x=>x.status==='published'&&x.balance>0).map(x=>opt(x.id,`${x.tenant_name} · P.${x.room_code} · ${monthVN(x.period)} · còn ${amount(x.balance)}`));
const choices=(obj)=>Object.entries(obj).map(([k,v])=>opt(k,v));
const F=(name,label,type='text',opts={})=>({name,label,type,...opts});
function schemaFor(entity,record=null,extra={}){
 const edit=!!record;const roomID=extra.room_id||'';
 switch(entity){
 case 'properties':return [F('name','Tên cơ sở','text',{required:true,full:true,placeholder:'Ví dụ: Nhà trọ Bình An'}),F('address','Địa chỉ','text',{full:true,placeholder:'Số nhà, đường, quận, thành phố'}),F('manager_phone','Số điện thoại liên hệ','tel',{full:true}),F('electric_rate','Đơn giá điện (₫/kWh)','number',{min:0}),F('water_rate','Đơn giá nước (₫/m³)','number',{min:0}),F('service_fee','Phí dịch vụ mỗi phòng (₫)','number',{min:0,full:true})];
 case 'rooms':return [F('property_id','Cơ sở','select',{required:true,options:propertyOptions()}),F('code','Mã phòng','text',{required:true,placeholder:'P101'}),F('floor','Tầng','text',{placeholder:'Tầng 1'}),F('area','Diện tích (m²)','number',{step:.1,min:0}),F('rent','Giá thuê mỗi tháng (₫)','number',{required:true,min:0}),F('deposit','Tiền cọc tham khảo (₫)','number',{min:0}),F('condition','Tình trạng phòng','select',{options:choices({ready:'Sẵn sàng',maintenance:'Đang bảo trì',inactive:'Ngừng sử dụng'})}),F('notes','Ghi chú','textarea',{full:true})];
 case 'tenants':return [F('full_name','Họ tên khách thuê','text',{required:true,full:true}),F('phone','Số điện thoại','tel',{required:true}),F('email','Email','email'),F('id_number','Số CCCD/CMND (9 hoặc 12 số)','text',{required:!edit,placeholder:'Ví dụ: 001234567890'}),F('hometown','Quê quán','text'),F('notes','Ghi chú','textarea',{full:true})];
 case 'contracts':return [
 ...(!edit?[F('room_id','Phòng cho thuê','select',{required:true,options:roomOptions(true)}),F('tenant_id','Khách thuê','select',{required:true,options:tenantOptions()})]:[]),
 F('start_date','Ngày bắt đầu','date',{required:true}),F('end_date','Ngày kết thúc','date',{required:true}),F('monthly_rent','Tiền thuê mỗi tháng (₫)','number',{required:true,min:0}),F('deposit','Tiền cọc (₫)','number',{min:0}),F('due_day','Ngày hạn thanh toán (1–28)','number',{min:1,max:28}),F('occupants','Số người ở','number',{min:1,max:50}),F('notes','Ghi chú hợp đồng','textarea',{full:true})];
 case 'readings':return [F('room_id','Phòng · Người thuê','select',{required:true,options:roomOptions()}),F('period','Kỳ chỉ số','month',{required:true}),F('electric_old','Số điện cũ (kWh)','number',{step:.001,min:0}),F('electric_new','Số điện mới (kWh)','number',{step:.001,min:0}),F('water_old','Số nước cũ (m³)','number',{step:.001,min:0}),F('water_new','Số nước mới (m³)','number',{step:.001,min:0})];
 case 'payments':return edit?[F('amount','Số tiền đã nhận (₫)','number',{required:true,min:1}),F('paid_at','Ngày thu tiền','date',{required:true}),F('method','Phương thức','select',{options:choices(methods)}),F('note','Ghi chú','textarea',{full:true})]:[F('invoice_id','Hóa đơn cần thu','select',{required:true,options:invoiceOptions()}),F('amount','Số tiền thanh toán (₫)','number',{required:true,min:1}),F('paid_at','Ngày thu tiền','date',{required:true}),F('method','Phương thức','select',{options:choices(methods)}),F('note','Ghi chú','textarea',{full:true})];
 case 'expenses':return [F('property_id','Cơ sở','select',{required:true,options:propertyOptions()}),F('category','Loại chi phí','select',{options:choices({repair:'Sửa chữa',utilities:'Điện nước',supplies:'Vật tư',operations:'Vận hành',salary:'Nhân công',other:'Khác'})}),F('amount','Số tiền (₫)','number',{required:true,min:1}),F('spent_on','Ngày chi','date',{required:true}),F('description','Mô tả khoản chi','textarea',{full:true})];
 case 'tickets':return [F('room_id','Phòng phát sinh','select',{required:true,options:roomOptions()}),F('category','Loại sự cố','select',{options:choices({electric:'Điện',water:'Nước',internet:'Internet',furniture:'Nội thất',other:'Khác'})}),F('title','Tiêu đề vấn đề','text',{required:true,full:true,placeholder:'Ví dụ: Điều hòa không làm lạnh'}),F('priority','Mức độ ưu tiên','select',{options:choices({low:'Thấp',medium:'Trung bình',high:'Cao'})}),F('status','Tiến độ','select',{options:choices({new:'Mới tiếp nhận',in_progress:'Đang xử lý',done:'Hoàn thành'})}),F('reported_at','Ngày báo','date',{required:true}),F('description','Nội dung yêu cầu','textarea',{full:true})];
 case 'users':return [F('full_name','Họ tên','text',{required:true,full:true}),...(!edit?[F('username','Tên đăng nhập','text',{required:true})]:[]),F('role','Vai trò','select',{options:choices({staff:'Nhân viên',admin:'Quản trị viên'})}),...(edit?[F('active','Trạng thái tài khoản','select',{options:[opt(1,'Đang hoạt động'),opt(0,'Đã khóa')]})]:[]),F('password',edit?'Mật khẩu mới (để trống nếu không thay đổi)':'Mật khẩu (tối thiểu 10 ký tự)','password',{required:!edit,full:true,minLength:10})];
 default:return [];
 }
}
function defaults(entity){switch(entity){
 case 'properties':return {electric_rate:3500,water_rate:20000,service_fee:100000};
 case 'rooms':return {area:20,rent:3000000,deposit:3000000,condition:'ready',property_id:state.propertyFilter||state.data.properties[0]?.id};
 case 'contracts':{const room=state.data.rooms.find(x=>x.status==='ready');const y=new Date().getFullYear();return {room_id:room?.id,tenant_id:state.data.tenants[0]?.id,start_date:today(),end_date:`${y+1}-${today().slice(5)}`,monthly_rent:room?.rent||3000000,deposit:room?.deposit||0,due_day:5,occupants:1};}
 case 'readings':return {room_id:state.data.rooms.find(x=>activeTenantFor(x.id,state.period))?.id,period:state.period,electric_old:0,electric_new:0,water_old:0,water_new:0};
 case 'payments':return {invoice_id:invoiceOptions()[0]?.value,amount:state.data.invoices.find(x=>x.status==='published'&&x.balance>0)?.balance||0,paid_at:today(),method:'transfer'};
 case 'expenses':return {property_id:state.propertyFilter||state.data.properties[0]?.id,category:'operations',amount:0,spent_on:today()};
 case 'tickets':return {room_id:state.data.rooms[0]?.id,category:'other',priority:'medium',status:'new',reported_at:today()};
 case 'users':return {role:'staff',active:1};default:return {};
}}
function fieldHTML(field,values){const val=values[field.name]??'';let input='';
 const req=field.required?'required':'';const min=field.min!==undefined?`min="${field.min}"`:'';const max=field.max!==undefined?`max="${field.max}"`:'';
 if(field.type==='select')input=`<select name="${field.name}" id="f-${field.name}" ${req}>${field.options?.length?field.options.map(o=>`<option value="${esc(o.value)}" ${String(o.value)===String(val)?'selected':''}>${esc(o.label)}</option>`).join(''):'<option value="">— Chưa có dữ liệu —</option>'}</select>`;
 else if(field.type==='textarea')input=`<textarea id="f-${field.name}" name="${field.name}" ${req} maxlength="1000" placeholder="${esc(field.placeholder||'Thêm ghi chú nếu cần')}">${esc(val)}</textarea>`;
 else input=`<input id="f-${field.name}" name="${field.name}" type="${field.type}" value="${esc(val)}" ${req} ${min} ${max} ${field.step?`step="${field.step}"`:''} ${field.minLength?`minlength="${field.minLength}"`:''} ${field.placeholder?`placeholder="${esc(field.placeholder)}"`:''} ${field.type==='number'?'inputmode="decimal"':''} autocomplete="off">`;
 return `<div class="field ${field.full?'full':''}"><label for="f-${field.name}">${esc(field.label)}${field.required?' <span style="color:#dc6470">*</span>':''}</label>${input}</div>`;
}
function openForm(entity,id=null,extra={}){
 const record=id?(state.data[entity]||[]).find(x=>String(x.id)===String(id)):null;
 if(id&&!record){toast('Không tìm thấy bản ghi.',true);return;}
 if((entity==='users'||(entity==='properties'&&!id))&&state.user.role!=='admin'){toast('Bạn không có quyền thực hiện thao tác này.',true);return;}
 const collection=state.data[entity]||[];
 const values={...defaults(entity),...(record||{}),...extra};
 if(entity==='readings'&&record)values.period=record.period;
 if(entity==='rooms'&&record?.status==='occupied')values.condition='ready';
 if(entity==='payments'&&extra.invoice_id){const invoice=state.data.invoices.find(x=>x.id===num(extra.invoice_id));values.amount=invoice?.balance||0;}
 const fields=schemaFor(entity,record,extra);
 if(!fields.length)return;
 const title=(record?'Chỉnh sửa ':'Thêm ')+({properties:'cơ sở',rooms:'phòng trọ',tenants:'khách thuê',contracts:'hợp đồng',readings:'chỉ số điện nước',payments:'giao dịch thu tiền',expenses:'khoản chi',tickets:'yêu cầu sửa chữa',users:'tài khoản'}[entity]||'dữ liệu');
 const hint=entity==='contracts'&&!record?'Hợp đồng chỉ được ký cho phòng đang sẵn sàng. Mỗi phòng có tối đa một hợp đồng hiệu lực.':entity==='readings'?'Chỉ số mới phải lớn hơn hoặc bằng chỉ số cũ. Có thể tự điền chỉ số kỳ trước khi chọn phòng.':entity==='users'?'Nhân viên có thể vận hành dữ liệu; chỉ quản trị viên quản lý tài khoản, sao lưu và xóa dữ liệu.':entity==='payments'?'Khoản thu được đối trừ vào hóa đơn được chọn và không được vượt quá số tiền còn thiếu.':'';
 modalContext={type:'entity',entity,id,values,fields};
 openModal(title,`<form id="entity-form"><div class="form-grid">${fields.map(f=>fieldHTML(f,values)).join('')}</div>${entity==='readings'?'<div class="modal-hint" id="reading-tenant" aria-live="polite"></div>':''}${entity==='tenants'&&state.user?.role==='admin'?tenantPortalPanel(record):''}${['readings','tenants'].includes(entity)?photoFields(entity,record):''}${entity==='tickets'?`<section class="ticket-photo-form"><label style="font-weight:700">Ảnh vị trí cần sửa chữa (tối đa 5 ảnh)</label><input type="file" name="photos" id="ticket-photos-input" accept="image/jpeg,image/png,image/webp" multiple><div id="ticket-photo-preview" class="ticket-photo-preview"></div>${record?`<button type="button" class="btn btn-outline" data-ticket-photos="${record.id}">Xem/xóa ảnh đã có</button>`:''}<p class="meta-note">Tối đa 5 ảnh, 3 MB mỗi ảnh, dùng chung với cổng khách thuê. Ảnh chỉ người có quyền được xem.</p></section>`:''}${hint?`<div class="modal-hint">${esc(hint)}</div>`:''}</form>`,
 `<button class="btn btn-outline" data-action="close-modal">Hủy</button><button class="btn btn-primary" type="submit" form="entity-form">${ic('check')} ${record?'Lưu thay đổi':'Tạo mới'}</button>`);
 if(entity==='readings'){updateReadingRooms($('#entity-form'));if(!record)fillPrevious();}
}
function tenantPortalPanel(record){
 const prop=record?.portal_property_id||state.data.properties?.[0]?.id||'';
 return `<section class="portal-admin-box"><h3>Tài khoản đăng nhập của khách thuê</h3><label class="portal-toggle"><input type="checkbox" name="portal_enabled" ${record?.portal_enabled?'checked':''}> Bật quyền đăng nhập cổng khách thuê</label>
 <label>Cơ sở áp dụng</label><select name="portal_property_id" required>${state.data.properties.map(p=>`<option value="${p.id}" ${String(prop)===String(p.id)?'selected':''}>${esc(p.name)}</option>`).join('')}</select>
 <p class="meta-note">User = số điện thoại; mật khẩu ban đầu = tên cuối của khách + _ + tên cơ sở (không dấu). Khách không có quyền đổi mật khẩu. Khi public Internet cần thêm mã bảo vệ do Admin cấp. Mã chỉ hiển thị một lần khi cấp hoặc đặt lại.</p>
 ${record?.portal_property_id?`<button class="btn btn-outline" type="button" data-portal-reset="${record.id}">${ic('refresh')} Cấp lại thông tin đăng nhập</button>`:''}</section>`;
}
function showPortalCredentials(data){
 if(!data)return;
 openModal('Thông tin đăng nhập khách thuê',`<div class="portal-admin-box"><p>Gửi trực tiếp các thông tin sau cho khách thuê qua kênh riêng. <b>Mã bảo vệ chỉ hiển thị lần này.</b></p><p>Số điện thoại: <strong>${esc(data.username)}</strong></p><p>Mật khẩu: <strong>${esc(data.password)}</strong></p><p>Mã bảo vệ: <strong>${esc(data.access_code)}</strong></p><p>Trang đăng nhập: <code>/tenant</code></p><p class="meta-note">Không gửi mật khẩu trong nhóm Zalo công khai. Đổi tên/cơ sở không tự thay đổi mật khẩu hiện có; Admin có thể cấp lại theo thông tin hiện tại.</p></div>`, `<button class="btn btn-primary" data-action="close-modal">Đã lưu thông tin</button>`);
}
async function loadTenantApprovals(){try{state.data.tenantApprovals=await api('tenant/admin/submissions');}catch(e){state.data.tenantApprovals=[];toast(e.message,true);}}
function pageTenantApprovals(){const arr=state.data.tenantApprovals||[];
 return heading('Duyệt chỉ số khách thuê','Ảnh và chỉ số do khách gửi chỉ trở thành chỉ số chính thức sau khi nhân viên có quyền duyệt xác nhận.',`<button class="btn btn-outline" data-action="refresh">${ic('refresh')} Cập nhật</button>`)
 +`<div class="card">${table(['PHÒNG / KHÁCH','KỲ','ĐIỆN','NƯỚC','ẢNH','TRẠNG THÁI','THAO TÁC'],arr.map(x=>`<tr><td><b>${esc(x.room_code)}</b> · ${esc(x.property_name)}<div class="cell-sub">${esc(x.tenant_name)} · ${esc(x.phone)}</div></td><td>${esc(x.period)}</td><td>${readNum(x.electric_old)} → <b>${readNum(x.electric_new)}</b></td><td>${readNum(x.water_old)} → <b>${readNum(x.water_new)}</b></td><td><a target="_blank" rel="noopener" href="/api/tenant/admin/submissions/${x.id}/photo/electric">Điện</a> · <a target="_blank" rel="noopener" href="/api/tenant/admin/submissions/${x.id}/photo/water">Nước</a></td><td>${esc({pending:'Đang chờ',approved:'Đã duyệt',rejected:'Đã từ chối'}[x.status]||x.status)}${x.feedback?`<div class="cell-sub">${esc(x.feedback)}</div>`:''}</td><td>${x.status==='pending'&&can('readings.record')?`<button class="btn btn-primary" data-meter-review="${x.id}" data-decision="approve">Duyệt</button> <button class="btn btn-outline" data-meter-review="${x.id}" data-decision="reject">Từ chối</button>`:'—'}</td></tr>`),arr.length,'Chưa có chỉ số khách gửi','Khách thuê sẽ gửi ảnh đồng hồ tại cổng /tenant.')}</div>`;
}
async function openOwnerSettings(){
 if(state.user?.role!=='admin')return;
 const props=state.data.properties||[];
 if(!props.length){toast('Hãy thêm cơ sở trước.',true);return;}
 const propertyId=Number(state.ownerProperty||props[0].id);
 try{
 const p=await api('tenant/admin/owner/'+propertyId);
 modalContext={type:'owner'};
 const fields=[['name','Họ tên','text'],['gender','Giới tính','text'],['age','Tuổi','number'],['address','Địa chỉ','text'],['phone','Số điện thoại','tel'],['email','Email','email']];
 const propertyOptions=props.map(x=>`<option value="${x.id}" ${x.id===propertyId?'selected':''}>${esc(x.name)}</option>`).join('');
 openModal('Chủ cho thuê & thông tin công khai',`<form id="owner-form" class="owner-fields"><label>Chọn cơ sở</label><select id="owner-property">${propertyOptions}</select><div class="form-grid">${fields.map(([key,label,type])=>`<div class="field"><label>${label}</label><input type="${type}" name="${key}" value="${esc(p[key]??'')}"><label class="portal-toggle"><input type="checkbox" name="show_${key}" ${p['show_'+key]?'checked':''}> Hiển thị cho khách thuê</label></div>`).join('')}</div><div class="field"><label>Ảnh chủ cho thuê</label>${p.photo_path?`<img class="tenant-photo" src="/api/tenant/admin/owner/${propertyId}/photo" alt="Ảnh chủ nhà">`:''}<input type="file" name="photo" accept="image/png,image/jpeg,image/webp"><label class="portal-toggle"><input type="checkbox" name="show_photo" ${p.show_photo?'checked':''}> Hiển thị ảnh chủ cho thuê</label></div><p class="meta-note">Thông tin không được tích chọn sẽ không có trong API khách thuê. Mỗi cơ sở có cấu hình riêng.</p></form>`,`<button class="btn btn-outline" data-action="close-modal">Hủy</button><button class="btn btn-primary" form="owner-form" type="submit">Lưu thông tin</button>`,true);
 }catch(e){toast(e.message,true);}
}
async function saveOwner(form){const prop=Number($('#owner-property').value);const d=new FormData(form);const payload={};for(const [k,v] of d.entries()){if(k!=='photo')payload[k]=v;}
 for(const k of ['name','gender','age','address','phone','email','photo'])payload['show_'+k]=form.elements['show_'+k]?.checked||false;
 try{await api('tenant/admin/owner/'+prop,'PUT',payload);const file=form.elements.photo.files[0];if(file){const body=new FormData();body.append('file',file);const r=await fetch('/api/tenant/admin/owner/'+prop+'/photo',{method:'POST',headers:{'x-csrf-token':state.csrf},body,credentials:'same-origin'});if(!r.ok){const detail=await r.json().catch(()=>({}));throw Error(detail.detail||'Không lưu được ảnh chủ nhà.');}}
 closeModal();toast('Đã lưu thông tin và các trường công khai.');}catch(e){toast(e.message,true);}}
function photoFields(entity,record){
 const uploadable=can('files.upload')&&(entity==='tenants'?can('tenants.edit'):can('readings.photos'));
 if(!uploadable)return '<div class="modal-hint">Bạn không có quyền tải ảnh lên. Liên hệ quản trị viên để cấp quyền tệp/ảnh.</div>';
 if(entity==='tenants')return `<div class="entity-upload"><label>Ảnh chân dung người thuê (JPG, PNG, WebP, tối đa 3 MB)</label>${record?.photo_path?`<img class="tenant-photo" style="width:70px;height:70px;margin-bottom:10px" src="/api/v2/files/${encodeURIComponent(record.photo_path)}" alt="Ảnh người thuê">`:''}<input type="file" name="tenant_photo" accept="image/png,image/jpeg,image/webp"><div class="id-card-photos"><div><label>CCCD/CMND mặt trước</label>${record?.id_front_path?`<a href="/api/v2/files/${encodeURIComponent(record.id_front_path)}" target="_blank" rel="noopener"><img class="id-photo" src="/api/v2/files/${encodeURIComponent(record.id_front_path)}" alt="CCCD mặt trước"></a>`:''}<input type="file" name="tenant_id_front" accept="image/png,image/jpeg,image/webp"></div><div><label>CCCD/CMND mặt sau</label>${record?.id_back_path?`<a href="/api/v2/files/${encodeURIComponent(record.id_back_path)}" target="_blank" rel="noopener"><img class="id-photo" src="/api/v2/files/${encodeURIComponent(record.id_back_path)}" alt="CCCD mặt sau"></a>`:''}<input type="file" name="tenant_id_back" accept="image/png,image/jpeg,image/webp"></div></div><div class="modal-hint">Ảnh giấy tờ là dữ liệu nhạy cảm: chỉ người được cấp quyền xem khách thuê mới xem được.</div></div>`;
 return `<div class="entity-upload"><label>Ảnh đồng hồ điện</label>${record?.electric_photo?`<a href="/api/v2/files/${encodeURIComponent(record.electric_photo)}" target="_blank" rel="noopener">Xem ảnh điện đã lưu</a>`:''}<input type="file" name="electric_photo_file" accept="image/png,image/jpeg,image/webp"><label style="margin-top:12px">Ảnh đồng hồ nước</label>${record?.water_photo?`<a href="/api/v2/files/${encodeURIComponent(record.water_photo)}" target="_blank" rel="noopener">Xem ảnh nước đã lưu</a>`:''}<input type="file" name="water_photo_file" accept="image/png,image/jpeg,image/webp"></div>`;
}
async function uploadEntityPhotos(entity,id,form){
 const fields=entity==='tenants'?[['tenant_photo','tenant'],['tenant_id_front','tenant_id_front'],['tenant_id_back','tenant_id_back']]:[['electric_photo_file','electric'],['water_photo_file','water']];
 for(const [field,category] of fields){const file=form.elements[field]?.files?.[0];if(!file)continue;
  if(file.size>3*1024*1024)throw Error('Ảnh phải nhỏ hơn hoặc bằng 3 MB. Dữ liệu đã lưu, cần tải lại ảnh.');
  const fd=new FormData();fd.append('category',category);fd.append('related_id',String(id));fd.append('file',file);
  const res=await fetch('/api/v2/files',{method:'POST',credentials:'same-origin',headers:{'X-CSRF-Token':state.csrf},body:fd});
  if(!res.ok){const detail=await res.json().catch(()=>({}));throw Error((detail.detail||'Không tải lên được ảnh')+'; phần dữ liệu đã lưu.');}
 }
}
async function fillPrevious(){const form=$('#entity-form');if(!form||modalContext?.entity!=='readings'||modalContext.id)return;
 const room_id=form.elements.room_id.value,period=form.elements.period.value;
 if(!room_id||!period)return;
 try{const res=await api('readings/previous?'+new URLSearchParams({room_id,period}));
 if($('#entity-form')!==form)return;
 form.elements.electric_old.value=res.electric_new||0;
 form.elements.water_old.value=res.water_new||0;
 if(num(form.elements.electric_new.value)<num(res.electric_new))form.elements.electric_new.value=res.electric_new||0;
 if(num(form.elements.water_new.value)<num(res.water_new))form.elements.water_new.value=res.water_new||0;
 }catch(e){toast(e.message,true);}
}
function openGenerate(){
 modalContext={type:'generate'};
 openModal('Lập hóa đơn tiền trọ',`<form id="generate-form"><div class="modal-hint">Tiền thuê tính cho tháng chọn; điện và nước lấy <b>tháng trước tháng chọn</b> (tháng 01 lấy tháng 12 năm trước). Chỉ số chưa có của tháng trước phải được ghi/duyệt trước; riêng khách mới không bị thu điện nước của người thuê cũ. Hóa đơn đã lập sẽ được bỏ qua.</div><div class="form-grid">
 ${fieldHTML(F('period','Kỳ hóa đơn','month',{required:true}),{period:state.period})}
 ${fieldHTML(F('room_id','Phòng · Người thuê','select',{options:[opt('','Tất cả phòng đang thuê'),...roomOptions(false,true)]}),{room_id:''})}
 ${fieldHTML(F('adjustment','Điều chỉnh mỗi hóa đơn (₫)','number',{full:true}),{adjustment:0})}
 ${fieldHTML(F('note','Ghi chú hóa đơn','textarea',{full:true}),{note:''})}
 </div></form>`,`<button class="btn btn-outline" data-action="close-modal">Hủy</button><button class="btn btn-primary" type="submit" form="generate-form">${ic('receipt')} Phát hành hóa đơn</button>`);
}
function openReissueInvoice(id){
 const x=state.data.invoices.find(v=>v.id===Number(id));if(!x)return;
 modalContext={type:'reissue',id:x.id};
 openModal('Phát hành lại HD-'+x.id,`<form id="invoice-reissue-form"><div class="modal-hint">Hóa đơn <b>${monthVN(x.period)}</b> sẽ lấy lại điện/nước <b>${monthVN(prevMonth(x.period))}</b> và tính lại giá/phí từ cấu hình đang dùng. Giữ số HD và toàn bộ giao dịch đã thu (${amount(x.paid)}). Nếu số đã thu vượt tổng mới, phải chọn xác nhận ghi nhận khoản thu thừa chờ đối soát; không tự hoàn tiền. Kỳ điện nước cũ phải được hủy trước khi sửa chỉ số.</div><div class="form-grid">
 ${fieldHTML(F('adjustment','Điều chỉnh ± (₫)','number'),{adjustment:x.adjustment||0})}
 ${fieldHTML(F('discount','Giảm giá (₫)','number'),{discount:x.discount||0})}
 ${fieldHTML(F('surcharge','Phụ thu (₫)','number'),{surcharge:x.surcharge||0})}
 ${fieldHTML(F('note','Ghi chú','textarea',{full:true}),{note:x.note||''})}
 ${fieldHTML(F('reason','Lý do sửa / phát hành lại','textarea',{required:true,full:true}),{reason:''})}
 </div><label class="field"><input type="checkbox" name="acknowledge_credit" value="true"> Nếu tiền đã thu lớn hơn tổng mới, tôi đồng ý để khoản thừa ở trạng thái <b>chờ đối soát</b>. Không tự động ghi hoàn tiền.</label></form>`,`<button class="btn btn-outline" data-action="close-modal">Hủy</button><button class="btn btn-primary" type="submit" form="invoice-reissue-form">Phát hành lại & ghi nhật ký</button>`);
}
function openVoidInvoice(id){
 const x=state.data.invoices.find(v=>v.id===Number(id));if(!x)return;
 modalContext={type:'void',id:x.id};
 openModal('Hủy HD-'+x.id,`<form id="invoice-void-form"><div class="modal-hint">Hủy hóa đơn là <b>hủy hiệu lực, không xóa chứng từ</b>. Những khoản đã thu (${amount(x.paid)}) vẫn tồn tại để đối soát và chuyển lại khi phát hành lại cùng số HD. Nếu muốn sửa chỉ số của ${monthVN(x.utility_period||x.period)}, hãy hủy trước rồi cập nhật chỉ số.</div>
 ${fieldHTML(F('reason','Lý do hủy (bắt buộc)','textarea',{required:true,full:true}),{reason:''})}
 ${x.paid>0?'<label class="field"><input type="checkbox" name="acknowledge_payments" required> Tôi xác nhận các giao dịch đã thu được giữ nguyên và cần đối soát.</label>':''}
 </form>`,`<button class="btn btn-outline" data-action="close-modal">Đóng</button><button class="btn btn-primary" type="submit" form="invoice-void-form">Hủy hiệu lực hóa đơn</button>`);
}
function prevMonth(period){const [y,m]=period.split('-').map(Number);return m===1?`${y-1}-12`:`${y}-${String(m-1).padStart(2,'0')}`;}
function openPassword(){modalContext={type:'password'};openModal('Đổi mật khẩu',`<form id="password-form"><div class="field"><label>Mật khẩu hiện tại</label><input type="password" name="current_password" autocomplete="current-password" required></div><div class="field"><label>Mật khẩu mới</label><input type="password" name="new_password" minlength="10" maxlength="128" autocomplete="new-password" required></div><p class="meta-note">Sau khi đổi mật khẩu bạn sẽ được đăng xuất khỏi tất cả các thiết bị.</p></form>`,`<button class="btn btn-outline" data-action="close-modal">Hủy</button><button class="btn btn-primary" type="submit" form="password-form">Cập nhật mật khẩu</button>`);}
// Render once for both the on-screen invoice and the browser print view.
// All customer/property fields are escaped because invoice data comes from users.
function renderInvoicePaper(x,bank,invoiceLines=[]){
 const meterValue=v=>Number.isFinite(Number(v))&&v!==null?Number(v).toLocaleString('en-US',{maximumFractionDigits:3}):'—';
 const unitRate=(code,amountKey,usageKey)=>{
   const saved=invoiceLines.find(line=>line.code===code);
   if(saved)return {value:Number(saved.unit_price),estimated:false};
   const usage=Number(x[usageKey]||0);
   return usage>0?{value:Math.round(Number(x[amountKey]||0)/usage),estimated:true}:null;
 };
 const serviceRows=invoiceLines.filter(row=>['service','base_service'].includes(row.code));
 const validServiceRows=serviceRows.length&&Math.round(serviceRows.reduce((n,row)=>n+Number(row.amount||0),0))===Number(x.services||0);
 const consumption=x.utility_period||x.period;
 const rows=[{label:'Tiền thuê phòng '+monthVN(x.period),value:x.rent}];
 for(const [code,caption,amountKey,oldKey,newKey,usageKey,unit] of [
   ['electric','Tiền điện','electricity','electric_old','electric_new','electric_usage','kWh'],
   ['water','Tiền nước','water','water_old','water_new','water_usage','m³']]){
   const rate=unitRate(code,amountKey,usageKey);
   const note=rate?` · ${rate.estimated?'Đơn giá quy đổi':'Đơn giá'}: <strong>${amount(rate.value)}/${unit}</strong>`:'';
   rows.push({label:`${caption} ${monthVN(consumption)}<div class="invoice-meter-detail">Chỉ số cũ: <strong>${meterValue(x[oldKey])}</strong> → Chỉ số mới: <strong>${meterValue(x[newKey])}</strong> · Tiêu thụ: <strong>${meterValue(x[usageKey])} ${unit}</strong>${note}</div>`,value:x[amountKey],safe:true});
 }
 if(validServiceRows){
   for(const item of serviceRows)rows.push({label:`${esc(item.label)}<div class="invoice-meter-detail">${meterValue(item.quantity)} × <strong>${amount(item.unit_price)}</strong></div>`,value:item.amount,safe:true});
 }else rows.push({label:'Phí dịch vụ',value:x.services});
 if(x.adjustment)rows.push({label:'Điều chỉnh',value:x.adjustment});
 const property=esc(x.property_name||'Cơ sở / Tòa nhà');
 const status=invoiceStatus(x);
 return `<article class="invoice-paper">
  <div class="invoice-head">
   <div><div class="eyebrow">PHIẾU THU / HÓA ĐƠN NỘI BỘ</div><h2>HÓA ĐƠN TIỀN PHÒNG</h2><span class="muted">${monthVN(x.period)} · Mã HD-${String(x.id).padStart(5,'0')}</span></div>
   <div class="invoice-head-status">${badge(status)}</div>
  </div>
  ${x.status==='void'?'<div class="modal-hint"><b>HÓA ĐƠN ĐÃ HỦY, KHÔNG CÓ GIÁ TRỊ THU TIỀN.</b> Các khoản thu cũ vẫn được lưu để đối soát.</div>':''}<div class="invoice-info"><div class="invoice-property"><strong>${property}</strong>${x.property_address?`<div>${esc(x.property_address)}</div>`:''}</div>
   <div class="invoice-tenant-highlight" aria-label="Thông tin khách thuê">
    <span>Khách thuê: <strong>${esc(x.tenant_name||'—')}</strong></span>
    <span class="invoice-tenant-divider" aria-hidden="true">·</span>
    <span>Phòng: <strong>${esc(x.room_code||'—')}</strong></span>
    <span class="invoice-tenant-divider" aria-hidden="true">·</span>
    <span>Số điện thoại: <strong>${esc(x.tenant_phone||'—')}</strong></span>
   </div>
  </div>
  <table class="invoice-table"><tbody>${rows.map(r=>`<tr><td>${r.safe?r.label:esc(r.label)}</td><td>${amount(r.value)}</td></tr>`).join('')}</tbody></table>
  <div class="invoice-total"><span>TỔNG CỘNG</span><span>${amount(x.total)}</span></div>
  <div class="invoice-sum invoice-sum-paid"><span>Đã thanh toán</span><strong class="positive">${amount(x.paid)}</strong></div>
  ${x.unapplied_credit>0?`<div class="invoice-sum"><span>Thu thừa cần đối soát</span><strong class="negative">${amount(x.unapplied_credit)}</strong></div>`:''}<div class="invoice-sum invoice-sum-balance"><span>Tổng tiền phải thanh toán</span><strong class="${x.balance?'negative':''}">${amount(x.balance)}</strong></div>
  ${bank?.configured?`<section class="invoice-bank" aria-label="Thông tin chuyển khoản">
    <div class="invoice-bank-qr"><img loading="eager" src="${esc(bank.qr_url)}" alt="Mã QR chuyển khoản ngân hàng"></div>
    <div class="invoice-bank-info"><strong>THANH TOÁN CHUYỂN KHOẢN</strong>
      <div>Ngân hàng: <b>${esc(bank.bank_name)}</b></div><div>Chủ tài khoản: <b>${esc(bank.holder)}</b></div>
      <div>Số tài khoản: <b>${esc(bank.account_number)}</b></div>
      <div>Số tiền: <b>${amount(bank.amount)}</b></div><div>Nội dung CK: <b>${esc(bank.content)}</b></div>
      <small>Chỉ chuyển khoản khi đã kiểm tra lại tên người thụ hưởng.</small>
    </div></section>`:''}
  ${x.note?`<p class="invoice-note">Ghi chú: ${esc(x.note)}</p>`:''}
  <p class="invoice-disclaimer">Hóa đơn quản lý nội bộ; không thay thế hóa đơn điện tử theo quy định pháp luật.</p>
  <footer class="invoice-print-footer" aria-label="Cơ sở / Tòa nhà">${property}</footer>
 </article>`;
}
async function openInvoice(id){const x=state.data.invoices.find(v=>v.id===num(id));if(!x)return;
 let bank=null,lines=[];
 // Snapshot from invoice_lines avoids replacing historical prices by current facility rates.
 try{[bank,lines]=await Promise.all([api('v6/invoices/'+x.id+'/payment-qr'),api('v2/invoices/'+x.id+'/lines')]);}
 catch(err){console.warn('Invoice detail fallback:',err.message);
   try{bank=await api('v6/invoices/'+x.id+'/payment-qr')}catch(e){}
   try{lines=await api('v2/invoices/'+x.id+'/lines')}catch(e){}
 }
 const detail=renderInvoicePaper(x,x.status==='void'?null:bank,Array.isArray(lines)?lines:[]);
 modalContext={type:'invoice',id};$('#print-root').innerHTML=detail;
 openModal('Chi tiết hóa đơn',detail,`<button class="btn btn-outline" data-action="close-modal">Đóng</button>${x.status==='void'?'':`<button class="btn btn-outline" data-action="print">${ic('print')} In hóa đơn</button><button class="btn btn-outline" data-action="download-invoice-png">${ic('download')} Lưu ảnh PNG</button>`}${x.status==='published'&&x.balance>0?`<button class="btn btn-primary" data-pay="${x.id}">${ic('wallet')} Thu tiền</button>`:''}`,true);
}
async function downloadInvoicePNG(id){
 if(busy)return;busy=true;
 try{
  const response=await fetch(`/api/v6/invoices/${encodeURIComponent(id)}/image.png`,{credentials:'same-origin',cache:'no-store'});
  if(!response.ok){const detail=await response.json().catch(()=>({}));throw Error(detail.detail||'Không tải được ảnh hóa đơn.');}
  const blob=await response.blob();if(!blob.type.startsWith('image/png'))throw Error('Máy chủ trả về dữ liệu ảnh không hợp lệ.');
  const url=URL.createObjectURL(blob);
  try{const link=document.createElement('a');link.href=url;link.download=`Hoa-don-HD${String(id).padStart(5,'0')}.png`;document.body.appendChild(link);link.click();link.remove();}
  finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
  toast('Đã tải ảnh hóa đơn PNG.');
 }catch(err){toast(err.message,true);}finally{busy=false;}
}
function openConfirm(title,body,cb){confirmAction=cb;modalContext={type:'confirm'};
 openModal(title,`<div class="confirm-copy">${esc(body)}</div>`,`<button class="btn btn-outline" data-action="close-modal">Hủy</button><button class="btn btn-danger" data-action="confirm">${ic('check')} Xác nhận</button>`);
}
async function apiMultipart(path,method,formdata){
 const r=await fetch('/api/'+path,{method,credentials:'same-origin',headers:{'x-csrf-token':state.csrf||''},body:formdata});
 const j=await r.json().catch(()=>({}));if(!r.ok)throw Error(j.detail||'Không thể tải ảnh/lưu yêu cầu.');return j;
}
async function showTicketPhotos(id){
 try{const photos=await api('v8/tickets/'+id+'/photos');
 const grid=photos.length?photos.map(photo=>`<div class="ticket-photo-item"><a href="${esc(photo.url)}" target="_blank" rel="noopener"><img src="${esc(photo.url)}" loading="lazy" alt="Ảnh sự cố"></a>${can('tickets.edit')?`<button class="btn btn-outline" data-remove-ticket-photo="${photo.id}" data-ticket="${id}">Xóa ảnh</button>`:''}</div>`).join(''):'<p>Chưa có ảnh.</p>';
 modalContext={type:'ticketphotos'};
 openModal('Ảnh yêu cầu sửa chữa',`<div class="ticket-photo-preview">${grid}</div>`,`<button class="btn btn-primary" data-action="close-modal">Đóng</button>`);
 }catch(e){toast(e.message,true);}
}
async function submitEntity(form){if(busy)return;busy=true;
 const ctx=modalContext;if(!ctx||ctx.type!=='entity')return;
 const payload={...ctx.values,...Object.fromEntries(new FormData(form).entries())};
 for(const field of ['tenant_photo','tenant_id_front','tenant_id_back','electric_photo_file','water_photo_file'])delete payload[field];
 if(ctx.entity==='tickets'){
    try{const fd=new FormData(form);const imgs=fd.getAll('photos').filter(f=>f&&f.name);if(imgs.length>5)throw Error('Chỉ được chọn tối đa 5 ảnh.');
      if(imgs.some(f=>f.size>3*1024*1024))throw Error('Mỗi ảnh không được quá 3 MB.');
      const result=await apiMultipart('v8/tickets'+(ctx.id?'/'+ctx.id:''),ctx.id?'PUT':'POST',fd);
      closeModal();await refresh();toast('Đã lưu yêu cầu sửa chữa ('+(result.photos_added??result.photos??0)+' ảnh mới).');
    }catch(ex){toast(ex.message,true);}finally{busy=false;}return;
 }
 if(ctx.entity==='readings'&&!activeTenantFor(Number(payload.room_id),payload.period)){toast('Phòng chưa có người thuê trong kỳ ghi chỉ số.',true);busy=false;return;}
 if(ctx.entity==='tenants'&&state.user?.role==='admin'){payload.portal_enabled=Boolean(form.elements.portal_enabled?.checked);payload.portal_property_id=Number(form.elements.portal_property_id?.value||0);}
 if(ctx.entity==='rooms'&&ctx.id&&ctx.values.status==='occupied')payload.condition='ready';
 // Editing a contract does not accept room/tenant reassignment.
 if(ctx.entity==='contracts'&&ctx.id){delete payload.room_id;delete payload.tenant_id;}
 try{const result=await api(ctx.entity+(ctx.id?'/'+ctx.id:''),ctx.id?'PUT':'POST',payload);
 let uploadError='';
 if(ctx.entity==='readings'||ctx.entity==='tenants'){
   try{await uploadEntityPhotos(ctx.entity,result.id||ctx.id,form);}catch(e){uploadError=e.message;}
 }
 closeModal();await refresh();toast(uploadError?'Dữ liệu đã lưu nhưng ảnh chưa tải lên: '+uploadError:'Đã lưu dữ liệu thành công.',Boolean(uploadError));if(result.portal_credentials)showPortalCredentials(result.portal_credentials);}
 catch(e){toast(e.message,true);}finally{busy=false;}
}
async function submitGenerate(form){if(busy)return;busy=true;const payload=Object.fromEntries(new FormData(form));
 try{const result=await api('invoices/generate','POST',payload);closeModal();state.period=payload.period;await refresh();toast(result.created?`Đã phát hành ${result.created} hóa đơn.`:'Các hóa đơn trong phạm vi đã được lập trước đó.');}
 catch(e){toast(e.message,true);}finally{busy=false;}
}
async function submitPassword(form){if(busy)return;busy=true;try{await api('auth/change-password','POST',Object.fromEntries(new FormData(form)));closeModal();toast('Đã đổi mật khẩu. Hãy đăng nhập lại.');renderAuth(false);}catch(e){toast(e.message,true);}finally{busy=false;}}
async function deleteEntity(entity,id){try{await api(`${entity}/${id}`,'DELETE');closeModal();await refresh();toast('Đã xóa bản ghi.');}catch(e){toast(e.message,true);}}
async function endContract(id){try{await api(`contracts/${id}/end`,'POST',{});closeModal();await refresh();toast('Hợp đồng đã kết thúc, phòng trở lại trạng thái trống.');}catch(e){toast(e.message,true);}}
async function logout(){try{await api('auth/logout','POST',{});}catch(e){}state.data={};renderAuth(false);}

// Event delegation keeps dynamically rendered pages and modal forms interactive.
document.addEventListener('click',async e=>{
 const target=e.target.closest('button, a[data-nav]');
 if(e.target.id==='modal-backdrop'&&!e.target.closest('.modal')){closeModal();return;}
 if(!target)return;
 if(target.dataset.utility){
 const action=target.dataset.utility,id=target.dataset.id;
 if(action==='ha-config'&&state.user?.role==='admin')await openHaConfig();
 if(action==='ha-meter'&&state.user?.role==='admin')await openHaMeter(id);
 if(action==='ha-sync'&&state.user?.role==='admin')await haSyncMeter(id);
 if(action==='ha-test'&&state.user?.role==='admin')await haTestOrPreview(action);
 if(action==='ha-preview'&&state.user?.role==='admin')await haTestOrPreview(action,id);
 if(action==='add-meter'&&can('utilitymeters.create'))openUtilityForm('meter');
 if(action==='edit-meter'&&can('utilitymeters.edit'))openUtilityForm('meter',id);
 if(action==='add-bill'&&can('utilitymeters.record'))openUtilityForm('bill');
 if(action==='edit-bill'&&can('utilitymeters.record'))openUtilityForm('bill',id);
 if(action==='delete-meter'&&can('utilitymeters.delete'))openConfirm('Xóa công tơ','Chỉ xóa được công tơ chưa có dữ liệu kỳ ghi.',async()=>{try{await api('utility-meters/'+id,'DELETE');closeModal();await loadUtilityData();renderPage();toast('Đã xóa công tơ.');}catch(e){toast(e.message,true);}});
 if(action==='delete-bill'&&can('utilitymeters.deletebill'))openConfirm('Xóa kỳ nhà cung cấp','Chỉ xóa được kỳ chưa ghi nhận thanh toán; thao tác này được lưu nhật ký.',async()=>{try{await api('utility-bills/'+id,'DELETE');closeModal();await loadUtilityData();renderPage();toast('Đã xóa kỳ.');}catch(e){toast(e.message,true);}});
 return;
 }
 if(target.dataset.invoiceReissue){openReissueInvoice(target.dataset.invoiceReissue);return;}
 if(target.dataset.invoiceVoid){openVoidInvoice(target.dataset.invoiceVoid);return;}
 if(target.dataset.nav){e.preventDefault();await navigate(target.dataset.nav);return;}
 if(target.dataset.add){e.preventDefault();if(!can(target.dataset.add+'.'+(target.dataset.add==='readings'||target.dataset.add==='payments'?'record':'create')))return;openForm(target.dataset.add);return;}
 if(target.dataset.edit){if(!can(target.dataset.edit+'.'+('edit')))return;openForm(target.dataset.edit,target.dataset.id);return;}
 if(target.dataset.view){if(target.dataset.view==='invoices')openInvoice(target.dataset.id);return;}
 if(target.dataset.pay){if(!can('payments.record'))return;openForm('payments',null,{invoice_id:num(target.dataset.pay)});return;}
 if(target.dataset.delete){const entity=target.dataset.delete,id=target.dataset.id;const titles={properties:'cơ sở',rooms:'phòng',tenants:'khách thuê',invoices:'hóa đơn',payments:'giao dịch thanh toán',expenses:'khoản chi',tickets:'yêu cầu sửa chữa'};
 openConfirm('Xóa dữ liệu',`Bạn chắc chắn muốn xóa ${titles[entity]||'bản ghi'} #${id}? Thao tác này không thể hoàn tác và sẽ bị từ chối nếu dữ liệu còn liên kết.`,()=>deleteEntity(entity,id));return;}
 if(target.dataset.end){if(!can('contracts.end'))return;const id=target.dataset.end;openConfirm('Kết thúc hợp đồng','Kết thúc hợp đồng sẽ trả phòng về trạng thái trống. Hóa đơn và lịch sử thanh toán vẫn được lưu lại. Hãy xác nhận khi khách đã bàn giao phòng.',()=>endContract(id));return;}
 if(target.dataset.ticketPhotos){await showTicketPhotos(Number(target.dataset.ticketPhotos));return;}
 if(target.dataset.removeTicketPhoto){const tid=Number(target.dataset.ticket),pid=Number(target.dataset.removeTicketPhoto);if(confirm('Xóa ảnh đã chọn?')){try{await api('v8/tickets/'+tid+'/photos/'+pid,'DELETE');await showTicketPhotos(tid);}catch(ex){toast(ex.message,true);}}return;}
 if(target.dataset.portalReset){try{const res=await api('tenant/admin/accounts/'+target.dataset.portalReset+'/reset','POST',{});showPortalCredentials(res);}catch(ex){toast(ex.message,true);}return;}
 if(target.dataset.meterReview){const id=Number(target.dataset.meterReview),decision=target.dataset.decision;
  openConfirm(decision==='approve'?'Duyệt chỉ số':'Từ chối chỉ số',decision==='approve'?'Xác nhận chuyển số khách thuê gửi thành chỉ số chính thức?':'Xác nhận từ chối đề nghị ghi chỉ số này?',async()=>{try{await api('tenant/admin/submissions/'+id+'/review','POST',{decision,feedback:decision==='reject'?'Chỉ số hoặc ảnh cần kiểm tra lại.':''});closeModal();await loadTenantApprovals();renderPage();toast('Đã xử lý đề nghị.');}catch(err){toast(err.message,true);}});return;}
 if(target.dataset.action){const a=target.dataset.action;
 if(a==='owner-settings'){await openOwnerSettings();return;}
 if(a==='close-modal'){closeModal();return;}
 if(a==='generate'){if(can('invoices.publish'))openGenerate();return;}
 if(a==='password'){openPassword();return;}
 if(a==='refresh'){await refresh();toast('Dữ liệu đã được cập nhật.');return;}
 if(a==='logout'){await logout();return;}
 if(a==='reload'){window.location.reload();return;}
 if(a==='menu'){state.sidebar=!state.sidebar;$('#sidebar')?.classList.toggle('open',state.sidebar);$('#side-overlay')?.classList.toggle('show',state.sidebar);return;}
 if(a==='confirm'){const task=confirmAction;if(task)await task();return;}
 if(a==='print'){window.print();return;}
 if(a==='download-invoice-png'){if(modalContext?.type==='invoice')await downloadInvoicePNG(modalContext.id);return;}
 }
 if(e.target.id==='side-overlay')closeMenu();
});
document.addEventListener('click',e=>{if(e.target?.id==='side-overlay')closeMenu();});
document.addEventListener('submit',async e=>{
 if(e.target.id==='owner-form'){e.preventDefault();saveOwner(e.target);return;}
 if(e.target.id==='utility-form'){e.preventDefault();saveUtility(e.target);return;}
 if(['ha-config-form','ha-meter-form'].includes(e.target.id)){e.preventDefault();saveHaForm(e.target);return;}
 if(['invoice-reissue-form','invoice-void-form'].includes(e.target.id)){
  e.preventDefault();const c=modalContext;if(!c)return;const d=Object.fromEntries(new FormData(e.target));
  if(c.type==='void')d.acknowledge_payments=e.target.elements.acknowledge_payments?.checked||false;
  else d.acknowledge_credit=e.target.elements.acknowledge_credit?.checked||false;
  try{await api('v10/invoices/'+c.id+'/'+(c.type==='void'?'void':'reissue'),'POST',d);closeModal();await refresh();toast(c.type==='void'?'Đã hủy hiệu lực hóa đơn, lưu nguyên lịch sử thu.':'Đã phát hành lại, giữ nguyên thanh toán.');}catch(err){toast(err.message,true);}return;
 }
 if(['entity-form','generate-form','password-form'].includes(e.target.id)){
 e.preventDefault();if(e.target.id==='entity-form')submitEntity(e.target);
 else if(e.target.id==='generate-form')submitGenerate(e.target);
 else submitPassword(e.target);
 }
});
document.addEventListener('change',async e=>{
 if(e.target.id==='ticket-photos-input'){
   const files=[...e.target.files], el=document.getElementById('ticket-photo-preview');
   if(files.length>5 || files.some(f=>f.size>3*1024*1024)){toast('Tối đa 5 ảnh, mỗi ảnh không quá 3 MB.',true);e.target.value='';if(el)el.innerHTML='';return;}
   if(el){el.innerHTML=files.map((f,i)=>`<div class="ticket-photo-item"><img alt="Ảnh đính kèm ${i+1}" src="${URL.createObjectURL(f)}"><small>${esc(f.name)}</small></div>`).join('');}
   return;
 }

 if(e.target.id==='owner-property'){state.ownerProperty=e.target.value;await openOwnerSettings();return;}
 const control=e.target.dataset.control;
 if(control==='property'){state.propertyFilter=e.target.value;renderPage();return;}
 if(control==='utilityYear'){state.utilityYear=Number(e.target.value);await loadUtilityData();renderPage();return;}
 if(control==='roomMode'){state.roomMode=e.target.value;renderPage();return;}
 if(control==='readingsYear'){state.readingsYear=Number(e.target.value);renderPage();return;}
 if(control==='invoicesYear'){state.invoicesYear=Number(e.target.value);renderPage();return;}
 if(control==='period'){state.period=e.target.value||thisMonth();if(state.view==='reports')await loadReport();renderPage();return;}
 if(control==='reportProperty'){state.reportProperty=e.target.value;await loadReport();renderPage();return;}
 if(e.target.closest('#entity-form')&&modalContext?.type==='entity'){
 if(modalContext.entity==='readings'&&['room_id','period'].includes(e.target.name)){if(e.target.name==='period')updateReadingRooms(e.target.form);else syncMeterTenant(e.target.form);if(activeTenantFor(Number(e.target.form.elements.room_id.value),e.target.form.elements.period.value))await fillPrevious();}
 if(modalContext.entity==='contracts'&&e.target.name==='room_id'){
  const r=state.data.rooms.find(x=>String(x.id)===e.target.value),form=e.target.form;
  if(r){form.elements.monthly_rent.value=r.rent;form.elements.deposit.value=r.deposit;}
 }
 if(modalContext.entity==='payments'&&e.target.name==='invoice_id'){
  const r=state.data.invoices.find(x=>String(x.id)===e.target.value);if(r)e.target.form.elements.amount.value=r.balance;
 }
 }
});
document.addEventListener('input',e=>{if(e.target.id==='global-search'){state.search=e.target.value.trim();renderPage();}
 if(e.target.closest('#utility-form')&&['reading_new','reading_old','billed_usage'].includes(e.target.name)){
  const f=e.target.form,u=f.elements.billed_usage;
  if(e.target.name==='billed_usage')u.dataset.manual='1';
  else if(!u.dataset.manual)u.value=Math.max(0,Number(f.elements.reading_new.value||0)-Number(f.elements.reading_old.value||0)).toFixed(3).replace(/\.?0+$/,'');
 }});
document.addEventListener('keydown',e=>{
 if(e.key==='Escape'){if($('#modal-backdrop'))closeModal();else closeMenu();}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('#global-search')?.focus();}
});
// Công tơ tổng: tách riêng chỉ số tính cho khách thuê và hóa đơn nhà cung cấp.
async function loadUtilityData(){
 if(!can('utilitymeters.view'))return;
 const [meters,bills,report]=await Promise.all([
  api('utility-meters'),api('utility-bills'),
  can('utilitymeters.report')?api('utility-report?year='+state.utilityYear):Promise.resolve({items:[],totals:{},method:''})
 ]);
 state.data.utilitymeters=meters;
 state.data.utilitybills=bills;
 state.data.utilityreport=report;
 if(state.user?.role==='admin'){try{state.data.hamappings=await api('ha/mappings')}catch(e){state.data.hamappings=[];}}
}
function pageUtilityMeters(){
 const meters=filter(state.data.utilitymeters||[],['property_name','meter_number','customer_code','label','supplier','kind']);
 const bills=filter((state.data.utilitybills||[]).filter(b=>b.period.startsWith(String(state.utilityYear)+'-')),['property_name','period','meter_number','customer_code','kind']);
 const haByMeter=Object.fromEntries((state.data.hamappings||[]).map(x=>[x.meter_id,x]));
 const report=state.data.utilityreport||{items:[],totals:{}};
 const entries=(report.items||[]).filter(x=>!state.propertyFilter||String(x.property_id)===String(state.propertyFilter));
 const sums={};for(const key of ['customer_billed','customer_collected_est','supplier_charged','supplier_paid','accrual_margin','cash_difference_est','electric_usage','water_usage'])sums[key]=entries.reduce((v,x)=>v+Number(x[key]||0),0);
 const years=[...new Set([state.utilityYear,Number(today().slice(0,4)),...(state.data.utilitybills||[]).map(x=>Number(x.period.slice(0,4))),...(state.data.invoices||[]).map(x=>Number(x.period.slice(0,4))),...(report.items||[]).map(x=>Number(x.period.slice(0,4)))])].sort((a,b)=>b-a);
 const filters=propFilter()+`<select data-control="utilityYear" aria-label="Năm đối soát công tơ">${years.map(y=>`<option value="${y}" ${y===state.utilityYear?'selected':''}>Cả năm ${y}</option>`).join('')}</select>`;
 return heading('Công tơ điện nước tổng','Theo dõi nhiều công tơ theo cơ sở, mã khách hàng nhà cung cấp và đối soát thu - chi.',
 `${state.user?.role==='admin'?`<button class="btn btn-outline" data-utility="ha-config">⚡ Kết nối Home Assistant</button>`:''}${can('utilitymeters.create')?`<button class="btn btn-outline" data-utility="add-meter">${ic('plus')} Thêm công tơ</button>`:''}${can('utilitymeters.record')?`<button class="btn btn-primary" data-utility="add-bill">${ic('plus')} Ghi kỳ nhà cung cấp</button>`:''}`)+
 `<div class="info-banner">Công tơ tổng và thống kê lấy theo tháng TIÊU THỤ. Hóa đơn tiền phòng tháng 10 sử dụng điện/nước tháng 9, không được đặt kỳ tháng 10 cho hóa đơn EVN tháng 9 chỉ vì đã thanh toán tháng 10.</div>`+
 `<div class="card" style="margin-bottom:18px">${toolbar(filters,'',meters.length)}</div>`+
 `<div class="metrics-grid utility-metrics">
 ${metric('ĐÃ TÍNH CHO KHÁCH',compact(sums.customer_billed)+' ₫','receipt','Tiền điện + nước trong hóa đơn đã chốt')}
 ${metric('NHÀ CUNG CẤP TÍNH',compact(sums.supplier_charged)+' ₫','expense','Tổng tiền điện nước nhà cung cấp')}
 ${metric('CHÊNH LỆCH DỒN TÍCH',compact(sums.accrual_margin)+' ₫','wallet','Đã tính khách − nhà cung cấp tính')}
 ${metric('TIỀN ĐÃ THU ƯỚC TÍNH',compact(sums.customer_collected_est)+' ₫','meter','Khoản điện nước phân bổ từ thanh toán')}
 </div>`+
 `<div class="card" style="margin-bottom:20px"><div class="toolbar"><strong>Danh sách công tơ của cơ sở</strong><span class="count">${meters.length} công tơ</span></div>`+
 table(['CƠ SỞ / CÔNG TƠ','LOẠI','MÃ KHÁCH HÀNG','NHÀ CUNG CẤP','TRẠNG THÁI',''],meters.map(m=>`<tr><td><strong>${esc(m.property_name)}</strong><div class="cell-sub">${esc(m.label||m.meter_number)} · Số: ${esc(m.meter_number)}</div>${haByMeter[m.id]?`<div class="cell-sub" style="color:${haByMeter[m.id].last_error?'#b54747':'#0b998e'}">HA ${haByMeter[m.id].auto_sync?'· Tự động':'· Thủ công'}${haByMeter[m.id].last_period?' · Kỳ '+esc(haByMeter[m.id].last_period):''}${haByMeter[m.id].last_error?' · Lỗi: '+esc(haByMeter[m.id].last_error):''}</div>`:''}</td><td>${m.kind==='electric'?'⚡ Điện':'💧 Nước'}</td><td><strong>${esc(m.customer_code)}</strong></td><td>${esc(m.supplier||'—')}</td><td>${m.active?badge('active'):badge('inactive')}</td><td><div class="table-actions">${state.user?.role==='admin'&&m.kind==='electric'?`<button data-utility="ha-meter" data-id="${m.id}" title="Cấu hình Home Assistant">HA</button><button data-utility="ha-sync" data-id="${m.id}" title="Đồng bộ Home Assistant">${ic('refresh')}</button>`:''}${can('utilitymeters.edit')?`<button data-utility="edit-meter" data-id="${m.id}" title="Sửa công tơ">${ic('edit')}</button>`:''}${can('utilitymeters.delete')&&!m.bill_count?`<button class="delete" data-utility="delete-meter" data-id="${m.id}" title="Xóa công tơ chưa có lịch sử">${ic('trash')}</button>`:''}</div></td></tr>`),meters.length,'Chưa có công tơ','Tạo công tơ điện/nước theo từng cơ sở hoặc tòa nhà.')+'</div>'+
 `<div class="card" style="margin-bottom:20px"><div class="toolbar"><strong>Sản lượng và hóa đơn nhà cung cấp — ${state.utilityYear}</strong><span class="count">${bills.length} kỳ</span></div>`+
 table(['KỲ TIÊU THỤ / CƠ SỞ','CÔNG TƠ','CHỈ SỐ ĐẦU → CUỐI','SẢN LƯỢNG TÍNH TIỀN','PHẢI TRẢ','ĐÃ TRẢ',''],bills.map(b=>`<tr><td><strong>${monthVN(b.period)}</strong><div class="cell-sub">${esc(b.property_name)}</div></td><td>${esc(b.kind==='electric'?'Điện':'Nước')} · ${esc(b.meter_number)}<div class="cell-sub">Mã KH: ${esc(b.customer_code)}</div></td><td>${Number(b.reading_old).toLocaleString('en-US')} → ${Number(b.reading_new).toLocaleString('en-US')}</td><td>${Number(b.billed_usage).toLocaleString('en-US')} ${b.kind==='electric'?'kWh':'m³'}</td><td>${amount(b.bill_amount)}${b.origin==='home_assistant'?'<div class="cell-sub">HA · tạm tính</div>':''}</td><td>${amount(b.paid_amount)}</td><td><div class="table-actions">${can('utilitymeters.record')?`<button data-utility="edit-bill" data-id="${b.id}" title="Chỉnh sửa kỳ">${ic('edit')}</button>`:''}${can('utilitymeters.deletebill')&&!b.paid_amount?`<button class="delete" data-utility="delete-bill" data-id="${b.id}" title="Xóa kỳ">${ic('trash')}</button>`:''}</div></td></tr>`),bills.length,'Chưa có kỳ công tơ','Kỳ thể hiện tháng đã tiêu thụ, không phải tháng thanh toán.')+'</div>'+
 (can('utilitymeters.report')?`<div class="card"><div class="toolbar"><strong>Thống kê chênh lệch điện nước ${state.utilityYear}</strong><span class="count">${entries.length} kỳ/cơ sở</span></div>`+
 table(['KỲ TIÊU THỤ / CƠ SỞ','KHÁCH ĐƯỢC TÍNH','NHÀ CUNG CẤP TÍNH','LÃI/LỖ DỒN TÍCH','ƯỚC TÍNH ĐÃ THU','THỰC TRẢ','CHÊNH LỆCH TIỀN'],entries.map(x=>`<tr><td><strong>${monthVN(x.period)}</strong><div class="cell-sub">${esc(x.property_name)}</div>${x.missing_electric_bill||x.missing_water_bill?`<div class="cell-sub negative">Thiếu kỳ ${x.missing_electric_bill?'điện ':''}${x.missing_water_bill?'nước':''}</div>`:''}</td><td>${amount(x.customer_billed)}<div class="cell-sub">Điện ${amount(x.electric_billed)} · Nước ${amount(x.water_billed)}</div></td><td>${amount(x.supplier_charged)}<div class="cell-sub">Điện ${amount(x.electric_charged)} · Nước ${amount(x.water_charged)}</div></td><td class="${x.accrual_margin<0?'negative':'positive'}">${amount(x.accrual_margin)}</td><td>${amount(x.customer_collected_est)}</td><td>${amount(x.supplier_paid)}</td><td class="${x.cash_difference_est<0?'negative':'positive'}">${amount(x.cash_difference_est)}</td></tr>`),entries.length,'Chưa có số liệu đối soát','So sánh điện nước trên hóa đơn khách tháng sau với công tơ tổng của tháng tiêu thụ này.')+
 `<div class="modal-hint utility-disclaimer">${esc(report.method||'')}</div><div class="modal-hint utility-disclaimer">Không nhập lặp số tiền hóa đơn nhà cung cấp vào Chi phí vận hành nếu đã dùng báo cáo này để đối soát, tránh cộng trùng khi tổng hợp thủ công.</div></div>`:'') ;
}
function openUtilityForm(kind,ident){
 const meter=kind==='meter';const record=ident?(state.data[meter?'utilitymeters':'utilitybills']||[]).find(x=>x.id===Number(ident)):null;
 const fields=meter?[F('property_id','Cơ sở / tòa nhà','select',{required:true,options:propertyOptions()}),F('kind','Loại công tơ','select',{required:true,options:choices({electric:'Điện',water:'Nước'})}),F('meter_number','Số công tơ điện/nước','text',{required:true}),F('customer_code','Mã khách hàng nhà cung cấp','text',{required:true}),F('supplier','Nhà cung cấp','text',{placeholder:'Ví dụ: EVN / Công ty cấp nước'}),F('label','Tên mô tả công tơ','text',{placeholder:'Ví dụ: Công tơ điện tổng tầng 1'}),F('active','Trạng thái','select',{options:[opt(1,'Đang sử dụng'),opt(0,'Ngừng sử dụng')]}),F('notes','Ghi chú','textarea',{full:true})]
 :[F('meter_id','Công tơ tổng','select',{required:true,options:(state.data.utilitymeters||[]).map(m=>opt(m.id,`${m.property_name} · ${m.kind==='electric'?'Điện':'Nước'} · ${m.meter_number} · KH: ${m.customer_code}`))}),F('period','Tháng tiêu thụ thực tế (không phải tháng thu)','month',{required:true}),F('reading_old','Chỉ số đầu kỳ','number',{step:0.001,min:0}),F('reading_new','Chỉ số cuối kỳ','number',{step:0.001,min:0}),F('billed_usage','Sản lượng nhà cung cấp tính tiền','number',{step:0.001,min:0}),F('bill_amount','Số tiền nhà cung cấp tính (₫)','number',{required:true,min:0}),F('paid_amount','Đã trả nhà cung cấp (₫)','number',{min:0}),F('paid_on','Ngày thanh toán','date'),F('note','Ghi chú / kỳ hóa đơn','textarea',{full:true})];
 const values=record|| (meter?{active:1,kind:'electric',property_id:state.propertyFilter||state.data.properties?.[0]?.id}:{period:(()=>{const d=new Date(today()+'T12:00:00');d.setMonth(d.getMonth()-1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`})(),meter_id:state.data.utilitymeters?.[0]?.id,reading_old:0,reading_new:0,billed_usage:0,bill_amount:0,paid_amount:0});
 if(!meter&&!record&&!state.data.utilitymeters?.length){toast('Cần tạo công tơ trước khi ghi kỳ thanh toán.',true);return;}
 modalContext={type:'utility',kind,ident,values};
 openModal((ident?'Chỉnh sửa ':'Thêm ')+(meter?'công tơ':'kỳ công tơ'),`<form id="utility-form"><div class="form-grid">${fields.map(f=>fieldHTML(f,values)).join('')}</div><div class="modal-hint">${meter?'Mỗi công tơ được gắn đúng một cơ sở; cùng một cơ sở có thể có nhiều công tơ điện và nước.':'Ghi đúng THÁNG TIÊU THỤ: ví dụ EVN thu tiền tháng 10 cho điện tháng 9 thì chọn kỳ 09/2026, ngày thanh toán 10/2026. Bản ghi cũ sai kỳ cần tự sửa; không tự động dời dữ liệu đã chốt.'}</div></form>`,
 `<button class="btn btn-outline" data-action="close-modal">Hủy</button><button class="btn btn-primary" type="submit" form="utility-form">${ic('check')} ${ident?'Lưu thay đổi':'Tạo mới'}</button>`);
}
async function saveUtility(form){if(busy)return;busy=true;const ctx=modalContext;
 try{const meter=ctx.kind==='meter',endpoint=meter?'utility-meters':'utility-bills';const payload=Object.fromEntries(new FormData(form).entries());
 await api(endpoint+(ctx.ident?'/'+ctx.ident:''),ctx.ident?'PUT':'POST',payload);
 closeModal();await loadUtilityData();renderPage();toast('Đã lưu thành công.');
 }catch(e){toast(e.message,true);}finally{busy=false;}
}


// Home Assistant integration for electricity supplier master meters.
async function openHaConfig(){
 if(state.user?.role!=='admin')return;
 try{
  const cfg=await api('ha/config');
  modalContext={type:'ha-config'};
  openModal('Kết nối Home Assistant',`<form id="ha-config-form"><div class="form-grid">
   ${fieldHTML(F('url','Địa chỉ Home Assistant','url',{required:true,full:true,placeholder:'http://192.168.31.100:8123'}),cfg)}
   ${fieldHTML(F('token','Long-Lived Access Token (bỏ trống để giữ token cũ)','password',{full:true}),{})}
   </div><div class="modal-hint">Token được mã hóa bằng khóa integration.key trên Ubuntu. Bạn tạo token trong Home Assistant → Hồ sơ người dùng → Long-Lived Access Tokens. Máy chủ TroFlow phải truy cập được Home Assistant qua mạng nội bộ. ${cfg.configured?'Đã lưu token trước đó.':'Chưa có token.'}</div>
   <div id="ha-connect-result" role="status"></div></form>`,
   `<button type="button" class="btn btn-outline" data-utility="ha-test">Kiểm tra kết nối</button>
    <button type="submit" form="ha-config-form" class="btn btn-primary">Lưu cấu hình</button>`);
 }catch(err){toast(err.message,true);}
}
async function openHaMeter(id){
 if(state.user?.role!=='admin')return;
 const meter=(state.data.utilitymeters||[]).find(m=>m.id===Number(id));
 if(!meter || meter.kind!=='electric')return;
 const current=(state.data.hamappings||[]).find(m=>m.meter_id===meter.id)||{};
 const values={period_offset:0,enabled:1,auto_sync:0,...current};
 modalContext={type:'ha-meter',id:meter.id};
 const fields=[
  F('old_entity','Chỉ số đầu kỳ / cuối kỳ trước (kWh)','text',{required:true,full:true,placeholder:'sensor.chi_so_cuoi_ky_truoc'}),
  F('new_entity','Chỉ số cuối kỳ / tạm chốt (kWh)','text',{required:true,full:true,placeholder:'sensor.chi_so_tam_chot'}),
  F('usage_entity','Sản lượng tháng (kWh)','text',{required:true,full:true,placeholder:'sensor.tieu_thu_ky_nay'}),
  F('amount_entity','Tiền điện tháng (VND)','text',{required:true,full:true,placeholder:'sensor.tien_dien_ky_nay'}),
  F('period_offset','Gán dữ liệu vào kỳ','select',{full:true,options:[opt(0,'Tháng hiện tại'),opt(-1,'Tháng trước')]}),
  F('enabled','Trạng thái kết nối công tơ','select',{options:[opt(1,'Bật'),opt(0,'Tắt')]}),
  F('auto_sync','Tự đồng bộ mỗi giờ','select',{options:[opt(0,'Tắt (chỉ đồng bộ thủ công)'),opt(1,'Bật')]}),
 ];
 openModal(`Home Assistant · ${meter.meter_number}`,`<form id="ha-meter-form"><div class="form-grid">${fields.map(f=>fieldHTML(f,values)).join('')}</div>
 <div class="modal-hint">Nhập đúng 4 Entity ID từ Developer Tools → States. Dùng dấu chấm thập phân trong giá trị sensor. Dữ liệu nhập là tạm tính, chưa phải hóa đơn EVN; không ghi đè kỳ nhập tay/đã thanh toán. Cần chọn đúng kỳ: sensor đang báo tháng nào thì chọn tháng đó.</div>
 ${values.last_error?`<div class="modal-hint" style="color:#b54747">Lỗi lần trước: ${esc(values.last_error)}</div>`:''}
 <div id="ha-meter-result" role="status"></div></form>`,
 `<button type="button" class="btn btn-outline" data-utility="ha-preview" data-id="${id}">Xem trước (sensor đã lưu)</button>
  <button type="submit" form="ha-meter-form" class="btn btn-primary">Lưu sensor</button>`,true);
}
async function haSyncMeter(id){
 if(state.user?.role!=='admin')return;
 try{
  const out=await api('ha/sync/'+Number(id),'POST',{});
  const msg=out.result==='skipped_manual'?'Kỳ này đã nhập thủ công hoặc đã trả tiền. Không ghi đè.':
   `Đã đồng bộ ${out.period}: ${out.billed_usage.toLocaleString('en-US')} kWh, ${amount(out.bill_amount)}.`;
  await loadUtilityData();renderPage();toast(msg);
 }catch(err){toast(err.message,true);}
}
async function saveHaForm(form){
 if(busy)return;
 busy=true;
 try{
  const values=Object.fromEntries(new FormData(form));
  const isConfig=form.id==='ha-config-form';
  const id=modalContext?.id;
  await api(isConfig?'ha/config':'ha/mappings/'+id,'PUT',values);
  closeModal();
  if(!isConfig)await loadUtilityData();
  renderPage();toast('Đã lưu cấu hình Home Assistant.');
 }catch(err){toast(err.message,true);}finally{busy=false;}
}
async function haTestOrPreview(action,id){
 try{
  const out=action==='ha-test'?await api('ha/test'):await api('ha/preview/'+Number(id),'POST',{});
  const target=document.getElementById(action==='ha-test'?'ha-connect-result':'ha-meter-result');
  if(target)target.textContent=out.ok?(action==='ha-test'?out.message:
  `Kỳ ${out.period}: ${out.reading_old.toLocaleString('en-US')} → ${out.reading_new.toLocaleString('en-US')} kWh; sản lượng ${out.billed_usage.toLocaleString('en-US')} kWh; tiền ${amount(out.bill_amount)}.`):out.message;
  if(!out.ok)toast(out.message,true);
 }catch(err){toast(err.message,true);}
}

init();
