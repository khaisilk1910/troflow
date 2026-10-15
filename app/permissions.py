"""Per-user capability flags enforced by the API, not by browser controls.
Existing staff accounts retain their V2 job defaults until an admin customizes them.
"""
from .db import rows

GROUPS = [
 ('dashboard','Tổng quan',['view']),('properties','Cơ sở',['view','create','edit','delete']),
 ('utilitymeters','Công tơ & điện nước tổng',['view','create','edit','delete','record','deletebill','report']),
 ('rooms','Phòng trọ',['view','create','edit','delete']),('tenants','Người thuê',['view','create','edit','delete']),
 ('contracts','Hợp đồng',['view','create','edit','delete','end','proration']),
 ('readings','Điện nước',['view','record','edit','delete','batch','photos']),
 ('invoices','Hóa đơn',['view','preview','create','edit','publish','delete','pdf','vietqr']),
 ('payments','Thu tiền hóa đơn',['view','record','edit','delete']),
 ('prepayments','Tiền thuê trả trước',['view','record','refund']),
 ('deposits','Tiền cọc',['view','record']),('residents','Người ở cùng',['view','create','leave']),
 ('services','Phí dịch vụ',['view','create','edit','assign','remove']),
 ('expenses','Chi phí',['view','create','edit','delete']),
 ('tickets','Sửa chữa',['view','create','edit','delete']),
 ('handovers','Bàn giao',['view','create','pdf']),
 ('imports','Nhập Excel',['view','execute']),('schedules','Lịch hóa đơn',['view','edit','execute']),
 ('reports','Báo cáo',['view']),('export','Xuất CSV',['execute']),
 ('files','Tài liệu và ảnh',['view','upload']),
 ('users','Tài khoản (Admin)',['view','create','edit']),
 ('access','Phân quyền (Admin)',['view','edit']),
 ('backups','Sao lưu / phục hồi (Admin)',['view','create','verify','restore','edit']),
 ('bank','Tài khoản ngân hàng (Admin)',['view','edit','create','delete']),
 ('zalo','Thông báo Zalo (Admin)',['view','edit','create','delete','send']),
 ('audit','Nhật ký hệ thống (Admin)',['view'])
]
ACTIONS={'view':'Xem','create':'Thêm','edit':'Sửa','delete':'Xóa','record':'Ghi nhận',
         'batch':'Ghi hàng loạt','photos':'Ảnh công tơ','publish':'Duyệt chốt','preview':'Xem trước',
         'pdf':'Xuất PDF','vietqr':'VietQR','end':'Kết thúc','proration':'Tính ngày',
         'deletebill':'Xóa kỳ','report':'Thống kê lãi lỗ','refund':'Hoàn / hủy','leave':'Báo rời','assign':'Gán dịch vụ','remove':'Ngừng dịch vụ',
         'execute':'Thực hiện','upload':'Tải lên','verify':'Kiểm tra','restore':'Phục hồi'}
ADMIN_ONLY={'users','access','backups','bank','zalo','audit'}
ADMIN_RESERVED={'properties.create','properties.delete'}
ALL_KEYS={f'{group}.{action}' for group,_,actions in GROUPS for action in actions}
ROLE_MODULES={
 'manager':{'dashboard','properties','utilitymeters','rooms','tenants','contracts','readings','invoices','payments','prepayments',
            'deposits','residents','services','expenses','tickets','handovers','imports','schedules','reports','export','files'},
 'accountant':{'dashboard','properties','utilitymeters','rooms','tenants','contracts','readings','invoices','payments','prepayments',
            'deposits','services','expenses','reports','export','imports','files'},
 'collector':{'dashboard','properties','rooms','tenants','contracts','invoices','payments','prepayments','deposits','reports'},
 'maintenance':{'dashboard','properties','utilitymeters','rooms','tenants','contracts','readings','tickets','handovers','files'},
 'viewer':{group for group,_,_ in GROUPS if group not in ADMIN_ONLY}
}
ROLE_WRITE={
 'manager':{'utilitymeters','rooms','tenants','contracts','readings','invoices','payments','prepayments','deposits','residents','services','expenses','tickets','handovers','imports','schedules','files'},
 'accountant':{'utilitymeters','readings','invoices','payments','prepayments','deposits','services','expenses','imports','files'},
 'collector':{'payments','prepayments','deposits'},
 'maintenance':{'utilitymeters','readings','tickets','handovers','files'},'viewer':set()
}

def defaults(job):
    permitted={}
    for group,_,actions in GROUPS:
        for action in actions:
            permitted[f'{group}.{action}']=(group not in ADMIN_ONLY and group in ROLE_MODULES.get(job,set()) and (action=='view' or group in ROLE_WRITE.get(job,set())))
    for key in ADMIN_RESERVED:permitted[key]=False
    # Restrict destructive operations by default; admin must grant explicitly.
    for key in list(permitted):
        if key.endswith('.delete') or key in ('prepayments.refund','payments.edit'):
            permitted[key]=False
    return permitted

