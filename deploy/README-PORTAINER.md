# TrọFlow: Git CMD -> GitHub Actions -> GHCR -> Portainer Stack

**TrọFlow 3.0:** xem [README-V3.md](../README-V3.md) trước khi nâng cấp. **Phiên bản TrọFlow 2.0:** tài liệu nâng cấp nghiệp vụ, migration từ V1 và rollback an toàn nằm ở [README-V2.md](../README-V2.md). Ứng dụng có thêm `/advanced` và thư mục ảnh riêng trên host `/opt/troflow/uploads`.

Triển khai dành cho **Portainer + Docker Standalone** (không phải Docker Swarm). Dữ liệu thật ở host **`/opt/troflow/data`**, sao lưu tại **`/opt/troflow/backups`**, ảnh tải lên tại **`/opt/troflow/uploads`**, không nằm trong Git/image.

## 1. Chuẩn bị host Ubuntu/Debian

Docker và Portainer đã được cài đặt. Chạy trên máy chủ:

```bash
sudo mkdir -p /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
sudo chown -R 10001:10001 /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
sudo chmod 700 /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
```

Hoặc sau khi đưa mã nguồn lên server, chạy `sudo sh deploy/prepare-host.sh`. UID 10001 khớp `USER appuser` trong Dockerfile. Nếu trước đó đã có dữ liệu, **không xóa hay ghi đè** `troflow.db`.

## 2. Tạo GitHub repository và push từ Git CMD/Git Bash Windows

Tạo repository mới, ví dụ `https://github.com/MYACCOUNT/troflow` (trong GitHub). Mở Git Bash tại thư mục `troflow` đã giải nén:

```bash
git init
git branch -M main
git remote add origin https://github.com/MYACCOUNT/troflow.git
git add .
git commit -m "Deploy TroFlow via GHCR"
git push -u origin main
```

Nếu repo đã có sẵn, không cần `git init` hay thêm remote lần nữa; dùng `git add . && git commit -m "..." && git push origin main`. **Đừng commit** `.env`, token, backup, cơ sở dữ liệu. GitHub có thể yêu cầu đăng nhập bằng Git Credential Manager thay vì password.

## 3. GitHub Actions tự build/push image

Workflow: `.github/workflows/build-deploy.yml`. Khi push `main`, chạy kiểm thử, sau đó build và push 2 tags:

- `ghcr.io/khaisilk1910/troflow:latest`
- `ghcr.io/khaisilk1910/troflow:sha-<12 ký tự commit>` (rollback dễ hơn)

Thay `myaccount/troflow` bằng **đúng owner/repository**, tất cả chữ thường. Workflow tự xác định tên từ GitHub Repository, **không cần sửa workflow**. Kiểm tra trong GitHub → **Actions** → `TroFlow - Build, publish and deploy`.

Image GHCR có thể mặc định **private** dù source public. Cách đơn giản: GitHub → Profile/Organization → Packages → package → Package settings → Change visibility → **Public**. Nếu phải để private, hãy tạo GitHub personal access token (classic) quyền `read:packages`, cấu hình GHCR Registry trong Portainer với đúng username/token, rồi chọn registry đó khi tạo Stack.

## 4. Tạo Portainer Stack kết nối Git repo

Vào **Stacks → Add stack → Git repository**, chọn GitHub repo, branch `main`, Compose path:

```text
deploy/portainer-stack.yml
```

**Environment variables** trong Portainer:

| Tên | Ví dụ | Ghi chú |
|---|---|---|
| `TROFLOW_IMAGE` | `ghcr.io/khaisilk1910/troflow:latest` | Có giá trị mặc định; khớp image Actions xây dựng |
| `TROFLOW_BIND_IP` | `0.0.0.0` | Cho phép LAN (cần firewall); dùng `127.0.0.1` nếu reverse proxy chạy trên cùng Docker host |
| `PORT` | `8088` | Cổng HTTP của host |
| `COOKIE_SECURE` | `0` | `1` khi truy cập bằng HTTPS, không phải HTTP trực tiếp |
| `TROFLOW_TZ` | `Asia/Ho_Chi_Minh` | Múi giờ |

Khi Portainer quản lý Docker trên **máy khác**, `/opt/troflow/...` là đường dẫn của **Docker host** đó, không phải máy cài trình duyệt/Portainer UI.

