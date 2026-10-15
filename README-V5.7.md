# TrọFlow 5.7 — Khách thuê báo sửa chữa, 5 ảnh và album Zalo cho chủ nhà

Đây là **bản nâng cấp nguyên dự án** TrọFlow V5.6; không tạo ứng dụng độc lập. Vẫn dùng GitHub Actions → GHCR `ghcr.io/khaisilk1910/troflow:latest` → Portainer, image giữ port nội bộ `8000`, port ngoài đặt qua biến `PORT`, dữ liệu bind mount trong `/opt/troflow`.

## 1. Chức năng mới

### Khách thuê: cổng `/tenant`

- Thẻ **Yêu cầu sửa chữa** hiển thị đúng tên cơ sở và phòng từ **hợp đồng hiện có hiệu lực** của chính tài khoản đang đăng nhập. Không có dropdown chọn các phòng hoặc người thuê khác.
- Người thuê khai báo loại sự cố, tiêu đề, ưu tiên, mô tả và tối đa **5 ảnh** JPG/PNG/WebP (mỗi ảnh đầu vào không quá 3 MB). **Ngày báo được máy chủ ghi tự động**, không phụ thuộc vào trình duyệt.
- Chỉ gửi được nếu đang có **đúng một hợp đồng hiệu lực**. Nếu một tài khoản thuê nhiều phòng cùng lúc, yêu cầu chủ nhà xác định/điều chỉnh hồ sơ trước; ứng dụng không đoán phòng.
- Người thuê được xem các yêu cầu do chính mình gửi cùng trạng thái và ảnh riêng tư; không được sửa tiến độ, không xem sự cố do khách khác gửi, không được truy cập API nhân viên.
- Giới hạn 5 yêu cầu/giờ/tài khoản để ngăn spam.

### Admin/nhân viên có quyền: **Vận hành → Yêu cầu sửa chữa**

- Form thêm/sửa yêu cầu có ô upload **tối đa 5 ảnh**, xem trước trước khi gửi; có thể xem/xóa ảnh đã lưu nếu có quyền sửa và không còn thông báo Zalo đang chờ gửi.
- Ảnh có thể bổ sung khi sửa; hệ thống kiểm tra tổng số ảnh đã có và ảnh mới không vượt 5.
- Khi người thuê gửi, danh sách Admin hiển thị nhãn “Khách thuê gửi”. Admin/nhân viên quản lý trạng thái như cũ.
- Các API V8 kiểm tra quyền `tickets.create/view/edit` và quyền truy cập từng cơ sở. Không thể đổi phòng của yêu cầu do khách đã gửi.

### **Hệ thống → Thông báo Zalo**

- Admin bật **Bật gửi thông báo** và **Gửi yêu cầu sửa chữa của khách thuê cho chủ nhà** trong phần cấu hình.
- Trong **Danh sách nơi nhận**, chọn **+ Nơi nhận chủ nhà**. Thêm nhiều user/nhóm Zalo, đặt tên, nhập `threadId`/`groupId` (không phải số điện thoại), chọn cơ sở hoặc Tất cả cơ sở, bật/tắt nhanh, sửa/xóa nơi nhận.
- **Nơi nhận sửa chữa** phải có `on_ticket=1`, `enabled=1`, **không gắn với `tenant_id`**, để tránh vô tình gửi thông tin khách thuê cho người thuê khác.
- Khi khách gửi, hệ thống tạo thông báo riêng cho từng nơi nhận phù hợp cơ sở. Tin nhắn bao gồm: tên cơ sở, mã phòng, tên/SĐT khách, loại sự cố, tiêu đề, mức ưu tiên, trạng thái, ngày báo, nội dung yêu cầu và số ảnh.
- Với **2–5 ảnh**, TrọFlow gọi một lần **`POST /api/sendImagesByAccount`** của chính gói `zalo-bot-server` đã cung cấp. Nội dung dùng thuộc tính `message`, danh sách ảnh thuộc `imagePaths`, `threadId`, `type` user/group và `accountSelection`. Đây là **một album native của Zalo Bot**, không tách thành 5 yêu cầu gửi ảnh.
- Với 1 ảnh dùng `/api/sendImageByAccount`, với 0 ảnh dùng `/api/sendMessageByAccount`.
- Gửi qua **outbox bền vững**, chạy độc lập sau khi giao dịch lưu đã commit. Khi bot thất bại, yêu cầu sửa chữa vẫn được lưu, lỗi hiển thị ở **Nhật ký thông báo** để gửi lại thủ công.
- Nhân viên không có quyền quản trị không được cấu hình Zalo. Việc bật tính năng mặc định là **tắt** khi nâng cấp để tránh gửi nhầm.

