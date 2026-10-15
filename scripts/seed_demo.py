"""Optional demo data. Run ONLY after creating initial admin, on an empty system.

    docker compose exec troflow python scripts/seed_demo.py

The script refuses to run when any properties already exist.
"""
from datetime import date, timedelta
from calendar import monthrange
from app.db import init_db, tx, one


def add(con, table, **fields):
    cols=list(fields)
    sql=f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
    return con.execute(sql,tuple(fields.values())).lastrowid


def month_delta(y,m,delta):
    start=y*12+m-1+delta
    return divmod(start,12)[0], divmod(start,12)[1]+1


def main():
    init_db()
    now=date.today()
    with tx() as con:
        if not one(con,'SELECT id FROM users LIMIT 1'):
            raise SystemExit('Tạo tài khoản quản trị trên giao diện trước khi nạp dữ liệu mẫu.')
        if one(con,'SELECT id FROM properties LIMIT 1'):
            raise SystemExit('Hệ thống đã có cơ sở. Không nạp dữ liệu mẫu để tránh trộn với dữ liệu thật.')
        properties=[
            add(con,'properties',name='An Nhiên Residence',address='24 Nguyễn Văn Cừ, Quận 5, TP.HCM',manager_phone='0909000001',electric_rate=3500,water_rate=20000,service_fee=120000),
            add(con,'properties',name='The Nest Apartments',address='56 Phan Xích Long, Phú Nhuận, TP.HCM',manager_phone='0909000002',electric_rate=3800,water_rate=22000,service_fee=150000),
        ]
        rooms=[]
        for ix,pid in enumerate(properties):
            for j in range(1,10):
                r=add(con,'rooms',property_id=pid,code=f'{ix+1}{((j-1)//3)+1}0{((j-1)%3)+1}',floor=f'Tầng {((j-1)//3)+1}',
                      area=22+(j%4)*4,rent=2900000+ix*500000+j*130000,deposit=3000000+ix*500000,
                      condition='maintenance' if j==9 and ix==1 else 'ready',notes='Dữ liệu minh họa')
                rooms.append((r,pid,ix,j))
        names=['Nguyễn Thu Hà','Lê Minh Khôi','Trần Bảo Anh','Phạm Đức Nam','Hoàng Thị Linh','Võ Thành Long',
               'Đặng Quỳnh Chi','Bùi Hoàng Phúc','Đỗ Mỹ Duyên','Mai Huy Hoàng','Nguyễn Ngọc Hân']
        selected=rooms[:7]+rooms[9:13]
        contracts=[]
        start=f'{now.year-1}-01-01'
        end=f'{now.year+1}-12-31'
        for k,((rid,pid,ix,j),name) in enumerate(zip(selected,names)):
            tenant=add(con,'tenants',full_name=name,phone=f'0901200{k:03d}',email='',id_number='',hometown='TP. Hồ Chí Minh',notes='Hồ sơ mẫu')
            end_date=(now+timedelta(days=16)).isoformat() if k==2 else end
            contract=add(con,'contracts',room_id=rid,tenant_id=tenant,start_date=start,end_date=end_date,
                         monthly_rent=2900000+ix*500000+j*130000,deposit=3000000,due_day=5,
                         occupants=1+(k%2),status='active',notes='Hợp đồng mẫu')
            contracts.append((contract,rid,pid,ix,k))
        previous_readings={}
        for months_ago in range(5,-1,-1):
            y,m=month_delta(now.year,now.month,-months_ago)
            period=f'{y:04d}-{m:02d}'
            due_y,due_m=month_delta(y,m,1)
            for cid,rid,pid,ix,k in contracts:
                p=one(con,'SELECT * FROM properties WHERE id=?',(pid,))
                c=one(con,'SELECT * FROM contracts WHERE id=?',(cid,))
                base_e,base_w=previous_readings.get(rid,(100+k*23,11+k*4))
                usage_e=35+(k%5)*8+months_ago%3
                usage_w=3+(k%4)
                previous_readings[rid]=(base_e+usage_e,base_w+usage_w)
                add(con,'readings',room_id=rid,period=period,electric_old=base_e,electric_new=base_e+usage_e,
                    water_old=base_w,water_new=base_w+usage_w)
                electricity=usage_e*p['electric_rate'];water=usage_w*p['water_rate']
                total=c['monthly_rent']+electricity+water+p['service_fee']
                invoice=add(con,'invoices',contract_id=cid,room_id=rid,period=period,
                            due_date=f'{due_y:04d}-{due_m:02d}-05',rent=c['monthly_rent'],electricity=electricity,
                            water=water,services=p['service_fee'],adjustment=0,electric_usage=usage_e,water_usage=usage_w,
                            total=total,note='Hóa đơn mẫu')
                # Two current-month balances unpaid, one half paid, all historical payments recorded.
                if months_ago==0 and k in (1,3):
                    continue
                payment=total//2 if months_ago==0 and k==5 else total
                day=min(now.day,15) if months_ago==0 else min(8,monthrange(y,m)[1])
                add(con,'payments',invoice_id=invoice,amount=payment,method='transfer' if k%3 else 'cash',
                    paid_at=f'{y:04d}-{m:02d}-{day:02d}',note='Thanh toán mẫu')
        expense_categories=['repair','utilities','supplies','operations','salary']
        for delta in range(6):
            y,m=month_delta(now.year,now.month,-delta)
            for ix,pid in enumerate(properties):
                add(con,'expenses',property_id=pid,category=expense_categories[(ix+delta)%len(expense_categories)],
                    amount=440000+ix*130000+delta*55000,spent_on=f'{y:04d}-{m:02d}-08',
                    description='Chi phí vận hành mẫu')
        add(con,'tickets',room_id=rooms[1][0],title='Điều hòa làm lạnh yếu',category='furniture',priority='high',status='new',
            description='Khách báo cần kiểm tra gas và vệ sinh dàn lạnh.',reported_at=now.isoformat())
        add(con,'tickets',room_id=rooms[3][0],title='Vòi nước phòng tắm bị rò',category='water',priority='medium',status='in_progress',
            description='Đã liên hệ thợ, dự kiến xử lý trong ngày.',reported_at=now.isoformat())
        add(con,'tickets',room_id=rooms[8][0],title='Thay đèn hành lang',category='electric',priority='low',status='done',
            resolved_at=now.isoformat(),description='Đã thay bóng LED.',reported_at=(now-timedelta(days=2)).isoformat())
    print('Đã tạo dữ liệu minh họa: 2 cơ sở, 18 phòng, 11 hợp đồng, 6 tháng hóa đơn.')

if __name__=='__main__': main()
