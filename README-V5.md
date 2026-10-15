# TrọFlow 5.0 – Hồ sơ CCCD & quản lý công tơ điện nước tổng

Phiên bản này nâng cấp trực tiếp từ TrọFlow 4.0 (bao gồm lịch sử V1–V4), giữ nguyên đường dẫn dữ liệu Docker và luồng GitHub Actions → GHCR → Portainer.

## Các điểm mới

1. **Hồ sơ khách thuê**: CCCD/CMND bắt buộc đối với hồ sơ thêm mới (`9` hoặc `12` chữ số); ảnh chân dung và ảnh CCCD mặt trước/mặt sau là ba ảnh độc lập. Khách thuê lưu từ các phiên bản trước không bị xóa/sửa tự động nếu thiếu CCCD.
2. **Nhận diện khách**: danh sách người thuê, phòng, hợp đồng, chỉ số, hóa đơn, thanh toán và một số màn hình nghiệp vụ nâng cao có tên, ảnh (nếu có), điện thoại, CCCD. Ảnh chỉ tải được khi đăng nhập và được cấp quyền phù hợp.
3. **Dashboard**: Công việc cần chú ý và Thao tác nhanh được đưa ngay lên đầu trang, trước các KPI.
4. **Công tơ tổng theo cơ sở**: mỗi cơ sở/tòa nhà có nhiều công tơ điện hoặc nước; nhập số công tơ, mã khách hàng nhà cung cấp, đơn vị cung cấp, tên gợi nhớ, trạng thái. Có thêm, sửa, xóa (chỉ khi chưa có dữ liệu kỳ) và ngừng sử dụng.
5. **Kỳ ghi công tơ tổng**: nhập chỉ số đầu/cuối, sản lượng nhà cung cấp tính tiền (có thể khác chênh lệch chỉ số), số tiền phải trả, số tiền đã trả, ngày trả và ghi chú. Một công tơ chỉ có một bản ghi trong một kỳ YYYY-MM; sửa kỳ và đối soát chống trùng dữ liệu.
6. **Báo cáo điện nước theo năm/cơ sở**: đối chiếu (a) điện/nước đã tính cho khách theo hóa đơn **đã chốt**, (b) tiền nhà cung cấp tính, (c) khoản nhà cung cấp đã được trả và (d) ước tính điện/nước đã thu từ khách.
7. **Phân quyền**: nhóm quyền mới "Công tơ & điện nước tổng" gồm `view/create/edit/delete/record/deletebill/report`, hiển thị menu tương ứng, đồng thời chặn truy cập không được cấp phép tại API. Phân quyền cơ sở áp dụng cho mọi endpoint mới.

### Định nghĩa lãi/lỗ công tơ

- **Chênh lệch dồn tích** = tiền điện + nước đã tính cho khách trong hóa đơn đã chốt **trừ** số tiền nhà cung cấp đã tính trong cùng kỳ.
- **Chênh lệch tiền ước tính** = số tiền điện/nước đã thu từ khách *phân bổ theo tỷ lệ thanh toán hóa đơn* **trừ** số tiền chủ đã trả nhà cung cấp.
- Khi khách thanh toán một hóa đơn có cả tiền thuê phòng, điện, nước và dịch vụ, hệ thống hiện **không thể xác định chính xác** khách chỉ định bao nhiêu trong giao dịch đó cho điện/nước. Vì vậy khoản thực thu riêng điện/nước **được ước tính theo tỷ lệ đã thanh toán**, KHÔNG phải đối soát dòng tiền độc lập. Muốn số thu chính xác theo khoản mục, cần phân bổ/thu riêng từng khoản trong nghiệp vụ thanh toán ở phiên bản tương lai.
- Báo cáo cảnh báo thiếu kỳ nhà cung cấp điện/nước khi đã có công tơ đang hoạt động hoặc đã có điện nước tính cho khách.
- Sổ công tơ tổng tách biệt với bảng `expenses` và không tự cộng chi phí nhà cung cấp vào báo cáo thu chi chung. Tránh tự ghi kép khi làm bảng kết hợp thu chi tổng hợp; đối chiếu từng báo cáo theo mục đích.

## Database và migration an toàn

- V5 `PRAGMA user_version=5`.
- Chỉ **bổ sung cột** `tenants.id_front_path`, `tenants.id_back_path`.
- Thêm bảng `utility_meters`, `utility_meter_periods` và các unique/index.
- Không xóa, rebuild hoặc reset bảng V1–V4. Migration kiểm tra cột/tables và chạy idempotent; trước khi sửa cấu trúc database hiện tại hệ thống snapshot SQLite nhất quán trong `/opt/troflow/backups/migrations/`.
- Nếu gặp lỗi, transaction migration rollback. Không dựa duy nhất vào snapshot migration để bảo vệ ảnh hoặc dữ liệu production.

### Đường dẫn persistent trên máy chủ