Bật **GitOps updates → Webhook** cùng 2 tùy chọn **Re-pull image** và **Force redeployment**. Chọn **Deploy the stack**. Portainer sẽ có một webhook URL dạng `https://PORTAINER_DOMAIN/api/stacks/webhooks/<uuid>`. **Giữ URL này bí mật** vì URL có thể kích hoạt triển khai mà không cần đăng nhập; không commit vào Git. Các lựa chọn theo [Portainer docs](https://docs.portainer.io/user/docker/stacks/add).

> Để dùng auto-deploy bằng webhook, GitHub Actions runner **phải có đường kết nối HTTPS** tới URL Portainer. Không nên công khai Portainer chỉ vì webhook nếu máy chỉ dùng LAN. Nếu không muốn public Portainer, không khai báo secret và tự bấm **Pull and redeploy** trong Portainer, hoặc sử dụng runner tự host có kết nối mạng nội bộ.

## 5. Kết nối GitHub Actions tới Portainer (tuỳ chọn auto-redeploy)

GitHub repository → **Settings → Secrets and variables → Actions → New repository secret**:

```text
Name: PORTAINER_WEBHOOK_URL
Value: https://your-portainer.example.com/api/stacks/webhooks/<uuid>
```

Sau mỗi push thành công và build image, GitHub Actions gọi `POST` webhook, Portainer pull lại image `latest` và cập nhật container; dữ liệu `/opt/troflow/data` giữ nguyên. Nếu secret không tồn tại, image **vẫn được build/push** nhưng người quản trị phải redeploy Stack thủ công.

Nếu cập nhật cấu hình workflow hoặc webhook, có thể chạy lại workflow từ GitHub Actions → **Run workflow**.

## 6. Test, backup và phục hồi

- Truy cập `http://IP_CUA_HOST:8088` nếu `TROFLOW_BIND_IP=0.0.0.0` và firewall cho phép. Nếu IP bind `127.0.0.1`, truy cập qua reverse proxy cùng máy chủ (khuyến nghị HTTPS).
- `docker ps --filter name=troflow`
- `docker logs -f troflow`
- Sao lưu cơ sở dữ liệu **đang hoạt động** (dùng SQLite online backup thay vì copy file `.db` trực tiếp):

```bash
docker exec troflow python /app/scripts/backup_sqlite.py
ls -lh /opt/troflow/backups
```

Script giữ **14 bản sao lưu gần nhất**, file mode private. **V2/V3 đã tích hợp bộ lập lịch sao lưu bên trong container**, mặc định 03:00 mỗi ngày theo `Asia/Ho_Chi_Minh` (điều chỉnh trong giao diện `/advanced` → Sao lưu). Chỉ dùng cron dưới đây nếu bạn đã tắt scheduler nội bộ (`TROFLOW_SCHEDULER=0`) để tránh chạy hai lịch trùng nhau:

```cron
0 3 * * * /usr/bin/docker exec troflow python /app/scripts/backup_sqlite.py >> /var/log/troflow-backup.log 2>&1
```

**Đảm bảo sao lưu bản khác nằm ngoài máy chủ** (sao lưu ngay trên cùng ổ đĩa không bảo vệ khỏi hỏng ổ). Tải xuống/sao chép ra nơi an toàn và bảo vệ dữ liệu định danh của khách thuê.

**Phục hồi (thủ công):** lưu lại bản DB hiện tại trước. Dừng container, lấy file sao lưu thay cho `/opt/troflow/data/troflow.db`, xóa **chỉ** file `troflow.db-wal`/`troflow.db-shm` cũ khi app đang dừng và sau khi đã giữ bản sao cần thiết, sau đó `chown 10001:10001`, khởi động lại. Không xóa toàn bộ thư mục `/opt/troflow/data`.

## 7. Rollback image

Tags `sha-<12 ký tự>` được xuất bản cùng với `latest`; để rollback, trước tiên đặt `TROFLOW_IMAGE=ghcr.io/khaisilk1910/troflow:sha-xxxxxxxxxxxx` trong Portainer rồi cập nhật/redeploy. Nếu một commit Git mới đổi cấu hình Stack, cần rollback config ở Git tương ứng. **Luôn sao lưu trước các thay đổi cấu trúc DB; app có migration tự động và sao lưu trước nâng cấp; rollback từ V3 về V2 bắt buộc kiểm tra tương thích và có thể cần bản backup trước migration.**

## Lưu ý

- Chỉ hỗ trợ một phiên bản app truy cập SQLite từ **một máy Docker host**. Không nhân đôi app dùng chung file SQLite qua NFS hoặc Swarm replicas.
- Không mở cổng 8088 trực tiếp ra Internet nếu không có HTTPS/reverse proxy, firewall và chính sách truy cập phù hợp.
- Chạy `docker inspect troflow` để kiểm tra Mounts xem đã map đúng `/opt/troflow/data`.
- Không cần Docker Hub password: GitHub Actions push GHCR bằng `GITHUB_TOKEN` có quyền `packages: write`.


**Phục hồi V2 từ giao diện:** vào `/advanced` → Sao lưu → kiểm tra backup → yêu cầu phục hồi (bắt buộc xác nhận) → khởi động lại container qua Portainer. Ứng dụng tạo snapshot trước khi phục hồi. Sao lưu ảnh `/opt/troflow/uploads` riêng nếu muốn khôi phục cả ảnh.
