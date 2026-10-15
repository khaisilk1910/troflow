# TrọFlow 3.0 — Phân quyền chi tiết, điện nước theo năm, tiền thuê trả trước

**Repository:** https://github.com/khaisilk1910/troflow  
**Image:** `ghcr.io/khaisilk1910/troflow:latest`  
**Trang cơ bản:** `/` · **Trang nâng cao:** `/advanced`  
**Dữ liệu bất biến trên Docker host:** `/opt/troflow/data`, `/opt/troflow/backups`, `/opt/troflow/uploads`.

## 1. Các thay đổi đã triển khai

### Phân quyền chi tiết từng người dùng

- Vào **TrọFlow Nâng cao → Phân quyền → Phân quyền** của một tài khoản nhân viên.
- Chọn vai trò mẫu: **Quản lý, Kế toán, Thu tiền, Bảo trì, Chỉ xem**, hoặc chỉnh lại từng ô.
- **79 quyền** trong **25 nhóm**: xem, thêm, sửa, xóa, ghi nhận, duyệt/chốt, nhập Excel, ghi điện nước, in PDF, hoàn tiền trả trước, vận hành lịch, v.v.
- Có tìm kiếm quyền, chọn/bỏ chọn hàng loạt và giới hạn phạm vi theo cơ sở.
- **API kiểm tra quyền ở máy chủ**; bỏ chọn quyền sẽ không thể gọi API tương ứng, kể cả khi tự gửi HTTP request.
- Các quyền quản trị tài khoản, phân quyền, sao lưu/khôi phục, ngân hàng, nhật ký và thêm/xóa cơ sở giữ riêng cho Admin. Không cấp được cho staff.
- Để duy trì tương thích, các tài khoản nhân viên V2 chưa tùy biến quyền vẫn được cấp quyền mặc định của vai trò V2. Đổi quyền sẽ vô hiệu hóa phiên đăng nhập trước đó của nhân viên.
- Khi phân quyền theo một/một số cơ sở, nhân viên chỉ được xem/thao tác các cơ sở đó; chọn **Tất cả cơ sở** cho phép áp dụng phạm vi không giới hạn.

### Điện & nước

- Danh sách tại `/` → **Chỉ số điện nước** có bộ lọc **Cả năm YYYY** (thay cho lựa chọn 1 tháng). Lọc cơ sở và tìm theo người thuê vẫn sử dụng được.
- Danh sách hiển thị **tên người thuê** gắn với chỉ số theo kỳ; nếu hợp đồng cũ đã kết thúc, vẫn tra lại được người thuê của kỳ lịch sử.
- Form **Ghi chỉ số** hiển thị **Phòng — Tên người thuê**, tự đồng bộ theo **tháng nhập chỉ số**; không hiển thị phòng trống trong kỳ được chọn.
- API từ chối tạo/sửa chỉ số cho phòng **không có hợp đồng giao với kỳ**. API nhập Excel và nhập hàng loạt cũng có cùng điều kiện.
- **Ghi chú:** kỳ nhập chỉ số **vẫn theo tháng**, vì hóa đơn điện nước luôn tính theo từng tháng; chỉ phần lọc và thống kê được mở rộng sang cả năm.

### Trả tiền thuê trước 1, 3, 6, 12 tháng hoặc tự chọn

- Vào `/advanced` → **Thuê trả trước** → **Thu trước tiền phòng**.
- Chọn hợp đồng (hiển thị tên người thuê, cơ sở và phòng), tháng bắt đầu, **thanh toán nhanh 1/3/6/12 tháng** hoặc kỳ kết thúc tự chọn, ngày nhận tiền, hình thức và ghi chú.
- Server tính tiền thuê đúng theo giá thuê của hợp đồng và **cách tính theo ngày** (nếu hợp đồng bật chia ngày). Giao dịch phải nằm trong hiệu lực hợp đồng.
- Sổ thu tiền thuê trả trước có chứng từ theo từng tháng, thời điểm nhận tiền, người thuê và trạng thái đã thu/đã hoàn.
- Không cho trả trước **trùng một tháng**, hoặc cho tháng đã có hóa đơn (kể cả hóa đơn nháp); không cho sửa giá hoặc đổi cách tính ngày khi còn kỳ trả trước chưa hoàn.
- Khi lập hóa đơn một tháng **đã được trả trước**, công thức là:

  **Tiền phòng còn thu = Tiền thuê theo hợp đồng trong kỳ − Tiền phòng đã thu trước trong kỳ.**

  Nếu đủ tiền thuê trước thì **tiền phòng trên hóa đơn = 0**, còn **điện, nước, phí dịch vụ định kỳ và điều chỉnh phát sinh** vẫn tính bình thường theo tháng. Hóa đơn có dòng trừ tiền đã nộp trước, giúp đối chiếu kế toán.
