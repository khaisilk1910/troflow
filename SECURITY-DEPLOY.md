# TrọFlow 5.5 — Kiểm toán và cấu hình bảo mật khi public Internet

## Kết luận

Bản TrọFlow 5.4 **không nên được công khai trực tiếp** bằng cách publish cổng 8088 ra `0.0.0.0`, vì website có hồ sơ CCCD/ảnh, tiền cọc, thu chi và tài khoản ngân hàng. Bản 5.5 đã sửa những vấn đề có thể chứng minh qua mã nguồn, nhưng **không thể cam kết website an toàn tuyệt đối** nếu chưa kiểm tra thực tế Ubuntu, Portainer, reverse proxy, firewall, cấu hình Zalo và quét bảo mật bên ngoài.

**Tốt nhất:** chỉ truy cập qua VPN/Tailscale hoặc lớp danh tính ngoài (Cloudflare Access với MFA). Nếu phải public cho nhân viên, dùng domain và HTTPS, không public cổng web ứng dụng, database, Portainer hay Zalo API.

## Rủi ro tìm thấy, phân loại và biện pháp

| Mức độ | Vấn đề V5.4 | Trạng thái V5.5 |
|---|---|---|
| Cao | Khi DB trống, `/api/auth/setup` có thể tạo Admin từ Internet | `TROFLOW_PUBLIC_MODE=1` khóa route; bootstrap Admin ngoại tuyến bằng terminal |
| Cao | `python-multipart==0.0.20` có các CVE DoS xử lý multipart/form | Nâng lên 0.0.32, quét dependency trong GitHub Actions |
| Cao | Khóa đăng nhập ở RAM, restart mất bộ đếm | Chuyển sang SQLite; chặn theo tài khoản + IP trong 15 phút |
| Cao | Nếu không gán cơ sở, nhân viên mặc định có thể truy cập mọi cơ sở | Internet mode từ chối dữ liệu đến khi Admin gán cơ sở |
| Cao | Ảnh CCCD dùng cùng quyền xem khách thuê | Thêm quyền `tenants.idphotos`, mặc định tắt cho nhân viên |
| Cao | Credential Zalo trước đây lưu plaintext vào file JSON | Mã hóa Fernet với khóa riêng ở `/opt/troflow/secrets/integration.key`; tự chuyển đổi khi được truy cập |
| Trung bình | Upload chỉ kiểm magic header, có thể chứa payload hoặc EXIF GPS | Pillow giải mã/tạo lại; strip metadata, giới hạn pixel và dung lượng |
| Trung bình | Mật khẩu mới dùng PBKDF2, cần tăng kháng tấn công offline | Hash mới Argon2id, các hash PBKDF2 cũ tự chuyển khi login |
| Trung bình | Chưa ràng buộc hostname, header/HTTPS thiếu cài đặt production | TrustedHost allowlist, cookie `Secure`, HSTS, no-referrer, CSP, phòng framing ngoài domain |
| Trung bình | Backend Internet có thể bind công khai, container nhiều quyền ghi | Stack public bind loopback, filesystem read-only, user 10001, cap-drop, hạn tài nguyên |
| Trung bình | Chặn body lớn dựa trên thao tác endpoint, thiếu proxy limit | Caddy `request_body max_size 5MB`; app kiểm tra Content-Length |
| Đã sửa | Route `/api/auth/me` của nhân viên bị mapping quyền chặn nhầm | Miễn kiểm quyền module cho `/api/auth/*` (vẫn yêu cầu session/CSRF nơi cần) |

**Phần cần làm sau**: MFA thực sự ở tầng ứng dụng chưa có; dùng Access/VPN có MFA. Chưa mã hóa toàn bộ DB tại-rest, cần LUKS/full-disk-encryption nếu cần. Chưa thực hiện pentest black-box thực tế; không coi 47 bài test là chứng chỉ an ninh. QR VietQR sử dụng dịch vụ ngoài; thông tin tài khoản, số tiền và nội dung chuyển khoản có thể được gửi cho VietQR. Nội dung CK hiện chứa tên/SĐT khách, cân nhắc giảm PII theo chính sách riêng tư của bạn.

## Trình tự triển khai production an toàn

**Bước 0: Sao lưu dữ liệu.** Tạm tắt webhook tự deploy của Portainer trong lúc chuẩn bị thay đổi cấu hình production, tránh image mới chạy trên Stack cũ còn public port. Trước khi deploy, tắt gửi Zalo tự động để thử nghiệm, tạo bản sao lưu SQLite qua giao diện/shell, đồng thời sao lưu `/opt/troflow/uploads` và cấu hình đang chạy. Không xóa file `/opt/troflow/data/troflow.db`. Kiểm tra khôi phục trên staging. Lưu ý key bí mật mới phải có bản backup riêng, nếu mất key không thể giải mã credential Zalo.

**Bước 1: Cài đặt host.** Trên Ubuntu, giải nén source ZIP vào thư mục tạm (không cần xóa container cũ), rồi chạy:

```sh
sudo sh deploy/prepare-public-host.sh
```

Script tạo thư mục mới và một khóa Fernet 32-byte bằng `os.urandom`, chỉ tạo khi key chưa tồn tại. Key gắn read-only vào container, không nằm trong Git hoặc Docker image. Các thư mục dữ liệu hiện có không bị xóa; kiểm tra quyền ghi UID 10001 trước khi deploy.

