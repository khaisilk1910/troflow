# TrọFlow 4.0 — Hướng dẫn nâng cấp từ V3

**Mục tiêu:** Gộp các phân hệ nâng cao vào menu chính, hiển thị hóa đơn theo năm, sửa/xóa an toàn chỉ số, bổ sung ảnh và rà soát quyền truy cập. Phiên bản này tiếp tục sử dụng database SQLite của TrọFlow V1/V2/V3; **không xóa dữ liệu hoặc thay đổi vị trí Docker mount**.

## Những thay đổi đã thực hiện

1. **Hóa đơn cả năm:** Trang **Hóa đơn tiền trọ** lọc theo `Cả năm YYYY`, hiển thị hóa đơn của mọi tháng trong năm, kèm kỳ trên từng dòng. Form **lập hóa đơn** vẫn chọn **tháng** để tính chính xác điện/nước và không thu trùng tiền thuê đã trả trước.
2. **Chỉ số điện nước sửa kỳ được:** Form sửa gọi `PUT /api/readings/{id}` thay vì gọi POST theo phòng/kỳ cũ. Có thể sửa phòng, tháng/năm và số cũ/mới; server kiểm tra hợp đồng trong kỳ, **trùng `room_id + period` → 409**, hoặc một trong hai kỳ đã có hóa đơn → 409. Nút xóa gọi `DELETE /api/readings/{id}`, từ chối nếu chỉ số đã được sử dụng để lập hóa đơn. POST tạo mới có kỳ trùng sẽ trả 409, yêu cầu dùng nút **Sửa**; không còn âm thầm cập nhật một bản ghi cũ.
3. **Ảnh điện nước:** Form thêm/sửa chỉ số chấp nhận JPG, PNG hoặc WebP, tối đa 3 MiB mỗi ảnh. Hỗ trợ **ảnh điện và ảnh nước riêng**, lưu tại `/opt/troflow/uploads`, hiển thị ảnh đã lưu trong bảng và liên kết mở ảnh.
4. **Ảnh khách thuê:** Thêm `tenants.photo_path` và chức năng tải ảnh chân dung ngay tại form thêm/sửa người thuê. Ảnh đại diện xuất hiện trong bảng người thuê; ảnh truy cập qua endpoint có đăng nhập và phân quyền.
5. **Bỏ menu "TrọFlow Nâng cao":** Các phân hệ đã chuyển thành mục menu trực tiếp như Tiền cọc, Tiền thuê trả trước, Người ở, Phí dịch vụ, Bàn giao, Nhập Excel, Phân quyền, Tự động hóa, Sao lưu, VietQR. Để giữ tương thích chức năng hiện hữu, các màn hình thuộc ứng dụng mở rộng cũ được hiển thị **nhúng cùng nguồn, chung phiên đăng nhập và menu ngoài**, không còn hai thanh menu. Đường dẫn `/advanced` được giữ lại cho các liên kết cũ.
6. **83 quyền theo thao tác, 25 nhóm:** Bổ sung `readings.edit`, `readings.delete`, `contracts.delete`, `payments.edit`. Menu/nút ở giao diện chính và các phân hệ nhúng ẩn theo quyền. Các API tiếp tục kiểm tra quyền độc lập và giới hạn cơ sở. Quyền xóa mặc định **tắt** cho nhân viên; quản trị có quyền thao tác theo ràng buộc dữ liệu.
7. **Sửa tiền thu:** Admin hoặc nhân viên được cấp `payments.edit` có thể sửa số tiền, ngày, phương thức, ghi chú giao dịch. Giữ nguyên hóa đơn, ngăn tổng các giao dịch vượt quá tiền hóa đơn và ghi audit trước/sau số tiền.
8. **Xóa hợp đồng chưa phát sinh chứng từ:** Có API và nút xóa. Nếu hợp đồng đã có hóa đơn, tiền cọc, trả trước hoặc bàn giao thì yêu cầu dùng quy trình kết thúc hợp đồng, giữ lịch sử kế toán.
9. **Giữ bản V3:** Tính tiền thuê trả trước theo tháng, điện nước thực tế, quản lý cư trú, hóa đơn nháp, lịch tự động và các nghiệp vụ khác vẫn tồn tại.

