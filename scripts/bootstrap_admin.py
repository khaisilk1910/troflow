#!/usr/bin/env python3
"""One-time offline administrator bootstrap for Internet-facing installations.
Run interactively inside the container: docker exec -it troflow python scripts/bootstrap_admin.py
"""
import getpass
import re
import sqlite3
from app.db import init_db,tx
from app.main import password_hash,strong_password,audit


def main():
    init_db()
    print('Tạo quản trị viên TrọFlow lần đầu; chỉ thực hiện trên server.')
    username=input('Tên đăng nhập (3-40 ký tự): ').strip()
    fullname=input('Họ tên quản trị viên: ').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',username) or not 1<=len(fullname)<=120:
        raise SystemExit('Tên đăng nhập hoặc họ tên không hợp lệ.')
    password=getpass.getpass('Mật khẩu mạnh (>= 15 ký tự ở chế độ Internet): ')
    confirm=getpass.getpass('Xác nhận mật khẩu: ')
    if password!=confirm:raise SystemExit('Mật khẩu xác nhận không khớp.')
    strong_password(password)
    with tx() as con:
        if con.execute('SELECT id FROM users LIMIT 1').fetchone():
            raise SystemExit('Đã tồn tại tài khoản. Dừng khởi tạo, không ghi đè dữ liệu.')
        try:
            cur=con.execute('INSERT INTO users(username,full_name,password_hash,role) VALUES (?,?,?,?)',
                            (username,fullname,password_hash(password),'admin'))
            audit(con,{'id':cur.lastrowid},'bootstrap','user',cur.lastrowid,'Khởi tạo qua terminal')
        except sqlite3.IntegrityError as exc:
            raise SystemExit('Không tạo được tài khoản: '+str(exc)) from exc
    print('Đã tạo quản trị viên thành công. Đăng nhập bằng HTTPS.')


if __name__=='__main__':main()
