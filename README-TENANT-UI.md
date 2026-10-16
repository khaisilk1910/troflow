# TrọFlow V5.7 — Cải tiến cổng khách thuê (UI / menu / trả trước)

## Tính năng

- Cổng `/tenant` sau đăng nhập có 7 mục điều hướng: **Tổng quan**, **Phòng đang thuê**, **Hóa đơn**, **Tiền thuê trả trước**, **Điện & nước**, **Yêu cầu sửa chữa**, **Liên hệ chủ nhà**. Mỗi lần chỉ hiển thị một mục. Điện thoại có menu cuộn ngang, máy tính có thanh menu bên trái.
- Phòng đang thuê: hiển thị tiền phòng, đơn giá điện (**đ/kWh**), đơn giá nước (**đ/m³**), phí dịch vụ (**đ/tháng**, hoặc "Không thu" nếu bằng 0), kỳ hợp đồng, ngày đến hạn, tiền cọc. Đây là **đơn giá hiện tại** lấy từ bảng `properties`, không phải đơn giá lịch sử của từng hóa đơn.
- Tiền thuê trả trước: hiển thị tổng đã nhận, **ngày nhận tiền**, phương thức thanh toán, từ tháng nào đến tháng nào, số tiền **từng tháng**, và khoản **đã hoàn** nếu có. Tổng "chưa hoàn" là tổng các kỳ có trạng thái `active`, **bao gồm kỳ tháng đã qua**; không được hiểu là toàn bộ số tiền chưa sử dụng. Tổng "từ tháng hiện tại trở đi" chỉ cộng các kỳ `active` từ tháng hiện tại.
- Hóa đơn có chi tiết tiền thuê, điện, nước, dịch vụ, khoản điều chỉnh, đã trả, còn phải trả. Gửi chỉ số và yêu cầu sửa chữa giữ nguyên API, phân quyền và quy trình xác nhận của phiên bản gốc.
- `GET /api/tenant/home` bổ sung thuộc tính `electric_rate`, `water_rate`, `service_fee`, `deposit`, `due_day` trong `contracts`, và mảng `prepayments` (phân nhóm theo đợt thu). Dữ liệu trả trước chỉ được truy vấn trong danh sách hợp đồng của đúng khách thuê và đúng cơ sở đã đăng nhập.

## Các file được cập nhật

- `app/tenant_portal.py` — trả đơn giá và các đợt thu tiền thuê trả trước.
- `app/static/tenant.js` — menu và toàn bộ giao diện khách thuê.
- `app/static/tenant.css` — phong cách giao diện mới, tương thích điện thoại.
- `app/static/tenant.html` — bố cục gốc, cập nhật phiên bản tệp tĩnh để làm mới cache.
- `tests/test_tenant_portal_v7.py` — thêm kiểm thử đơn giá, tiền trả trước, hoàn tiền, và phạm vi tài khoản khách thuê.

**Không cần tạo bảng hoặc chạy migration mới**: các bảng `rent_coverage` và `rent_prepayment_batches`, các cột đơn giá đã có trong TrọFlow V5.7. Thay đổi này không sửa dữ liệu cũ, cấu hình tài khoản quản trị, Cloudflare Tunnel hay chế độ bảo vệ truy cập Internet.

## Cập nhật bản đang dùng với GitHub Actions + Portainer

1. Sao lưu database đang chạy bằng cơ chế backup hiện có trước khi nâng cấp.
2. Trong repository cùng phiên bản nguồn đã gửi, thay đúng **5 file được cập nhật** nói trên. Nếu repo đã chỉnh sửa những file đó về sau, hãy xem diff và hợp nhất trước khi chép đè. Có thể dùng gói `TroFlow_Tenant_UI_Patch.zip` để thay đúng đường dẫn.
3. Commit và push lên nhánh `main`. Chờ GitHub Actions chạy kiểm thử và publish image thành công.
4. Nếu Portainer chưa tự cập nhật qua webhook, chạy **Pull and redeploy** cho Stack đang dùng với image mới. Giữ nguyên volume `/opt/troflow/data`, `/opt/troflow/uploads`, `/opt/troflow/backups` và `/opt/troflow/secrets`.
5. Mở `/tenant`, đăng nhập tài khoản khách thuê, kiểm tra đơn giá trong **Phòng đang thuê** và các đợt đóng trước trong **Tiền thuê trả trước**.

Không chép file `.db`, không thay đổi stack YAML, và không cần đặt `TROFLOW_PUBLIC_MODE=0` để bật giao diện mới.

## Kiểm thử

```bash
python -m unittest tests.test_tenant_portal_v7 -v
node --check app/static/tenant.js
node tests/test_tenant_ui.js
```