### Lưu ý về xóa/sửa khi đã có hóa đơn

Admin **không được xóa trực tiếp chứng từ có khoản thanh toán, chỉ số điện/nước liên quan hóa đơn hoặc hợp đồng có lịch sử tài chính**. Đây là ràng buộc toàn vẹn dữ liệu có chủ đích; để sửa số tiền đã thu, dùng thao tác chỉnh sửa thanh toán có audit; để kết thúc hợp đồng dùng bàn giao/quyết toán. Nếu cần chứng từ hủy/điều chỉnh hóa đơn đã phát hành, đó là nghiệp vụ khác phải xây thêm, không nên sửa trực tiếp lịch sử giao dịch.

### Lưu ý về ảnh và quyền

Để nhân viên tải ảnh người thuê, cần `tenants.edit` và `files.upload`; tải ảnh chỉ số cần `readings.photos` và `files.upload`. Xem ảnh yêu cầu quyền đọc tài liệu phù hợp và giới hạn cơ sở. Ảnh sau khi gắn vào bản ghi là tệp riêng trong `/opt/troflow/uploads`; khi lưu bản ghi thành công nhưng ảnh lỗi, ứng dụng hiển thị cảnh báo rõ để tránh người dùng bấm Lưu lại và tạo bản ghi trùng.

## Migration V3 → V4

- `PRAGMA user_version` nâng từ `3` lên `4`.
- Thêm cột `tenants.photo_path TEXT`, giữ các bảng/cột/ID cũ.
- Các mục phân quyền mới được nhận diện động bởi `app/permissions.py`, không xóa bản ghi phân quyền cũ.
- Lần đầu khởi động trên database cũ tạo bản sao SQLite nhất quán tại `/opt/troflow/backups/migrations/troflow-before-v4-<timestamp>.sqlite3` (nếu đang có database). Nếu có lỗi migration, transaction rollback; không tự xóa bảng cũ.
- **Quan trọng:** Backup DB và thư mục uploads độc lập trước khi triển khai production. Tránh nâng cấp đồng thời hai container cùng trỏ vào SQLite.

## Portainer / Docker Stack

File: `deploy/portainer-stack.yml`. Image: `ghcr.io/khaisilk1910/troflow:latest`.

| Portainer Environment variable | Ví dụ | Ghi chú |
| --- | --- | --- |
| `TROFLOW_IMAGE` | `ghcr.io/khaisilk1910/troflow:latest` | GHCR package phải public hoặc cấu hình credential pull |
| `PORT` | `8088` | Cổng trên host; không chiếm cổng 8000 của host |
| `TROFLOW_BIND_IP` | `0.0.0.0` | LAN; nếu chỉ reverse proxy cùng host dùng `127.0.0.1` |
| `COOKIE_SECURE` | `1` | Chỉ đặt `1` khi truy cập ứng dụng bằng HTTPS |
| `BACKUP_KEEP` | `14` | Giữ bản sao lưu theo cấu hình |

Bind mount ở host:

```text
/opt/troflow/data      -> /app/data
/opt/troflow/backups   -> /app/backups
/opt/troflow/uploads   -> /app/uploads
```

Chuẩn bị trên host nếu **lần đầu**:

```sh
sudo mkdir -p /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
sudo chown -R 10001:10001 /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
```

**Không chown/xóa một database production mà không kiểm tra user, group và backup trước.** Image chạy dưới UID 10001.