**Bước 2: Cấu hình reverse proxy.** Cần một domain thực, ví dụ `tro.example.com`, trỏ DNS về public IP. Nếu Caddy cài trực tiếp trên Ubuntu (không trong Docker), dùng `deploy/Caddyfile.example` và thay domain. Caddy cung cấp HTTPS tự động, redirect HTTP→HTTPS và giới hạn body 5 MB; yêu cầu Caddy v2.10+ cho `request_body`. Nếu đã có Nginx Proxy Manager/Traefik/Caddy trên host, **không cài Caddy thứ hai giành port 80/443**; cấu hình reverse proxy hiện tại tương đương. Dùng IP/domain hợp lệ, tránh dùng IP trần mà không có HTTPS.

**Bước 3: Portainer Stack.** Sau khi image 5.5 build thành công và đã kiểm thử staging, trong Portainer chỉnh Git Compose path thành `deploy/portainer-stack-public.yml`. Environment variables:

```ini
TROFLOW_IMAGE=ghcr.io/khaisilk1910/troflow:latest
TROFLOW_DOMAIN=tro.example.com
PORT=8088
BACKUP_KEEP=14
```

File Stack bắt buộc `TROFLOW_PUBLIC_MODE=1`, `COOKIE_SECURE=1`, bind **127.0.0.1:8088**, khóa mã hóa mount riêng và filesystem read-only. Không đặt `network_mode: host` cho TrọFlow. Các volume vẫn là `/opt/troflow/{data,backups,uploads}`. Khi chuyển sang host binding loopback, các thiết bị trong LAN sẽ **không** truy cập qua `http://IP-SERVER:8088`, mà truy cập HTTPS qua domain. Zalo Bot đang ở host network tiếp tục tải ảnh bằng `http://127.0.0.1:8088` từ chính host.

**Bước 4: Bootstrap Admin lần đầu nếu database hoàn toàn trống:**

```sh
docker exec -it troflow python scripts/bootstrap_admin.py
```

Chỉ làm bước này khi chưa có Admin. Nếu TrọFlow cũ đã có người dùng, không bootstrap nữa. Password ở Internet mode yêu cầu ít nhất 15 ký tự. Sau deploy, phiên cookie cũ có thể mất và người dùng cần đăng nhập lại vì tên cookie cứng hơn.

**Bước 5: Phân quyền nhân viên.** Admin mở Phân quyền và **chọn ít nhất một cơ sở** cho từng tài khoản nhân viên. Không gán cơ sở sẽ nhận 403 ở Internet mode (đây là hành vi cố ý). Quyền **Xem/sửa ảnh CCCD** mặc định tắt; chỉ bật khi thực sự cần cho công việc. Chỉ chủ nhà nên có quyền backup, ngân hàng và Zalo.

**Bước 6: Kiểm tra:**

```sh
docker exec troflow python scripts/security_selfcheck.py
sudo ss -lntp | grep -E ':3000|:8088|:443|:80'
sudo ufw status verbose
curl -I https://tro.example.com/
```

Quan sát `Strict-Transport-Security`, `Content-Security-Policy`, `Referrer-Policy`. Thử đăng nhập hợp lệ qua domain, tải ảnh CCCD với Admin, xác nhận nhân viên thiếu quyền bị 403. Chạy thử Zalo đến **nhóm thử nghiệm**, kiểm tra URL nội bộ bot→TrọFlow. Port 3000 của Zalo Bot chạy host network cần **chặn inbound từ Internet**, nhưng không chặn traffic từ Docker bridge. Giới hạn truy cập giao diện Portainer, SSH bằng VPN/IP allowlist và MFA.

## Vận hành định kỳ

- Bật 2FA tại GitHub và Portainer; tốt hơn bật Identity-aware proxy/Cloudflare Access MFA trước TrọFlow; không dùng lại mật khẩu.
- Dùng GHCR tag SHA cho rollback thay vì chỉ dựa vào `latest`; DB restore phải đúng phiên bản app.
- Dùng backup ngoài máy chủ đã mã hóa và **kiểm tra khôi phục**, bao gồm `/opt/troflow/data`, `/opt/troflow/uploads` và **bản sao key bí mật lưu tách biệt**.
- Cập nhật Ubuntu/Docker/Caddy đều đặn; theo dõi GitHub Dependabot, các cảnh báo CVE và logs. GitHub Actions thêm `pip-audit --strict`; nếu lỗ hổng mới xuất hiện, **không cho phát hành image mới cho đến khi xử lý**.
- Thiết lập UFW/nftables phù hợp mạng Docker; Docker có thể publish port theo đường đi không tuân UFW như kỳ vọng, vì thế kiểm tra từ bên ngoài mạng sau khi thay đổi firewall.
- Trước khi public rộng, thuê pentest ít nhất một vòng: xác thực, phân quyền từng cơ sở, IDOR, XSS, SSRF Zalo, upload, phục hồi backup và mất phiên.

## Phạm vi kiểm thử

Code audit thủ công các module `main`, `advanced`, `notify`, `permissions`, `db`, `utility`, static UI, CI, Dockerfile và Stack. Kiểm thử 47 ca Python (41 cũ + 6 bảo mật) trên temp DB; có các tình huống staff/CCCD, migration mật khẩu, thống kê lỗi login, key Fernet và header. CI còn có các bài kiểm tra JavaScript hiện có.

**Chưa kiểm chứng Docker Engine/Caddy/Portainer/Ubuntu thực, quét cổng ngoài Internet, kiểm tra đa người dùng thực và Zalo gửi tin thật.** Giải pháp giảm rủi ro, không đồng nghĩa hệ thống miễn nhiễm tấn công.
