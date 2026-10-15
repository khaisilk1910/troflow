# TrọFlow 5.4 — Nâng cấp nội dung hóa đơn, PNG và Zalo

Bản này nâng cấp trực tiếp từ TrọFlow 5.3. Không thêm/sửa bảng database nên **không cần migration**. Dữ liệu bind-mount `/opt/troflow/data`, `/opt/troflow/backups`, `/opt/troflow/uploads` giữ nguyên. Portainer và GitHub Actions vẫn dùng image `ghcr.io/khaisilk1910/troflow:latest` và port ngoài `${PORT:-8088}`.

## Chức năng

1. Nội dung CK VietQR lấy **tên khách thuê viết hoa không dấu**, mã phòng và số điện thoại, tiếp theo là mã hóa đơn và kỳ theo định dạng `TRANG-P01-0982986102 HD00002 202610`. Xử lý tại `app/invoice_format.py` và dùng chung cho `GET /api/v6/invoices/{id}/payment-qr` cùng API VietQR V2 cũ. Khoản cần chuyển vẫn là **dư nợ của hóa đơn**, không phải tổng trước thanh toán.
2. Cửa sổ hóa đơn và bản in hiển thị **chỉ số cũ → mới, số tiêu thụ, đơn giá điện/nước**, in đậm chỉ số và tiêu thụ. Đơn giá đọc theo bản ghi `invoice_lines` đã lưu khi lập hóa đơn; với hóa đơn cũ không có snapshot sẽ ghi `Đơn giá quy đổi` để không ngộ nhận đó là giá niêm yết lịch sử.
3. **Phí dịch vụ** chia theo từng dòng dịch vụ được ghi ở thời điểm lập hóa đơn. Nếu hóa đơn cũ không có chi tiết hoặc tổng các dòng không khớp tổng phí thì hiển thị một dòng phí dịch vụ để tránh tính nhầm.
4. Đổi **Số dư cần thanh toán → Tổng tiền phải thanh toán**, bỏ hạn thu, trạng thái Chưa thanh toán chuyển đỏ trong hóa đơn/bản in.
5. Thêm nút **Lưu ảnh PNG**; tải file từ API có kiểm tra đăng nhập, quyền `invoices.view` và phạm vi cơ sở.
6. Xuất PDF nội bộ từ **cùng một mẫu PNG** để đồng nhất nội dung và QR. Với hóa đơn dài, PDF được phân trang A4. Bản PDF này là ảnh raster, không chọn/copy riêng văn bản được; lệnh in từ trình duyệt vẫn dùng HTML như trước.
7. Zalo: thông báo phát hành hóa đơn và thanh toán đính kèm **ảnh hóa đơn** qua link có token 10 phút. Ảnh đính kèm có cùng nội dung với ảnh tải PNG, chụp cả QR khi VietQR trả ảnh thành công. Gửi thủ công khi chọn hóa đơn + bật `Gửi kèm ảnh` tiếp tục hoạt động.

## Triển khai

### Sao lưu trên Ubuntu trước khi cập nhật

Dùng chức năng Sao lưu trong TrọFlow hoặc:

```bash
docker exec troflow python /app/scripts/backup_sqlite.py
```

Sao lưu cả `/opt/troflow/uploads` nếu có ảnh thật.

### Push từ Windows Git CMD

Chép **nội dung** thư mục `troflow` trong ZIP vào repository clone `https://github.com/khaisilk1910/troflow` (giữ thư mục `.git`). Sau đó:

```bat
git add -A
git commit -m "TroFlow 5.4 - Invoice details PNG and Zalo"
git push origin main
```

GitHub Actions chạy unittest và Node tests, sau đó build image GHCR. Nếu Portainer GitOps webhook được cấu hình, Stack có thể tự cập nhật.

### Kiểm tra sau triển khai

1. Mở hóa đơn đã phát hành từ trước: kiểm tra tên/phòng/điện thoại, chỉ số, đơn giá và phí.
2. Kiểm tra nội dung CK trong QR VietQR và chuyển khoản thử số tiền nhỏ sau khi xác minh người nhận.
3. Nhấn **Lưu ảnh PNG**; xác nhận file là ảnh hợp lệ. Nhấn **In hóa đơn**, xem trước PDF A4.
4. Trong **Thông báo Zalo**, gửi thử một hóa đơn vào user/nhóm **thử nghiệm** (đảm bảo URL nội bộ TrọFlow trong cấu hình Zalo Bot truy cập được). Kiểm tra outbox thành công/thất bại.
5. Kiểm tra nhân viên chưa có quyền xem hóa đơn không thể tải PNG theo URL trực tiếp.

**Hạn chế kết nối:** QR được tải từ `img.vietqr.io` khi render PNG/PDF ở phía server. Nếu VietQR không truy cập được, ảnh vẫn hiển thị ngân hàng/tên chủ tài khoản/số tài khoản/nội dung và cảnh báo không tải được QR. Khi gửi tự động Zalo cần cấu hình đúng bot/session/API, URL TroFlow cho bot đọc và Internet để lấy QR. **Không tự động đối soát giao dịch ngân hàng**.

**Không được coi là đã deploy:** Bộ mã đã chạy kiểm thử unit/integration cục bộ, nhưng chưa thể xác nhận gửi Zalo thật, quét QR ngân hàng thật hoặc chạy `docker build`/Portainer trên máy chủ của bạn. Nên thử trên Stack staging dùng bản sao dữ liệu trước khi production.
