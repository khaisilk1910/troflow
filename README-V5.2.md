# TrọFlow 5.2 — Zalo Bot Server + Ngân hàng / QR + điện nước trên hóa đơn

Phiên bản mã nguồn dựa trên **TrọFlow 5.1**, schema database **V6**. Dữ liệu của TrọFlow **không chuyển chỗ**: `/opt/troflow/data`, `/opt/troflow/backups`, `/opt/troflow/uploads`. Không phải cài đặt lại hoặc xóa database.

## Những chức năng mới

1. **Thông báo Zalo trong menu Admin**: URL Zalo Bot Server, Zalo accountSelection, mật khẩu truy cập bot, bật/tắt chung, bật/tắt hóa đơn và thanh toán, quản lý người nhận (user/nhóm), gắn người nhận với khách thuê/cơ sở, gửi thủ công, gửi ảnh hóa đơn, nhật ký và gửi lại thủ công khi lỗi.
2. **Tài khoản ngân hàng & QR**: nhiều tài khoản theo cơ sở, thêm/sửa/xóa, bật/tắt, chọn tài khoản mặc định, xem trước QR. Có QR VietQR tự điền số tiền còn phải thanh toán và nội dung riêng cho mỗi hóa đơn.
3. **Chi tiết hóa đơn và bản in A4**: điện/nước có chỉ số cũ → mới, sản lượng sử dụng, tiền thu; phần ngân hàng có tên ngân hàng, chủ tài khoản, số tài khoản, số tiền, nội dung CK và QR. Hai nơi dùng cùng một template.
4. **Migration V6**: tự bổ sung `bank_accounts`, `zalo_config`, `zalo_destinations`, `zalo_outbox`, `notification_media`. Dữ liệu ngân hàng lưu tại cơ sở theo format V2/V5 được import sang bảng ngân hàng mới, trường cũ vẫn giữ.

## Quan trọng: đối chiếu mã nguồn bot được người dùng cung cấp

Bot là dự án `zalo-bot-server-main` dùng `zca-js` (Zalo cá nhân **không chính thức**). Không phải Zalo Official Account API. Cơ chế kết nối **không dùng API token**: TrọFlow đăng nhập `POST /api/login` bằng tài khoản quản trị bot để lấy cookie session; sau đó gọi:

- `POST /api/sendMessageByAccount`: `{message, threadId, type, accountSelection}`
- `POST /api/sendImageByAccount`: `{message, imagePath, threadId, type, accountSelection}`
- `type: 0` = user, `type: 1` = group. `accountSelection`: Zalo **ownId** hoặc **số điện thoại của tài khoản gửi đã đăng nhập bot**, không phải số điện thoại khách thuê.
- `threadId`: Zalo ID của user/nhóm, nhập chuỗi số, không phải số điện thoại.

Bot tải ảnh bằng HTTP GET từ `imagePath`. Vì vậy TrọFlow cấp một URL ẩn danh bằng token ngẫu nhiên **256-bit**, chỉ dùng xem ảnh hóa đơn, hết hạn sau **10 phút**; token không cấp quyền truy cập ảnh CCCD, ảnh phòng hay API khác. TrọFlow **không** phải mở toàn bộ `/api` không xác thực.

## Kết nối hai container trên cùng Ubuntu

Portainer Stack có thêm:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Nếu Zalo Bot Server xuất port `3000` lên Docker host, trong **Admin → Thông báo Zalo**:

| Trường | Giá trị mẫu |
|---|---|
| Bot server URL (TrọFlow → Bot) | `http://host.docker.internal:3000` |
| Account selection | Zalo ownId hoặc SĐT tài khoản bot đã đăng nhập |
| URL nội bộ TroFlow để bot tải ảnh (Bot → TrọFlow) | `http://IP-UBUNTU:8088` hoặc hostname nội bộ **bot truy cập được** |
| Username/password | Tài khoản **quản trị ứng dụng Zalo Bot Server**, không phải tài khoản Zalo cá nhân |

**Hai URL phục vụ hai chiều kết nối riêng biệt.** `host.docker.internal` chỉ hoạt động trong container được cấu hình `extra_hosts`, không mặc định hoạt động trong container bot. Với bot chạy `network_mode: host`, bot có thể tải ảnh từ `http://127.0.0.1:8088`. Nếu bot ở bridge, dùng IP LAN Docker host hoặc thêm `extra_hosts` tương tự vào Stack bot. `media_url` cần là HTTP(S) URL có thể truy cập từ bot, không nhập `/api` vào cuối.

**Bảo mật:** nếu cần truyền username/password qua mạng không tin cậy thì dùng **HTTPS**. Với HTTP, chỉ dùng mạng nội bộ hoặc liên kết cùng host được bảo vệ. Bot là phần mềm dùng API cá nhân không chính thức, khả năng gửi tin có thể ngừng hoạt động khi Zalo cập nhật; TrọFlow không đảm bảo gửi thành công trong mọi điều kiện. Không gửi tin đến người chưa đồng ý nhận thông báo.

### Bật thông báo có kiểm soát