- **Không ghi nhận tiền trả trước lần hai khi lập hóa đơn.** Số đã trả trước được tính là **tiền mặt/chuyển khoản thực nhận trong ngày thu**, tách khỏi thanh toán hóa đơn tháng.
- Có thể hoàn một **tháng chưa có hóa đơn**; có lịch sử hoàn và dòng tiền âm tương ứng. **Không hỗ trợ hủy một kỳ đã có hóa đơn**, cần đối soát hợp lệ trước thay vì sửa/xóa âm thầm.
- Khi trả phòng còn kỳ thuê đã nộp trước chưa sử dụng, hệ thống yêu cầu hoàn hoặc xử lý khoản đó trước khi kết thúc hợp đồng.

**Ví dụ:** P01 thuê 3.500.000 đ/tháng. Khách trả trước tháng 10–12/2026: thu 10.500.000 đ trong tháng 10. Chỉ số điện tháng 10: 130 kWh × 3.500 = 455.000 đ; nước 8 m³ × 20.000 = 160.000 đ; phí dịch vụ cơ sở 100.000 đ. Hóa đơn tháng 10 là **715.000 đ**, **không thu thêm 3.500.000 đ tiền phòng**. Tháng 11–12 cũng chỉ lập hóa đơn điện/nước/phí thực tế.

## 2. Database V2 → V3

Migration tự chạy **trong quá trình khởi động**, tuần tự, có phiên bản (`PRAGMA user_version=3`), idempotent, không xóa bảng hay dựng lại dữ liệu V2.

Các bảng thêm mới:

| Bảng | Chức năng |
|---|---|
| `user_permissions` | Cờ cho phép/từ chối từng thao tác theo user |
| `rent_prepayment_batches` | Chứng từ nhận tiền thuê trước theo đợt |
| `rent_coverage` | Khoản tiền thuê phân bổ theo hợp đồng và tháng; ngăn thu trùng |

Trước khi nâng cấp database V1/V2 hiện có, hệ thống tạo **SQLite online backup nhất quán** tại `/opt/troflow/backups/migrations/troflow-before-v3-*.sqlite3` và xác minh `PRAGMA integrity_check`. Dữ liệu của 12 phân hệ V2 và các hóa đơn cũ tiếp tục được giữ nguyên.

**Lưu ý:** Bản V2 trước đây **không hiểu các bảng/chính sách tiền thuê đã trả trước**. Không rollback bằng cách chỉ hạ image: khi khôi phục V2 phải cân nhắc khôi phục database được backup trước migration, có thể mất giao dịch đã phát sinh trong thời gian chạy V3. Luôn triển khai thử trên bản sao dữ liệu và chuẩn bị kịch bản rollback.

## 3. Portainer Stack và port linh hoạt

File dùng cho GitOps: `deploy/portainer-stack.yml`.

```yaml
services:
  troflow:
    image: ${TROFLOW_IMAGE:-ghcr.io/khaisilk1910/troflow:latest}
    ports:
      - "${TROFLOW_BIND_IP:-0.0.0.0}:${PORT:-8088}:8000"
    volumes:
      - /opt/troflow/data:/app/data
      - /opt/troflow/backups:/app/backups
      - /opt/troflow/uploads:/app/uploads
```

Port `8000` **chỉ ở bên trong container**, không chiếm cổng 8000 của server. `PORT=8088` là cổng trên host có thể đổi sang 8181, 8888, 9001, v.v. Không sử dụng `network_mode: host`. Biến mẫu của Stack nằm tại `deploy/portainer.env.example`.

**Portainer → Stacks → troflow → Environment variables:**

