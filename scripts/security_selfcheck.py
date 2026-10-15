#!/usr/bin/env python3
"""Offline risk checks for running container; prints no secrets or tenant data."""
import os,sqlite3,stat,sys
from pathlib import Path
from app.db import DB_PATH,connect

findings=[]
def check(ok,message):
    findings.append((bool(ok),message))
    print(('[OK] ' if ok else '[WARNING] ')+message)

public=os.getenv('TROFLOW_PUBLIC_MODE')=='1'
check(public,'Chế độ Internet đã bật')
check(os.getenv('COOKIE_SECURE')=='1','Cookie Secure được cấu hình')
check(bool(os.getenv('TROFLOW_ALLOWED_HOSTS')),'Hostname được giới hạn')
key=Path(os.getenv('TROFLOW_SECRET_KEY_FILE','/run/secrets/troflow_integration_key'))
check(key.is_file(),'Khóa mã hóa bot được gắn ngoài image')
if key.is_file():
    check(not(key.stat().st_mode & (stat.S_IRWXG|stat.S_IRWXO)), 'Khóa bí mật không có quyền group/other')
secrets_path=DB_PATH.parent/'zalo-integration-credentials.json'
if secrets_path.is_file():
    import json
    try: data=json.loads(secrets_path.read_text())
    except Exception: data={}
    check('password' not in data,'Mật khẩu bot lưu tại data đã được mã hóa')
check(DB_PATH.is_file(),'Database SQLite tồn tại')
if DB_PATH.is_file():
    with connect() as con:
        no_scope=con.execute("""SELECT COUNT(*) FROM users u WHERE u.role='staff' AND u.active=1 AND NOT EXISTS
           (SELECT 1 FROM property_grants g WHERE g.user_id=u.id)""").fetchone()[0]
        admins=con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
    check(no_scope==0,f'Nhân viên đang hoạt động nhưng chưa gán cơ sở: {no_scope}')
    check(admins>=1,'Có ít nhất một Admin đang hoạt động')
print('Kiểm tra xong. Tiếp tục kiểm tra HTTPS, firewall, reverse proxy và phiên làm việc trên trình duyệt.')
sys.exit(0 if all(ok for ok,_ in findings) else 1)