Trước khi cập nhật production, hãy tạo bản backup database bằng chức năng sao lưu hiện có, **xuất thêm bản sao ra thiết bị khác** và kiểm tra có thể khôi phục trên staging. Nếu dùng reverse proxy, cấu hình HTTPS trước khi đặt `COOKIE_SECURE=1`.

## Git CMD → GitHub Actions → GHCR → Portainer

Clone repo hiện hữu nếu chưa có trên máy:

```bat
cd /d D:\
git clone https://github.com/khaisilk1910/troflow.git
cd troflow
```

Chép **nội dung** thư mục `troflow/` trong ZIP V4 vào thư mục repo đang clone; giữ lại `.git/`. Kiểm tra không có `.env`, mật khẩu hoặc SQLite cá nhân trong các file chuẩn bị commit. Sau đó:

```sh
git status
git add -A
git commit -m "Upgrade TroFlow V4 - meters invoices photos permissions"
git push origin main
```

Workflow `.github/workflows/build-deploy.yml` chạy `python -m unittest discover -s tests -v`, chỉ build/push GHCR sau khi các test thành công. Nếu repository có secret `PORTAINER_WEBHOOK_URL`, workflow sẽ gọi webhook khi image push xong. Trong Portainer cần bật **Re-pull image** và **Force redeployment** cho GitOps/webhook để không tái dùng image `latest` cũ. Khi cần rollback nên dùng tag `sha-<commit>`, và đảm bảo DB có khả năng tương thích với image cũ; không chỉ hạ image khi schema đã nâng.

## Kiểm thử / mức xác nhận

Chạy tại thư mục dự án:

```sh
python -m pip install -r requirements.txt 'httpx>=0.27,<1'
python -m unittest discover -s tests -v
node --check app/static/app.js
node --check app/static/advanced.js
```

**Đã kiểm tra trong môi trường xây dựng:** 19/19 integration/regression test đạt, cú pháp Python/JS đạt, các luồng upload, quyền hạn, trùng kỳ và bảo toàn ràng buộc hóa đơn được kiểm tra qua TestClient.

**Chưa xác nhận:** build image Docker và cập nhật Portainer trên server thật. Chromium trong môi trường này trả lỗi `ERR_BLOCKED_BY_ADMINISTRATOR` đối với HTTP/HTTPS nên chưa thể khẳng định toàn bộ layout và thao tác trình duyệt đạt. Cần QA trên staging bằng trình duyệt, đặc biệt các trang nhúng, modal tải ảnh, menu trên điện thoại và thao tác quyền.

## Quy trình QA staging trước khi nâng cấp thật

1. Sao chép database và thư mục uploads hiện tại sang một bộ `/opt/troflow-staging/{data,backups,uploads}` tách biệt.
2. Tạo staging Stack riêng, map bind mount staging vào `/app/data`, `/app/backups`, `/app/uploads`; dùng port khác (ví dụ 8089).
3. Kiểm tra đăng nhập Admin; mở **Hóa đơn tiền trọ**, đổi bộ lọc năm, xác nhận hóa đơn các tháng hiển thị.
4. Ghi một kỳ mới vào phòng có hợp đồng; thử tạo trùng (phải thấy cảnh báo), thử sửa kỳ (thành công nếu chưa lập hóa đơn), thử xóa và thử sửa/xóa khi kỳ đã có hóa đơn (phải bị từ chối).
5. Tải ảnh điện, ảnh nước và ảnh khách thuê; đăng xuất, đăng nhập lại, xác minh ảnh hiển thị và quyền của các user.
6. Với nhân viên đã cấp quyền một cơ sở, kiểm tra menu chỉ hiện mục có quyền, API trả 403 nếu gọi chức năng bị cấm; thử cập nhật chỉ số của cơ sở khác (403).
7. Kiểm tra trả trước tiền thuê theo tháng/quý và hóa đơn điện nước tháng vẫn không thu trùng tiền phòng.
8. Tạo backup mới sau migration, kiểm tra integrity, mới thực hiện lên production.