```env
TROFLOW_IMAGE=ghcr.io/khaisilk1910/troflow:latest
PORT=8088
TROFLOW_BIND_IP=0.0.0.0
COOKIE_SECURE=0
TROFLOW_TZ=Asia/Ho_Chi_Minh
```

Đặt `COOKIE_SECURE=1` khi trình duyệt truy cập qua HTTPS; không đặt `1` trên HTTP trực tiếp. Nếu sử dụng reverse proxy trên cùng Docker host, nên bind `TROFLOW_BIND_IP=127.0.0.1`. Bảo vệ các cổng mở ra LAN/Internet bằng firewall và HTTPS.

Trên máy Docker host:

```bash
sudo mkdir -p /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
sudo chown -R 10001:10001 /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
sudo chmod 700 /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
```

**Không xóa hoặc ghi đè** `/opt/troflow/data/troflow.db`. Trước khi cập nhật production, chạy sao lưu nhất quán bằng script:

```bash
docker exec troflow python /app/scripts/backup_sqlite.py
ls -lh /opt/troflow/backups
```

## 4. Đẩy mã nguồn lên GitHub bằng Git CMD (Windows)

Tải source ZIP, giải nén. Nếu repo có dữ liệu/commit từ trước thì:

```bat
cd /d D:\
git clone https://github.com/khaisilk1910/troflow.git
cd troflow
```

Chép **nội dung bên trong thư mục `troflow` của ZIP** vào thư mục clone (ghi đè file cũ; giữ thư mục `.git`). Sau đó:

```bat
git add -A
git commit -m "Upgrade TroFlow V3 - permissions, annual meters, prepaid rent"
git push origin main
```

Workflow tại `.github/workflows/build-deploy.yml` sẽ **chạy toàn bộ bài kiểm thử, build `linux/amd64`, push image `:latest` + tag SHA** lên GHCR. Nếu đã khai báo `PORTAINER_WEBHOOK_URL` trong GitHub Actions secrets, workflow gọi Portainer GitOps webhook. Trong Portainer phải bật **Re-pull image** và **Force redeployment**.

**Lưu ý:** workflow không tự bật quyền public cho GHCR package. Nếu image private, Docker host/Portainer cần xác thực để pull được. Webhook phải truy cập được từ runner GitHub Actions.

## 5. Kiểm thử

```bash
python -m pip install -r requirements.txt 'httpx>=0.27,<1' pytest
python -m unittest discover -s tests -v
node --check app/static/app.js
node --check app/static/advanced.js
```

Bộ thử nghiệm hiện có **14 bài test** API và migration, gồm V1→V3/V2→V3, tính tiền trả trước ba tháng, hóa đơn điện nước hằng tháng, hoàn tháng chưa sử dụng, không thu trùng, quyền API, staff login, phòng trống không được ghi chỉ số, danh sách điện nước nhiều tháng, số dư báo cáo, ghi chỉ số/import, PDF/backup.

Đã kiểm tra render trong Chromium với dữ liệu mô phỏng cho các màn hình **lọc chỉ số năm, form người thuê, bảng thu trước, hộp thoại 79 quyền**; không ghi nhận lỗi JavaScript ở lượt kiểm tra đó. **Chưa thử Docker build/Portainer deploy thật trong môi trường thực hiện**; hãy staging trước khi sử dụng với dữ liệu thật.

## 6. Giới hạn cần biết

- VietQR là mã chuyển tiền, **chưa tự đối soát ngân hàng**.
- Tiền phòng trả trước được ghi nhận như giao dịch thu tiền theo hợp đồng, không phải tự động phân bổ doanh thu kế toán dồn tích trong báo cáo doanh thu.
- Không cho hoàn tiền đã xuất hóa đơn, cần quy trình đối soát riêng.
- Phí dịch vụ được tính theo cấu hình hiện hành; nếu chủ trọ muốn tính dịch vụ vào đợt trả trước, cần bổ sung chính sách riêng (bản V3 **chỉ thu trước tiền thuê phòng**).
- Trong bản V3, hoạt động thư mục SQLite vẫn thiết kế cho **một container viết dữ liệu**; không scale nhiều replicas dùng chung SQLite.
- Không mở port Docker trực tiếp ra Internet mà không cấu hình HTTPS, quản lý tài khoản và backup.
