# TroFlow V5.7 - Kiem tra ket noi Zalo Bot & xac nhan noi nhan

Ban cap nhat nay giu nguyen database, cac bang Zalo hien tai, du lieu khach thue va he thong thong bao hoa don/sua chua.

## Giao dien

- `Luu & kiem tra`: luu cau hinh, dong thoi xac thuc qua `POST /api/login` tren Bot Server tu chinh container TroFlow.
- `Kiem tra ket noi`: kiem tra lai ma khong can luu / nhap lai mat khau.
- Phan biet: da ket noi / sai thong tin bot / khong truy cap duoc IP va cong bot / bot tra loi loi / thieu mat khau.
- Trang thai **Da ket noi** chi khang dinh TroFlow da dang nhap thanh cong vao **Zalo Bot Server**. Muon xac nhan tai khoan Zalo va threadId gui duoc thi thu gui tin nhan.
- Tao moi noi nhan **dang bat** se tao mot tin nhan xac nhan va gui ngay sau khi database commit. Khong gui lai khi sua thong tin noi nhan. Noi nhan/tinh trang gui co the xem o danh sach va Nhat ky.
- Neu bot dang tat thi noi nhan van luu, tin nhan xac nhan hien `Gui that bai` kem ly do; sau khi bat bot, co the bam `Gui lai` trong Nhat ky thong bao.
- Neu noi nhan duoc tao o trang thai tat thi khong gui xac nhan.

## Kiểm tra mạng Docker với Bot Server

Cau hinh trong UI, bot_url VD: `http://192.168.31.100:3000` hoac `http://host.docker.internal:3000` (yeu cau `extra_hosts` co `host.docker.internal:host-gateway`). Phai la dia chi **TroFlow container** truy cap duoc, khong phai chi dien thoai truy cap duoc.

Tren may Ubuntu chay Docker:

```sh
sudo ss -lntp | grep ':3000'
docker exec troflow python -c "import socket; s=socket.create_connection(('192.168.31.100',3000),3); print('Bot port reachable'); s.close()"
```

Neu ket noi that bai, kiem tra container Bot Server, IP/port, firewall, Docker bridge network va dia chi bind cua Bot Server. Bot chi lang nghe `127.0.0.1:3000` tren Ubuntu khong mac nhien truy cap duoc tu Docker bridge.

Neu trang TroFlow bao `Failed to fetch`, loi xay ra giua trinh duyet va TroFlow API (hoac khong nhan duoc phan hoi); khong the quy do thanh Bot Server. Kiem tra lai URL truy cap LAN/Cloudflare Tunnel, proxy va Console/Network trong trinh duyet. Sau ban cap nhat, giao dien Zalo se hien thong bao mang de hieu hon.

## API (chi admin)

- `GET /api/v6/zalo/connection`: kiem tra truc tiep server -> Bot Server; chi tra ve status, message, checked_at, connected; khong tra mat khau.
- `PUT /api/v6/zalo/settings`: tra ve `connection` sau khi luu, bat ke ket qua ket noi. Neu khong lien lac duoc bot, cau hinh van duoc luu.
- `POST /api/v6/zalo/destinations`: tra ve `welcome_notification_id`, `welcome_status`. Mot tin nhan xac nhan se duoc gui nen sau khi luu.
- `GET /api/v6/zalo/outbox/{id}/status`: tra ve trang thai/gui loi cua thong bao.

## Cap nhat

Sao luu `/opt/troflow/data`, `/opt/troflow/uploads` va khoa `/opt/troflow/secrets/integration.key` truoc khi cap nhat. Khong xoa database, khong can migration cho tinh nang nay. Ban PATCH chi chua nhung tep thay doi; ban FULL SOURCE la repo day du duoc chinh sua tu TroFlow V5.7 Tenant Portal.

Sau khi push len GitHub, cho CI build image va Portainer pull/redeploy image moi. Neu dung tag `latest`, bao dam image moi da duoc pull thay vi chi restart container cu. Trong browser nen hard refresh de nhan `integrations.js?v=58`.

## Bao mat

Zalo Bot Server duoc goi tu backend voi credentials luu tren may chu, khong dua username/password bot sang ben dich gui qua browser va khong ghi log mat khau. API chay trong pham vi admin. Zalo Bot giao tiep API ca nhan khong chinh thuc; can co su dong y cua nguoi nhan.