**Lưu ý gửi album:** API bot trả về `deliveryStatus='accepted'` nếu xác nhận đủ số ảnh; nếu trả `partial`, TrọFlow đánh dấu lỗi để Admin kiểm tra lịch sử Zalo trước khi thử lại, vì có thể bot đã gửi một phần. API `zca-js` không chính thức nên gửi thành công trên production vẫn cần thử thực tế.

## 2. Ảnh và bảo mật dữ liệu

- Ảnh được giải mã/tái mã hóa dưới dạng JPEG và xóa metadata EXIF; tên tệp ngẫu nhiên 40 ký tự hex, tệp `0600` trong `/opt/troflow/uploads`.
- API ảnh của khách yêu cầu cookie phiên khách và đúng `reported_by_tenant_id` + cơ sở. API ảnh nhân viên yêu cầu `tickets.view` và quyền cơ sở. Không có thư mục ảnh công khai.
- Bot tải từng ảnh qua liên kết capability ngẫu nhiên 256-bit, có hạn **10 phút**; token chỉ tham chiếu ảnh sự cố, không truy xuất được ảnh CCCD. Không đưa token vào thông báo Zalo.
- API upload kiểm tra tối đa 5 ảnh, tối đa 3 MB/ảnh. Độ lớn request multipart dành riêng cho yêu cầu sửa chữa có giới hạn 18 MiB; proxy HTTPS phải cho phép khoảng **18 MiB** body cho các đường dẫn upload. Các API bình thường vẫn được bảo vệ ở giới hạn trước đó.
- Zalo Bot đang chạy `network_mode: host` trên Ubuntu; URL TrọFlow nội bộ để bot tải ảnh có thể là `http://127.0.0.1:8088` nếu port này được publish trên host. **Không mở port Zalo Bot 3000 trực tiếp ra Internet**.
- Gửi ảnh tới Zalo là chia sẻ dữ liệu ra một dịch vụ bên ngoài; chỉ cấu hình nơi nhận được phép và cần có sự đồng ý của người liên quan.

## 3. Migration an toàn V7 → V8

TrọFlow tự động tạo snapshot SQLite trước migration nếu đang nâng cấp từ V7. Migration **chỉ bổ sung**:

- Hai cột `tickets.reported_by_tenant_id`, `tickets.reported_contract_id` để gắn người gửi với hồ sơ, nhưng không thay đổi yêu cầu sửa chữa cũ.
- Bảng `ticket_photos`, `ticket_media_tokens` để lưu ảnh riêng tư và capability token thời hạn ngắn.
- Hai cờ `zalo_config.ticket_enabled`, `zalo_destinations.on_ticket`, đều mặc định `0`.
- Cột `zalo_outbox.ticket_id` cho hàng đợi thông báo sửa chữa.

Không xóa, làm mới hoặc đưa dữ liệu cũ lên GitHub. Dữ liệu vẫn nằm ở:

```text
/opt/troflow/data/troflow.db
/opt/troflow/backups/migrations/
/opt/troflow/uploads/
/opt/troflow/secrets/
```