Mặc định **tắt toàn bộ** sau khi nâng cấp. Làm theo thứ tự:

1. Kiểm tra trang quản trị Zalo Bot Server đã đăng nhập tài khoản Zalo và có thể gửi tin thử.
2. Mở **Thông báo Zalo**, nhập 2 URL kết nối, accountSelection và tài khoản đăng nhập bot; lưu.
3. Tạo nơi nhận `user` hoặc `group`, chọn khách thuê/cơ sở tương ứng, bật loại thông báo muốn nhận. Khách thuê liên kết giúp lọc hóa đơn tự động; nhóm có thể nhận mọi hóa đơn của cơ sở nếu không gắn một khách riêng.
4. Bật kênh gửi thông báo. Bật riêng thông báo hóa đơn và/hoặc thông báo thu tiền. Thử gửi một tin thủ công trước.
5. Sau khi kiểm tra thực tế mới bật gửi thông báo tự động cho người nhận thật.

Thông báo khi **phát hành/chốt hóa đơn**: kèm ảnh hóa đơn PNG có QR nếu cấu hình ngân hàng và còn công nợ. Thông báo khi **ghi nhận thanh toán**: thông báo tổng đã thu và số dư mới, không tự gửi ảnh. Trang Admin có thể gửi ảnh thủ công. Mỗi sự kiện tự động có khóa chống gửi trùng. Thất bại được ghi vào nhật ký, chỉ gửi lại **theo yêu cầu Admin**, tránh spam và gửi trùng khi bot lỗi mạng. Nếu tiến trình gián đoạn trong khi gửi, thông báo bị đánh dấu cần đối chiếu thay vì tự gửi lại.

Mật khẩu bot nhập trên web Admin được lưu bằng file 0600 tại `/opt/troflow/data/zalo-integration-credentials.json`. Không trả mật khẩu qua API. Có thể dùng biến môi trường `ZALO_BOT_USERNAME`/`ZALO_BOT_PASSWORD` trên Portainer thay thế; **biến môi trường sẽ được ưu tiên**. Vì chứa mật khẩu, cần bảo vệ file dữ liệu này và không commit vào Git.

## Quản lý ngân hàng

Vào **Tài khoản ngân hàng & QR** trong menu chính Admin. Điền tên cơ sở, mã ngân hàng/BIN dùng VietQR, tên ngân hàng, số tài khoản, chủ tài khoản. Tài khoản được đánh dấu mặc định và đang bật sẽ xuất hiện trên hóa đơn của **đúng cơ sở**. Nhiều tài khoản một cơ sở được hỗ trợ; chỉ một tài khoản được ưu tiên mặc định. Nút xem QR để xem QR tài khoản chưa điền tiền; còn QR trên hóa đơn **có sẵn tiền và nội dung riêng**. Ảnh QR phụ thuộc dịch vụ `img.vietqr.io`; browser/máy chủ cần mạng đến dịch vụ này.

VietQR chỉ **khởi tạo yêu cầu chuyển khoản**, không xác thực đã nhận tiền. Giao dịch cần được ghi nhận trên TrọFlow sau khi đối chiếu ngân hàng.

## Triển khai Portainer / GitHub

1. Sao lưu trước khi nâng cấp: `/opt/troflow/data/troflow.db` và `/opt/troflow/uploads`, tốt nhất sử dụng chức năng backup nhất quán của TrọFlow.
2. Deploy phiên bản mới trước với bản sao database trong Stack staging. Migration schema lên V6 được tự động thực hiện khi app khởi động, sau khi tạo bản backup vào `/opt/troflow/backups/migrations/`.
3. Git CMD: copy source từ ZIP vào repo `https://github.com/khaisilk1910/troflow` (giữ `.git`), rồi chạy:

```bash
git add -A
git commit -m "Upgrade TroFlow 5.2 Zalo notifications and invoice QR"
git push origin main
```

4. GitHub Actions thực thi Python tests + JS tests rồi build `ghcr.io/khaisilk1910/troflow:latest`. Portainer có thể tự redeploy qua webhook, cấu hình Re-pull image / Force redeployment. Stack vẫn dùng `PORT=8088` (host) → `8000` (container) và `/opt/troflow/...` bind mounts.
5. Trong trình duyệt tải lại bằng Ctrl+F5. Kiểm tra menu mới, thêm bank, mở hóa đơn, in bản A4, rồi thử gửi Zalo user và nhóm thật trước khi bật thông báo tự động.

## Kiểm thử

`python -m unittest discover -s tests -q`: 31 bài kiểm thử (gồm migration, ngân hàng, chống duplicate, outbox, quyền Admin, mock session login và send Zalo endpoints). `node tests/test_invoice_print.js`, `node tests/js_smoke.js`, `node --check app/static/integrations.js` đều đạt.

Chưa chạy build Docker thực tế / chưa gửi tin qua phiên Zalo thật trong môi trường bàn giao. Chromium không truy cập localhost do chính sách môi trường, vì vậy chưa xác nhận tương tác thủ công toàn bộ web trên trình duyệt thật. Cần thử trên staging/Portainer trước production.