def effective(con,user):
    if user['role']=='admin':return {key:True for key in ALL_KEYS}
    p=defaults(user.get('job_role') or 'manager')
    for item in rows(con,'SELECT permission_key,allowed FROM user_permissions WHERE user_id=?',(user['id'],)):
        if item['permission_key'] in ALL_KEYS and item['permission_key'].split('.')[0] not in ADMIN_ONLY and item['permission_key'] not in ADMIN_RESERVED:
            p[item['permission_key']]=bool(item['allowed'])
    return p

def route_permission(path,method):
    """An unmapped authenticated API operation fails closed for staff."""
    parts=path.strip('/').split('/')
    if len(parts)<2 or parts[0]!='api':return None
    if parts[1] in ('auth','health'):return None
    v2=len(parts)>2 and parts[1]=='v2'
    p=parts[2:] if v2 else parts[1:]
    if not p:return None
    mod=p[0]
    if v2:
        if mod=='summary':return 'dashboard.view'
        if mod=='contracts':return 'contracts.proration'
        if mod=='readings':return 'readings.batch' if method!='GET' else 'readings.view'
        if mod=='deposits':return 'deposits.record' if method!='GET' else 'deposits.view'
        if mod=='residents':return 'residents.leave' if len(p)>2 and p[2]=='leave' else ('residents.create' if method!='GET' else 'residents.view')
        if mod=='services':return 'services.view' if method=='GET' else ('services.edit' if method=='PUT' else 'services.create')
        if mod=='contract-services':return 'services.view' if method=='GET' else ('services.remove' if method=='DELETE' else 'services.assign')
        if mod=='invoices':
            if method=='GET':
                return 'invoices.pdf' if p[-1]=='pdf' else 'invoices.vietqr' if p[-1]=='vietqr' else 'invoices.view'
            if p[-1]=='preview':return 'invoices.preview'
            if p[-1]=='publish':return 'invoices.publish'
            return 'invoices.create' if p[-1]=='draft' and method=='POST' else 'invoices.edit'
        if mod=='handovers':return 'handovers.pdf' if method=='GET' and p[-1]=='pdf' else ('handovers.view' if method=='GET' else 'handovers.create')
        if mod=='files':return 'files.view' if method=='GET' else 'tenants.edit' if ('tenant' in p and method!='GET') else 'files.upload'
        if mod=='imports':return 'imports.view' if method=='GET' else 'imports.execute'
        if mod=='access':return 'access.view' if method=='GET' else 'access.edit'
        if mod=='backups':
            return 'backups.view' if method=='GET' else 'backups.'+('edit' if 'config' in p else p[-1])
        if mod=='schedules':return 'schedules.view' if method=='GET' else ('schedules.execute' if 'run' in p else 'schedules.edit')
        if mod=='properties' and 'bank' in p:return 'bank.edit'
        if mod=='prepayments':return 'prepayments.view' if method=='GET' else ('prepayments.refund' if 'refund' in p else 'prepayments.record')
        return None
    if mod=='v6':
        if len(p)<2:return None
        section=p[1]
        if section=='banks':return 'bank.view' if method=='GET' else 'bank.create' if method=='POST' else 'bank.delete' if method=='DELETE' else 'bank.edit'
        if section=='invoices':return 'invoices.view'
        if section=='zalo':return 'zalo.view' if method=='GET' else 'zalo.send' if ('send' in p or 'retry' in p) else 'zalo.create' if method=='POST' else 'zalo.delete' if method=='DELETE' else 'zalo.edit'
        return None
    if mod=='utility-meters':
        if method=='GET':return 'utilitymeters.view'
        return 'utilitymeters.delete' if method=='DELETE' else 'utilitymeters.create' if method=='POST' else 'utilitymeters.edit'
    if mod=='utility-bills':
        if method=='GET':return 'utilitymeters.view'
        return 'utilitymeters.deletebill' if method=='DELETE' else 'utilitymeters.record'
    if mod=='utility-report':return 'utilitymeters.report'
    if mod=='dashboard':return 'dashboard.view'
    if mod=='reports':return 'reports.view'
    if mod=='export':return 'export.execute'
    if mod in ('users','audit'):
        return f'{mod}.'+('view' if method=='GET' else 'create' if method=='POST' else 'edit')
    if mod in ('properties','rooms','tenants','contracts','readings','invoices','payments','expenses','tickets'):
        if method=='GET':return f'{mod}.view'
        if mod=='contracts' and p[-1]=='end':return 'contracts.end'
        if mod=='invoices' and p[-1]=='generate':return 'invoices.publish'
        if mod=='readings':return 'readings.delete' if method=='DELETE' else 'readings.edit' if method in ('PUT','PATCH') else 'readings.record'
        if mod=='payments':return 'payments.delete' if method=='DELETE' else 'payments.edit' if method in ('PUT','PATCH') else 'payments.record'
        return f'{mod}.'+('create' if method=='POST' else 'edit' if method in ('PUT','PATCH') else 'delete')
    return None
