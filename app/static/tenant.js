'use strict';

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const currency = value => (Number(value) || 0).toLocaleString('en-US') + ' đ';
const num = value => (Number(value) || 0).toLocaleString('en-US', {maximumFractionDigits:3});
const dateText = value => /^\d{4}-\d{2}-\d{2}$/.test(String(value || '')) ? `${value.slice(8,10)}/${value.slice(5,7)}/${value.slice(0,4)}` : (value ? esc(value) : '—');
const periodText = value => /^\d{4}-\d{2}$/.test(String(value || '')) ? `${value.slice(5,7)}/${value.slice(0,4)}` : esc(value || '—');
const monthNow = () => {const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;};
let csrf = '', dashboard = null, repairs = [], activeTab = 'overview';

const icons = {
  overview:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
  rooms:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 21v-5h6v5M8 8h2m4 0h2M8 12h2m4 0h2"/>',
  invoices:'<path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6"/>',
  prepaid:'<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 10h18M16 15h2"/>',
  meters:'<path d="m12 2-8 11h7l-1 9 10-13h-8l2-7z"/>',
  repairs:'<path d="M14 7a5 5 0 0 0-6 6l-5 5 3 3 5-5a5 5 0 0 0 6-6l-3 3-3-3z"/>',
  owner:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  arrow:'<path d="M5 12h14m-7-7 7 7-7 7"/>',
  check:'<path d="m4 12 5 5L20 6"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'
};
function icon(name, size=19){return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${icons[name]||icons.overview}</svg>`;}
const nav = [
  ['overview','Tổng quan','overview'],
  ['rooms','Phòng đang thuê','rooms'],
  ['invoices','Hóa đơn','invoices'],
  ['prepaid','Tiền thuê trả trước','prepaid'],
  ['meters','Điện & nước','meters'],
  ['repairs','Yêu cầu sửa chữa','repairs'],
  ['owner','Liên hệ chủ nhà','owner']
];

async function req(url, options={}){
  const r=await fetch(url,{credentials:'same-origin',...options,headers:{...(options.headers||{}),...(options.method&&options.method!=='GET'?{'x-csrf-token':csrf}:{})}});
  const j=await r.json().catch(()=>({}));
  if(!r.ok) throw Error(typeof j.detail==='string'?j.detail:'Yêu cầu không hợp lệ.');
  return j;
}
function notice(message, isError=false){
  $('#alert').innerHTML=message?`<div class="${isError?'warn':'ok'}" role="status">${esc(message)}</div>`:'';
}
function empty(title, description){return `<div class="empty"><div class="empty-mark">${icon('check',25)}</div><strong>${esc(title)}</strong><p>${esc(description)}</p></div>`;}
function sectionHeading(label, heading, detail=''){
  return `<div class="section-heading"><div><div class="eyebrow">${esc(label)}</div><h2>${esc(heading)}</h2>${detail?`<p>${esc(detail)}</p>`:''}</div></div>`;
}
function box(title, body, extraClass=''){
  return `<section class="surface ${extraClass}"><div class="surface-heading"><h3>${title}</h3></div>${body}</section>`;
}
function field(label, value){return `<div class="detail-line"><span>${esc(label)}</span><strong>${value}</strong></div>`;}
function tabLink(name,text,cls='text-link'){return `<button type="button" class="${cls}" data-tab="${name}">${esc(text)} ${icon('arrow',16)}</button>`;}
function coveredPeriods(data){
  return (data.prepayments||[]).flatMap(b => (b.periods||[]).filter(p=>p.status==='active').map(p=>({...p,contract_id:b.contract_id,room_code:b.room_code})));
}
function invoiceOutstanding(data){return (data.invoices||[]).reduce((sum,i)=>sum+Math.max(0,Number(i.total)-Number(i.paid)),0);}

function renderOverview(d){
  const contract=d.contracts[0];
  const future=coveredPeriods(d).filter(p=>p.period>=monthNow());
  const futureTotal=future.reduce((sum,p)=>sum+Number(p.amount),0);
  const overdue=invoiceOutstanding(d);
  const latest=d.invoices.slice(0,3);
  return `${sectionHeading('TRANG CHỦ','Tổng quan của bạn','Thông tin quan trọng về phòng thuê và các khoản thanh toán.')}
  <div class="welcome-band"><div><span class="welcome-caption">KHÔNG GIAN DÀNH RIÊNG CHO BẠN</span><h3>Xin chào, ${esc(d.tenant.name)} <span class="wave">👋</span></h3><p>Mọi thông tin thuê phòng của bạn được sắp xếp gọn gàng theo từng mục.</p>${contract?`<span class="welcome-pill">${icon('rooms',15)} Phòng ${esc(contract.room_code)} · ${esc(contract.property_name)}</span>`:''}</div><div class="welcome-art" aria-hidden="true">⌂</div></div>
  <div class="stat-grid">
    <div class="stat-card"><span class="stat-icon teal">${icon('rooms',22)}</span><span class="stat-label">Tiền thuê hàng tháng</span><strong>${contract?currency(contract.monthly_rent):'—'}</strong><span class="stat-help">${contract?'Theo hợp đồng đang hiệu lực':'Chưa có hợp đồng'}</span></div>
    <div class="stat-card"><span class="stat-icon amber">${icon('invoices',22)}</span><span class="stat-label">Hóa đơn còn phải thanh toán</span><strong>${currency(overdue)}</strong><span class="stat-help">Tổng số còn lại của hóa đơn đã phát hành</span></div>
    <div class="stat-card"><span class="stat-icon violet">${icon('prepaid',22)}</span><span class="stat-label">Tiền thuê trả trước từ tháng này</span><strong>${currency(futureTotal)}</strong><span class="stat-help">${future.length?`${future.length} kỳ tháng chưa hoàn tiền`:'Chưa có kỳ trả trước sắp tới'}</span></div>
  </div>
  <div class="two-column"><section class="surface"><div class="surface-heading"><h3>Phòng thuê của tôi</h3>${tabLink('rooms','Xem phòng')}</div>
  ${contract?`<div class="room-preview"><div class="room-avatar">${icon('rooms',29)}</div><div><b>Phòng ${esc(contract.room_code)}</b><p>${esc(contract.property_name)}</p></div><span class="chip success">Đang thuê</span></div>
  <div class="compact-details">${field('Thời hạn hợp đồng',`${dateText(contract.start_date)} – ${dateText(contract.end_date)}`)}${field('Điện',`${currency(contract.electric_rate)}/kWh`)}${field('Nước',`${currency(contract.water_rate)}/m³`)}</div>`:empty('Chưa có phòng đang thuê','Liên hệ quản lý để kiểm tra hợp đồng của bạn.')}</section>
  <section class="surface"><div class="surface-heading"><h3>Hóa đơn gần đây</h3>${tabLink('invoices','Xem tất cả')}</div>
  ${latest.length?latest.map(i=>`<div class="activity-row"><span class="activity-icon">${icon('invoices')}</span><div class="activity-main"><strong>Hóa đơn tháng ${periodText(i.period)}</strong><small>${Number(i.paid)>=Number(i.total)?'Đã thanh toán đủ':'Còn lại '+currency(Math.max(0,Number(i.total)-Number(i.paid)))}</small></div><b>${currency(i.total)}</b></div>`).join(''):empty('Chưa có hóa đơn','Hóa đơn sẽ xuất hiện khi được quản lý phát hành.')}</section></div>
  <div class="quick-section"><div class="surface-heading"><h3>Truy cập nhanh</h3></div><div class="quick-grid">
  <button data-tab="prepaid" class="quick-action">${icon('prepaid',22)}<span>Xem tiền trả trước</span>${icon('arrow',17)}</button>
  <button data-tab="meters" class="quick-action">${icon('meters',22)}<span>Gửi chỉ số điện nước</span>${icon('arrow',17)}</button>
  <button data-tab="repairs" class="quick-action">${icon('repairs',22)}<span>Báo sự cố phòng</span>${icon('arrow',17)}</button></div></div>`;
}
function renderRooms(d){
  return `${sectionHeading('HỢP ĐỒNG & CHI PHÍ','Phòng đang thuê','Đơn giá hiện tại và các thông tin cần biết về phòng của bạn.')}
  ${d.contracts.length?d.contracts.map(c=>{
    const advance=(d.prepayments||[]).filter(b=>b.contract_id===c.contract_id).flatMap(b=>b.periods.filter(p=>p.status==='active'));
    const advanceTotal=advance.reduce((sum,p)=>sum+Number(p.amount),0);
    const advanceMonths=[...new Set(advance.map(p=>p.period))].sort();
    return `<section class="surface room-card"><div class="room-card-top"><div class="room-icon">${icon('rooms',28)}</div><div><span class="eyebrow">PHÒNG ĐANG THUÊ</span><h3>Phòng ${esc(c.room_code)}</h3><p>${esc(c.property_name)}</p></div><span class="chip success">Đang hiệu lực</span></div>
    <div class="rent-highlight"><div><span>TIỀN THUÊ PHÒNG / THÁNG</span><strong>${currency(c.monthly_rent)}</strong></div><span class="rent-icon">${icon('prepaid',28)}</span></div>
    <div class="price-grid">
      <div class="price-tile"><div class="price-icon">${icon('meters',21)}</div><span>Đơn giá điện</span><strong>${currency(c.electric_rate)}<small> / kWh</small></strong></div>
      <div class="price-tile"><div class="price-icon water-mark">◉</div><span>Đơn giá nước</span><strong>${currency(c.water_rate)}<small> / m³</small></strong></div>
      <div class="price-tile"><div class="price-icon service-mark">◎</div><span>Phí dịch vụ</span><strong>${Number(c.service_fee)>0?currency(c.service_fee):'Không thu'}${Number(c.service_fee)>0?'<small> / tháng</small>':''}</strong></div>
    </div>
    <p class="hint">Đây là mức giá hiện tại do chủ nhà cấu hình. Số tiền thực tế từng kỳ được thể hiện trên hóa đơn.</p>
    <div class="contract-details">${field('Hợp đồng từ ngày',dateText(c.start_date))}${field('Đến ngày',dateText(c.end_date))}${field('Ngày đến hạn thanh toán',`Ngày ${num(c.due_day)} hàng tháng`)}${field('Tiền cọc theo hợp đồng',currency(c.deposit))}</div>
    <div class="advance-inline"><div class="advance-icon">${icon('prepaid',22)}</div><div><b>Tiền nhà đã đóng trước</b>${advance.length?`<p>Đã ghi nhận <strong>${currency(advanceTotal)}</strong> cho ${advance.length} kỳ tháng chưa hoàn tiền${advanceMonths.length?`, từ ${periodText(advanceMonths[0])} đến ${periodText(advanceMonths[advanceMonths.length-1])}`:''}.</p>`:'<p>Chưa có khoản tiền thuê trả trước được ghi nhận cho phòng này.</p>'}</div>${tabLink('prepaid','Chi tiết')}</div>
    </section>`;
  }).join(''):empty('Chưa có hợp đồng đang hiệu lực','Thông tin phòng thuê sẽ hiển thị sau khi quản lý kích hoạt hợp đồng.')}`;
}
function renderInvoices(d){
  return `${sectionHeading('THANH TOÁN','Hóa đơn của tôi','Xem tổng tiền, số tiền đã thu và từng khoản cấu thành hóa đơn.')}
  <div class="overview-numbers"><div><small>TỔNG CÒN PHẢI THANH TOÁN</small><strong>${currency(invoiceOutstanding(d))}</strong></div><span>${icon('invoices',28)}</span></div>
  ${d.invoices.length?`<div class="invoice-stack">${d.invoices.map(i=>{
    const balance=Math.max(0,Number(i.total)-Number(i.paid));
    return `<details class="invoice-entry"><summary><div class="invoice-icon">${icon('invoices',23)}</div><div class="invoice-title"><strong>Hóa đơn tháng ${periodText(i.period)}</strong><small>${dateText((i.created_at||'').slice(0,10))}</small></div><div class="invoice-amount"><strong>${currency(i.total)}</strong><span class="chip ${balance?'pending':'success'}">${balance?'Còn '+currency(balance):'Đã thanh toán'}</span></div><span class="expand-arrow">⌄</span></summary><div class="invoice-breakdown"><p class="muted">Tiền thuê ${periodText(i.period)} · Điện/nước ${periodText(i.utility_period||i.period)}</p>${Number(i.paid)>Number(i.total)?`<p class="muted">Đã thu thừa ${currency(Number(i.paid)-Number(i.total))} · Chờ chủ nhà đối soát.</p>`:''}
    ${field('Tiền thuê',currency(i.rent))}${field(`Tiền điện (${num(i.electric_usage)} kWh)`,currency(i.electricity))}${field(`Tiền nước (${num(i.water_usage)} m³)`,currency(i.water))}${field('Phí dịch vụ',currency(i.services))}${Number(i.adjustment)?field('Điều chỉnh',currency(i.adjustment)):''}
    <div class="invoice-totals">${field('Tổng hóa đơn',currency(i.total))}${field('Đã thu',currency(i.paid))}${field('Cần thanh toán',`<span class="${balance?'due-text':'paid-text'}">${currency(balance)}</span>`)}</div></div></details>`;
  }).join('')}</div>`:empty('Chưa có hóa đơn','Khi chủ nhà phát hành hóa đơn, bạn sẽ xem được chi tiết tại đây.')}
  <div class="small-callout">${icon('prepaid',19)} <div>Tiền thuê đã trả trước được quản lý ghi nhận riêng theo từng tháng. ${tabLink('prepaid','Xem khoản trả trước')}</div></div>`;
}
function renderPrepaid(d){
  const batches=d.prepayments||[];
  const active=coveredPeriods(d);
  const sum=active.reduce((total,p)=>total+Number(p.amount),0);
  const upcoming=active.filter(p=>p.period>=monthNow());
  const upcomingSum=upcoming.reduce((total,p)=>total+Number(p.amount),0);
  return `${sectionHeading('THANH TOÁN TRƯỚC','Tiền thuê đã đóng trước','Thời gian đã thanh toán, số tiền từng tháng và lịch sử hoàn tiền nếu có.')}
  <div class="prepaid-summary"><div><small>TỔNG TIỀN TRẢ TRƯỚC ĐÃ GHI NHẬN, CHƯA HOÀN</small><strong>${currency(sum)}</strong><span>${active.length} kỳ tháng</span></div><div class="prepaid-divider"></div><div><small>ÁP DỤNG TỪ THÁNG HIỆN TẠI TRỞ ĐI</small><strong>${currency(upcomingSum)}</strong><span>${upcoming.length} kỳ tháng</span></div></div>
  <p class="hint">Số tiền đã ghi nhận bao gồm cả những tháng đã qua; không có nghĩa toàn bộ số tiền đó còn dư. Khoản đã hoàn sẽ được đánh dấu riêng.</p>
  ${batches.length?batches.map(b=>{
    const all=b.periods||[];
    const refunded=Number(b.refunded_amount)>0;
    const valid=all.filter(p=>p.status==='active');
    const from=all[0]?.period,to=all[all.length-1]?.period;
    return `<article class="surface prepaid-batch"><div class="batch-header"><div class="batch-heading"><span class="batch-icon">${icon('prepaid',23)}</span><div><span class="eyebrow">LẦN THU #${num(b.batch_id)} · PHÒNG ${esc(b.room_code)}</span><h3>${currency(b.total_paid)}</h3><p>Đã nhận ngày ${dateText(b.paid_on)}</p></div></div><span class="chip ${valid.length?'success':'rejected'}">${!valid.length?'Đã hoàn toàn bộ':refunded?'Hoàn một phần':'Đã ghi nhận'}</span></div>
    <div class="batch-facts">${field('Thời gian đã đóng trước',from===to?`Tháng ${periodText(from)}`:`Tháng ${periodText(from)} – ${periodText(to)}`)}${field('Phương thức',esc(({cash:'Tiền mặt',transfer:'Chuyển khoản',other:'Khác'})[b.method]||'Khác'))}${field('Số tiền chưa hoàn',`<span class="paid-text">${currency(b.active_amount)}</span>`)}${refunded?field('Số tiền đã hoàn trả',currency(b.refunded_amount)):''}</div>
    <div class="period-label">CHI TIẾT THEO TỪNG THÁNG</div><div class="period-grid">${all.map(p=>`<div class="period-tile ${p.status==='refunded'?'is-refunded':''}"><span>Tháng ${periodText(p.period)}</span><strong>${currency(p.amount)}</strong><small>${p.status==='refunded'?'Đã hoàn tiền':'Đã trả trước'}</small></div>`).join('')}</div></article>`;
  }).join(''):empty('Chưa có khoản trả trước','Khi chủ nhà ghi nhận khoản đóng tiền thuê trước, bạn sẽ thấy kỳ tháng và số tiền tương ứng ở đây.')}`;
}
function renderMeters(d){
  return `${sectionHeading('CHỈ SỐ TIÊU THỤ','Điện & nước','Gửi chỉ số đồng hồ và theo dõi trạng thái duyệt của quản lý.')}
  <div class="two-column meters-columns"><section class="surface"><div class="surface-heading"><h3>Gửi chỉ số mới</h3><span class="chip pending">Chờ quản lý duyệt</span></div><p class="form-help">Vui lòng gửi số trên đồng hồ và ảnh chụp rõ nét. Chỉ số được tính khi quản lý xác nhận.</p>
  ${d.contracts.length?`<form id="meter-form"><label for="meter-room">Hợp đồng / Phòng</label><select id="meter-room" name="contract_id" required>${d.contracts.map(c=>`<option value="${Number(c.contract_id)}">Phòng ${esc(c.room_code)} · ${esc(c.property_name)}</option>`).join('')}</select><label for="meter-period">Kỳ cần gửi</label><input id="meter-period" type="month" name="period" required value="${monthNow()}"><div class="input-group"><div><label for="meter-electric">Chỉ số điện mới (kWh)</label><input id="meter-electric" type="number" step="0.001" min="0" name="electric_new" placeholder="Nhập chỉ số" required></div><div><label for="meter-water">Chỉ số nước mới (m³)</label><input id="meter-water" type="number" step="0.001" min="0" name="water_new" placeholder="Nhập chỉ số" required></div></div><label for="electric-photo">Ảnh đồng hồ điện</label><input id="electric-photo" type="file" name="electric_photo" accept="image/*" required><label for="water-photo">Ảnh đồng hồ nước</label><input id="water-photo" type="file" name="water_photo" accept="image/*" required><button class="primary full-width" type="submit">Gửi chỉ số để duyệt ${icon('arrow',17)}</button></form>`:empty('Chưa có hợp đồng','Bạn cần hợp đồng đang hiệu lực để gửi chỉ số.')}</section>
  <section class="surface"><div class="surface-heading"><h3>Lịch sử gửi chỉ số</h3></div>${d.submissions.length?d.submissions.map(s=>`<div class="activity-row stacked"><span class="activity-icon">${icon('meters')}</span><div class="activity-main"><strong>Tháng ${periodText(s.period)}</strong><small>Điện: ${num(s.electric_new)} kWh · Nước: ${num(s.water_new)} m³</small><div class="photo-links"><a href="/api/tenant/submissions/${Number(s.id)}/photo/electric" target="_blank" rel="noopener">Ảnh điện</a><a href="/api/tenant/submissions/${Number(s.id)}/photo/water" target="_blank" rel="noopener">Ảnh nước</a></div>${s.feedback?`<small class="feedback">${esc(s.feedback)}</small>`:''}</div><span class="chip ${esc(s.status)}">${({pending:'Chờ duyệt',approved:'Đã duyệt',rejected:'Từ chối'})[s.status]||'—'}</span></div>`).join(''):empty('Chưa gửi chỉ số nào','Chỉ số bạn gửi sẽ xuất hiện tại đây.')}</section></div>
  ${box('Chỉ số đã được xác nhận',d.readings.length?d.readings.map(r=>`<div class="meter-history"><div><strong>Phòng ${esc(r.room_code)}</strong><small>Tháng ${periodText(r.period)}</small></div><div><span>Điện</span><strong>${num(r.electric_old)} → ${num(r.electric_new)}</strong><small>+${num(Number(r.electric_new)-Number(r.electric_old))} kWh</small></div><div><span>Nước</span><strong>${num(r.water_old)} → ${num(r.water_new)}</strong><small>+${num(Number(r.water_new)-Number(r.water_old))} m³</small></div></div>`).join(''):empty('Chưa có chỉ số xác nhận','Các chỉ số đã được duyệt sẽ hiển thị tại đây.'),'meter-history-surface')}`;
}
function renderRepairs(d){
  const today=new Date().toLocaleDateString('vi-VN');
  const live=d.contracts.filter(c=>c.start_date<=new Date().toLocaleDateString('sv-SE')&&c.end_date>=new Date().toLocaleDateString('sv-SE'));
  return `${sectionHeading('HỖ TRỢ PHÒNG THUÊ','Yêu cầu sửa chữa','Báo sự cố trong phòng và cập nhật tiến độ xử lý.')}
  <div class="two-column repairs-columns"><section class="surface"><div class="surface-heading"><h3>Gửi yêu cầu mới</h3></div><p class="form-help">Phòng được xác định từ hợp đồng đang hiệu lực của bạn.</p>
  ${live.length===1?`<form id="repair-form"><div class="room-inline">${icon('rooms',19)} Phòng <b>${esc(live[0].room_code)} · ${esc(live[0].property_name)}</b></div><label for="repair-category">Loại sự cố</label><select id="repair-category" name="category"><option value="other">Khác</option><option value="electric">Điện</option><option value="water">Nước</option><option value="internet">Internet</option><option value="furniture">Nội thất</option></select><label for="repair-title">Tiêu đề vấn đề *</label><input id="repair-title" name="title" required maxlength="160" placeholder="Ví dụ: Điều hòa không làm lạnh"><div class="input-group"><div><label for="repair-priority">Mức độ ưu tiên</label><select id="repair-priority" name="priority"><option value="low">Thấp</option><option value="medium" selected>Trung bình</option><option value="high">Cao</option></select></div><div><label for="repair-date">Ngày báo</label><input id="repair-date" readonly value="${today}"></div></div><label for="repair-description">Mô tả chi tiết</label><textarea id="repair-description" name="description" maxlength="1000" placeholder="Vị trí và biểu hiện của sự cố..."></textarea><label for="repair-photos">Ảnh đính kèm (tối đa 5 ảnh, 3 MB/ảnh)</label><input id="repair-photos" name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple><div id="repair-preview" class="repair-preview"></div><button class="primary full-width" type="submit">Gửi yêu cầu sửa chữa ${icon('arrow',17)}</button></form>`:empty('Không thể gửi yêu cầu','Cần đúng một hợp đồng đang hiệu lực để hệ thống xác định phòng.')}</section>
  <section class="surface"><div class="surface-heading"><h3>Yêu cầu đã gửi</h3><span class="chip neutral">${repairs.length} yêu cầu</span></div>${repairs.length?repairs.map(t=>`<div class="repair-item"><div class="repair-top"><strong>${esc(t.title)}</strong><span class="chip ${t.status==='done'?'success':t.status==='new'?'pending':'neutral'}">${esc(({new:'Mới tiếp nhận',in_progress:'Đang xử lý',done:'Hoàn thành'})[t.status]||t.status)}</span></div><p class="repair-meta">Phòng ${esc(t.room_code)} · ${dateText((t.reported_at||'').slice(0,10))} · ${esc(({low:'Thấp',medium:'Trung bình',high:'Cao'})[t.priority]||t.priority)}</p><p>${esc(t.description||'Không có mô tả bổ sung.')}</p>${t.photo_count?`<button type="button" class="outline small-action" data-repair-photos="${Number(t.id)}">Xem ${num(t.photo_count)} ảnh</button>`:''}<div class="repair-preview" id="repair-gallery-${Number(t.id)}"></div></div>`).join(''):empty('Chưa có yêu cầu sửa chữa','Yêu cầu mới sẽ được hiển thị ở đây để bạn theo dõi.')}</section></div>`;
}
function renderOwner(d){
  const owner=d.owner||{};
  const labels={name:'Họ và tên',gender:'Giới tính',age:'Tuổi',address:'Địa chỉ',phone:'Số điện thoại',email:'Email'};
  const fields=Object.entries(labels).filter(([k])=>owner[k]!==undefined&&owner[k]!==null&&owner[k]!=='');
  return `${sectionHeading('THÔNG TIN LIÊN HỆ','Thông tin chủ cho thuê','Những thông tin liên hệ mà chủ nhà lựa chọn công khai cho bạn.')}
  <section class="surface owner-surface"><div class="owner-hero"><div class="owner-portrait">${owner.photo_url?`<img src="${esc(owner.photo_url)}" alt="Ảnh chủ nhà">`:icon('owner',37)}</div><div><div class="eyebrow">CHỦ CHO THUÊ</div><h3>${esc(owner.name||'Quản lý cơ sở')}</h3><p>${esc(d.tenant.property)}</p></div></div>
  ${fields.length?`<div class="owner-details">${fields.map(([k,label])=>field(label,esc(owner[k]))).join('')}</div>`:empty('Chưa có thông tin công khai','Bạn có thể liên hệ quản lý theo thông tin được cung cấp khi ký hợp đồng.')}
  ${(owner.phone||owner.email)?`<div class="owner-actions">${owner.phone?`<a class="primary" href="tel:${esc(String(owner.phone).replace(/[^+0-9]/g,''))}">Gọi chủ nhà</a>`:''}${owner.email?`<a class="outline" href="mailto:${esc(owner.email)}">Gửi email</a>`:''}</div>`:''}</section>`;
}

function selectTab(tab, scroll=false){
  if(!nav.some(n=>n[0]===tab)) return;
  activeTab=tab;
  document.querySelectorAll('[data-nav-tab]').forEach(b=>{
    const selected=b.dataset.navTab===tab;
    b.classList.toggle('active',selected);
    b.setAttribute('aria-selected',String(selected));
    b.tabIndex=selected?0:-1;
  });
  document.querySelectorAll('[data-pane]').forEach(p=>{p.hidden=p.dataset.pane!==tab;});
  const target=$(`[data-nav-tab="${tab}"]`);
  if(target && scroll && window.matchMedia('(max-width: 850px)').matches){
    target.scrollIntoView({behavior:'smooth',inline:'nearest',block:'nearest'});
  }
  if(scroll){const area=$('.page-content');if(area)area.scrollIntoView({behavior:'smooth',block:'start'});}
}
async function home(tab=activeTab){
  const d=await req('/api/tenant/home');
  const history=await req('/api/tenant/tickets');
  dashboard=d;repairs=history;
  const screens={overview:renderOverview(d),rooms:renderRooms(d),invoices:renderInvoices(d),prepaid:renderPrepaid(d),meters:renderMeters(d),repairs:renderRepairs(d),owner:renderOwner(d)};
  $('#portal').innerHTML=`<div class="portal-identity"><div><div class="eyebrow">CỔNG THÔNG TIN KHÁCH THUÊ</div><h1>Không gian của tôi</h1><p>${esc(d.tenant.property)} <span class="dot">•</span> ${esc(d.tenant.phone)}</p></div><div class="account-badge"><span class="account-avatar">${esc((d.tenant.name||'K').trim().slice(-1).toUpperCase())}</span><div><small>TÀI KHOẢN KHÁCH THUÊ</small><b>${esc(d.tenant.name)}</b></div></div></div>
  <div class="app-shell"><aside class="side-menu"><div class="menu-caption">DANH MỤC</div><nav role="tablist" aria-label="Menu khách thuê">${nav.map(([key,label,ic])=>`<button class="nav-item" type="button" data-nav-tab="${key}" role="tab" aria-controls="view-${key}" aria-selected="false">${icon(ic,20)}<span>${label}</span></button>`).join('')}</nav><div class="sidebar-note">${icon('check',18)}<span>Thông tin riêng tư chỉ hiển thị cho tài khoản của bạn.</span></div></aside>
  <div class="page-content">${nav.map(([key,label])=>`<section id="view-${key}" data-pane="${key}" role="tabpanel" aria-label="${label}" hidden>${screens[key]}</section>`).join('')}</div></div>`;
  selectTab(tab);
}
function loginScreen(){
  $('#portal').innerHTML=`<section class="login surface"><div class="eyebrow">TRỌFLOW · KHÁCH THUÊ</div><h1>Đăng nhập</h1><p>Đăng nhập để xem thông tin phòng thuê, hóa đơn và gửi chỉ số điện nước.</p><form id="login"><label for="login-phone">Số điện thoại</label><input id="login-phone" type="tel" name="phone" autocomplete="username" required placeholder="Số điện thoại đăng ký"><label for="login-password">Mật khẩu</label><input id="login-password" type="password" name="password" autocomplete="current-password" required><label for="login-code">Mã bảo vệ (khi quản lý yêu cầu)</label><input id="login-code" name="access_code" autocomplete="off" placeholder="Mã được chủ nhà cấp"><small class="form-help">Khi bật chế độ truy cập Internet an toàn, tài khoản có thể cần mã bảo vệ bổ sung.</small><button class="primary full-width" type="submit">Đăng nhập ${icon('arrow',17)}</button></form><p class="login-footnote">Tài khoản được chủ nhà cấp. Vui lòng liên hệ quản lý nếu quên thông tin đăng nhập.</p></section>`;
}
async function boot(){
  try{const me=await req('/api/tenant/auth/me');csrf=me.csrf;$('#exit').hidden=false;await home();}
  catch(e){csrf='';$('#exit').hidden=true;loginScreen();}
}

document.addEventListener('click',async e=>{
  const navTarget=e.target.closest('[data-tab],[data-nav-tab]');
  if(navTarget){selectTab(navTarget.dataset.tab||navTarget.dataset.navTab,true);return;}
  const btn=e.target.closest('[data-repair-photos]');
  if(!btn)return;
  const id=Number(btn.dataset.repairPhotos);
  try{
    const images=await req('/api/tenant/tickets/'+id+'/photos');
    const el=$('#repair-gallery-'+id);
    if(el)el.innerHTML=images.map(p=>`<a href="${esc(p.url)}" target="_blank" rel="noopener"><img src="${esc(p.url)}" alt="Ảnh sự cố"></a>`).join('');
  }catch(ex){notice(ex.message,true);}
});

document.addEventListener('submit',async e=>{
  if(e.target.id==='login'){
    e.preventDefault();const form=e.target,btn=form.querySelector('button');btn.disabled=true;
    try{const response=await req('/api/tenant/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(form)))});csrf=response.csrf;$('#exit').hidden=false;activeTab='overview';await home('overview');notice('Đăng nhập thành công.');}
    catch(ex){notice(ex.message,true);}finally{btn.disabled=false;}return;
  }
  if(e.target.id==='meter-form'){
    e.preventDefault();const form=e.target,btn=form.querySelector('button');btn.disabled=true;
    try{await req('/api/tenant/readings/submit',{method:'POST',body:new FormData(form)});await home('meters');notice('Đã gửi chỉ số và ảnh. Vui lòng chờ quản lý duyệt.');}
    catch(ex){notice(ex.message,true);}finally{btn.disabled=false;}return;
  }
  if(e.target.id==='repair-form'){
    e.preventDefault();const form=e.target,btn=form.querySelector('button');const photos=[...form.elements.photos.files];
    if(photos.length>5||photos.some(f=>f.size>3*1024*1024)){notice('Tối đa 5 ảnh, mỗi ảnh 3 MB.',true);return;}
    btn.disabled=true;
    try{await req('/api/tenant/tickets',{method:'POST',body:new FormData(form)});await home('repairs');notice('Yêu cầu sửa chữa đã được gửi cho quản lý.');}
    catch(ex){notice(ex.message,true);}finally{btn.disabled=false;}
  }
});

document.addEventListener('change',e=>{
  if(e.target.id!=='repair-photos')return;
  const fs=[...e.target.files],el=$('#repair-preview');
  if(fs.length>5||fs.some(f=>f.size>3*1024*1024)){
    notice('Tối đa 5 ảnh, mỗi ảnh 3 MB.',true);e.target.value='';el.innerHTML='';return;
  }
  el.innerHTML=fs.map((f,i)=>`<span><img src="${URL.createObjectURL(f)}" alt="Ảnh đính kèm ${i+1}"><small>${esc(f.name)}</small></span>`).join('');
});
$('#exit').addEventListener('click',async()=>{
  try{await req('/api/tenant/auth/logout',{method:'POST'});}finally{csrf='';window.location.reload();}
});
boot();