Trước khi deploy, tạo backup **độc lập** cả database, uploads, secrets và thử trước trên Stack staging. Không chia sẻ database giữa staging/production.

## 4. Cài đặt trên Portainer và Zalo Bot

Giữ các bind mounts:

```yaml
volumes:
  - /opt/troflow/data:/app/data
  - /opt/troflow/backups:/app/backups
  - /opt/troflow/uploads:/app/uploads
```

Nếu public, tiếp tục dùng `deploy/portainer-stack-public.yml` và HTTPS. Stack public bind `127.0.0.1:${PORT:-8088}:8000` và đã khai báo `extra_hosts: ["host.docker.internal:host-gateway"]` để TrọFlow gọi Bot chạy host network.

Sau khi deploy:

1. Đăng nhập Admin → **Thông báo Zalo** → đảm bảo URL bot `http://host.docker.internal:3000` kết nối được; `URL nội bộ TrọFlow để bot tải ảnh`: `http://127.0.0.1:8088` (hoặc port bạn đặt).
2. Bật **Bật gửi thông báo** và **Gửi yêu cầu sửa chữa của khách thuê cho chủ nhà** rồi lưu.
3. Chọn **+ Nơi nhận chủ nhà**, nhập `threadId` của Zalo user hoặc `groupId`, chọn cơ sở, giữ **Nhận yêu cầu sửa chữa gửi cho chủ** được tích, lưu. Có thể tạo thêm nhiều nơi nhận.
4. Dùng tài khoản khách thử `/tenant` để gửi 2–3 ảnh mẫu. Xem yêu cầu tại menu **Yêu cầu sửa chữa** và nhật ký Zalo. Xác nhận nhóm/user nhận **một album** và đủ toàn bộ nội dung.
5. Sau khi thử thành công mới bật nơi nhận thật. Đảm bảo Cron/scheduler TrọFlow chạy (`TROFLOW_SCHEDULER=1`) vì outbox được xử lý trong scheduler.

Nếu Zalo không gửi: kiểm tra cấu hình đăng nhập bot, session, `media_url`, quyền nội bộ port 8088, quyền Zalo account với user/group và trạng thái trong nhật ký. Nếu `deliveryStatus` là `partial`, **kiểm tra Zalo trước khi nhấn Gửi lại**.

## 5. Git CMD

Giải nén ZIP, chép **nội dung** thư mục `troflow` vào repository Git đã clone (giữ nguyên `.git`).

```bat
git add -A
git commit -m "Upgrade TroFlow 5.7 - Tenant Repairs and Zalo Albums"
git push origin main
```

GitHub Actions tự chạy test, scan dependency, build image và đẩy GHCR. Portainer webhook chỉ cập nhật khi đã bật Re-pull image + Force redeployment. Tạm vô hiệu tự deploy sản xuất nếu chưa thử trên staging.

## 6. Đã kiểm thử / chưa kiểm thử

- Đã chạy unit/integration API: migration giữ dữ liệu, upload tối đa 5, loại bỏ ảnh giả, phòng tự động, cách ly dữ liệu hai khách, giới hạn 5 lượt/giờ, quyền theo cơ sở của staff, nơi nhận nhiều user/nhóm, bật/tắt, outbox, media token riêng, định dạng album bot, 0/1/2–5 ảnh.
- Đã chạy JavaScript syntax check và các bài kiểm tra UI mô phỏng/hồi quy từ bản 5.6.
- **Chưa kiểm chứng bằng trình duyệt Chromium thật trong môi trường hiện tại:** Chromium từ chối mở localhost với `ERR_BLOCKED_BY_ADMINISTRATOR`.
- **Chưa chạy Docker build/Portainer production, chưa gửi tin lên Zalo account thật** vì không có quyền truy cập máy chủ. Không nên diễn giải các bài test mock API là chứng nhận Zalo đã giao tin thành công.

