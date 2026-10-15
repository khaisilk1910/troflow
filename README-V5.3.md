# TrọFlow 5.3 — Tự chọn ngân hàng, tự điền mã BIN VietQR

## Nguồn dữ liệu

- Nguồn chính thức của nhà cung cấp API VietQR Payment Kit (Casso): https://www.vietqr.io/api-bank
- Endpoint dữ liệu: `GET https://api.vietqr.io/v2/banks`
- Danh sách tại thời điểm đóng gói **2026-10-15** có **75 ngân hàng / tổ chức / ví được VietQR liệt kê**. Không phải 75 ngân hàng truyền thống.
- Dữ liệu dự phòng được đóng sẵn trong `app/vietqr_banks.json` và kiểm tra toàn vẹn tại `app/bank_catalog.py`.
- Tài liệu nhà cung cấp khuyến nghị làm mới danh sách hằng ngày vì BIN/tên/mức hỗ trợ có thể thay đổi. Quản trị viên có thể nhấn nút **Cập nhật danh sách VietQR** khi cần; dữ liệu mới được lưu trong `/opt/troflow/data/vietqr-banks-cache.json`.

## Cách sử dụng

1. Vào **Tài chính → Tài khoản ngân hàng & QR → Thêm tài khoản**.
2. Gõ tên/mã ở ô **Tìm kiếm ngân hàng**; hỗ trợ tên có/không dấu, tên viết tắt và BIN.
3. Chọn ngân hàng trong **Ngân hàng / mã BIN VietQR**. BIN và tên được tự điền, không cho sửa trực tiếp khi đã chọn danh mục chuẩn.
4. Nhập chính xác tên chủ tài khoản và số tài khoản thực tế; lưu, sau đó **Xem QR** và quét kiểm tra trước khi gửi hóa đơn cho khách.
5. Nếu ngân hàng nằm ngoài danh sách, chọn **Khác / nhập BIN thủ công** và nhập tên/BIN chính xác theo nhà cung cấp.
6. Nếu gặp lỗi mạng khi nhấn **Cập nhật danh sách VietQR**, danh sách tích hợp sẵn vẫn hoạt động bình thường.

Lưu ý: `transferSupported` trong API phản ánh khả năng *ứng dụng ngân hàng hỗ trợ chuyển tiền bằng quét mã*, không phải bảo đảm từng tài khoản ngân hàng có thể nhận tiền. QR không chứng minh giao dịch đã thanh toán. Xác nhận tên người nhận trong ứng dụng ngân hàng trước khi giao dịch.

## Các endpoint mới (quản trị viên)

- `GET /api/v6/bank-catalog` — lấy danh mục tích hợp sẵn hoặc bản đã cập nhật.
- `POST /api/v6/bank-catalog/refresh` — lấy danh mục mới từ VietQR qua HTTPS, giới hạn phản hồi và kiểm tra schema; nếu thất bại trả mã 502 và giữ danh mục trước đó.

Dữ liệu của các tài khoản đã lưu trong bảng `bank_accounts` không bị xóa. API tạo/sửa tài khoản vẫn hỗ trợ mã cũ nhập thủ công; khi có `catalog_bin`, API kiểm tra khớp BIN và chuẩn hóa tên theo danh mục đáng tin cậy.

## Triển khai và cập nhật

**Không có thay đổi database schema**. Đường dẫn bind mount `/opt/troflow/data`, `/opt/troflow/backups`, `/opt/troflow/uploads` không thay đổi; Stack, Portainer webhook và GitHub Actions vẫn hoạt động. Gói ZIP chứa toàn bộ mã nguồn và `deploy/portainer-stack.yml`, bạn có thể chép toàn bộ nội dung thư mục `troflow/` vào repository hiện tại (giữ `.git`), sau đó:

```bash
git add -A
git commit -m "TrọFlow 5.3 - VietQR bank picker"
git push origin main
```

Kiểm thử:

```bash
python -m pip install -r requirements.txt httpx
python -m unittest discover -s tests -v
node tests/test_bank_catalog.js
node tests/js_smoke.js
node tests/test_invoice_print.js
```

Đây là kiểm thử mã nguồn/API và giao diện chọn ngân hàng bằng Chromium mô phỏng, không phải kiểm tra giao dịch chuyển khoản ngân hàng thực tế. Sau khi deploy, kiểm tra lại QR với tài khoản thật của bạn trước khi gửi cho khách.