```text
/opt/troflow/
  data/troflow.db
  backups/                  # SQLite snapshots, kiểm tra và backup định kỳ
  uploads/                  # Ảnh công tơ, ảnh khách thuê, ảnh CCCD
```

**Không** xóa `/opt/troflow/data`, `/opt/troflow/uploads` khi nâng cấp/redeploy. Sao lưu riêng cả SQLite lẫn uploads; đặt thư mục có quyền truy cập hạn chế và mã hóa bản sao lưu ngoại vi có thông tin CCCD.

### Portainer Stack

Bản deploy dùng `deploy/portainer-stack.yml`.

```yaml
services:
  troflow:
    image: ghcr.io/khaisilk1910/troflow:latest
    container_name: troflow
    restart: unless-stopped
    ports:
      - "${TROFLOW_BIND_IP:-0.0.0.0}:${PORT:-8088}:8000"
    environment:
      TZ: Asia/Ho_Chi_Minh
      DATABASE_PATH: /app/data/troflow.db
      UPLOAD_DIRECTORY: /app/uploads
      BACKUP_DIRECTORY: /app/backups
    volumes:
      - /opt/troflow/data:/app/data
      - /opt/troflow/backups:/app/backups
      - /opt/troflow/uploads:/app/uploads
```

Ví dụ trên rút gọn; dùng **file đầy đủ trong dự án** để giữ healthcheck, security và scheduler. `PORT=8088` là cổng bên ngoài, port 8000 **chỉ bên trong container**, không chiếm port 8000 host. Nếu sử dụng HTTPS reverse proxy, cân nhắc `TROFLOW_BIND_IP=127.0.0.1`, `COOKIE_SECURE=1`.

Chuẩn bị máy chủ trước khi deploy:

```bash
sudo mkdir -p /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
sudo chown -R 10001:10001 /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
sudo chmod 700 /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
```

Nếu các thư mục đã có dữ liệu, chỉ đổi quyền sau khi kiểm tra UID thực tế của ứng dụng trên host. Tuyệt đối không xóa database.

### GitHub Actions và Git CMD

File `.github/workflows/build-deploy.yml` tiếp tục dùng GHCR và webhook Portainer đã cấu hình. Bước kiểm thử chạy unit/integration tests + `node --check` + render smoke HTML. Tại repository đã clone, chép **nội dung** thư mục `troflow/` trong ZIP đè lên source hiện có (giữ thư mục `.git`) rồi:

```bash
git add -A
git commit -m "Upgrade TroFlow V5 - CCCD and supplier utility meters"
git push origin main
```

Theo dõi: https://github.com/khaisilk1910/troflow/actions

### API mới

- `GET/POST /api/utility-meters`, `PUT/DELETE /api/utility-meters/{id}`.
- `GET/POST /api/utility-bills`, `PUT/DELETE /api/utility-bills/{id}`.
- `GET /api/utility-report?year=2026&property_id=...`.
- `POST /api/v2/files` category `tenant_id_front`, `tenant_id_back` (tệp JPG/PNG/WebP, ≤3 MB) và GET `/api/v2/files/{name}` cần đăng nhập/phạm vi phù hợp.

### Kiểm tra trước production

1. Chụp backup cả database **và uploads** trên server cũ; giữ bản ngoài máy chủ.
2. Chạy V5 **trên Stack staging** gắn bản **sao** dữ liệu và ảnh, không dùng volume chung với production.
3. Thử tạo/sửa khách thuê, nhập CCCD và tải 2 mặt; xem quyền nhân viên đối với ảnh.
4. Thử tạo 2 công tơ điện + 1 công tơ nước cùng cơ sở; nhập trùng kỳ phải nhận `HTTP 409`.
5. Tạo một hóa đơn điện nước có thanh toán một phần, xem báo cáo năm, kiểm tra chênh lệch thu ước tính.
6. Kiểm tra giao diện trên desktop/mobile, backup/restore, ghcr image và Portainer webhook trên hạ tầng thực.
7. Khi đạt trên staging mới cập nhật Stack production. Rollback có thể yêu cầu phục hồi đồng bộ **image + database + ảnh**, không chỉ dùng image cũ.

### Kiểm thử trong môi trường xây dựng

- `python -m unittest discover -s tests -v`: **24/24** kiểm thử đạt.
- `node --check app/static/app.js`, `node --check app/static/advanced.js`: hợp lệ.
- `node tests/js_smoke.js`: render 6 trang thành công trong môi trường Node (mô phỏng state, không phải kiểm thử trình duyệt).
- **Chưa thực hiện** được tương tác Chromium với máy chủ localhost vì môi trường kiểm thử trả `ERR_BLOCKED_BY_ADMINISTRATOR`.
- **Chưa thực hiện** Docker build/Portainer deploy thật do không có Docker Engine hoặc quyền truy cập server của người dùng.
