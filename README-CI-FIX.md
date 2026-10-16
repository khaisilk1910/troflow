# TrọFlow — Sửa GitHub Actions chỉ còn một workflow build image

## 1. Nguyên nhân lỗi đã xác nhận

Trong file `logs_104998190846.zip`, job `Test app` dừng tại `pip-audit` với `exit code 1`:

- `cryptography 46.0.4` có cảnh báo; báo cáo yêu cầu các phiên bản vá đến `50.0.0`.
- `starlette 0.50.0` có cảnh báo; báo cáo yêu cầu các phiên bản vá đến `1.3.1`.
- Job build image phụ thuộc job kiểm thử nên không chạy khi kiểm thử thất bại.

Bản vá này dùng `cryptography==50.0.2`, `starlette==1.8.0` và `fastapi==0.143.1` (bản FastAPI mới hỗ trợ Starlette 1.x). Vẫn giữ bước `pip-audit`: **không tắt hoặc bỏ qua lỗi bảo mật**.

## 2. Nên dùng bản vá nhỏ, không chép đè toàn bộ dự án

Giải nén `TroFlow_CI_Only_Patch.zip`, sao chép 2 file sau vào thư mục repository TrọFlow đang dùng (ghi đè file cũ):

- `requirements.txt`
- `.github/workflows/build-deploy.yml`

**Quan trọng:** Không chép đè toàn bộ source V5.7 nếu repository đã có thay đổi mới hơn bản phát hành này.

Mở **Git CMD** tại thư mục repository, chạy:

```bat
git rm -f .github/dependabot.yml
git add requirements.txt .github/workflows/build-deploy.yml
git commit -m "Fix TrọFlow single GitHub Action and audit"
git push origin main
```

Nếu không có `.github/dependabot.yml`, lệnh `git rm` sẽ báo lỗi không tìm thấy file; bạn có thể bỏ qua dòng này.

## 3. Sau khi push

Chỉ có một **workflow** `TroFlow - Build Docker Image` với một **job** `Test, audit, build and publish`. Job chạy lần lượt:

1. Cài đặt thư viện Python và kiểm tra dependency.
2. Quét lỗ hổng bằng `pip-audit`.
3. Kiểm thử Python, JavaScript.
4. Build/push `ghcr.io/khaisilk1910/troflow:latest` và tag `sha-<12 ký tự SHA>`.
5. Gọi Portainer webhook nếu đã khai báo secret `PORTAINER_WEBHOOK_URL`.

Nếu kiểm thử hoặc quét bảo mật thất bại, image **không được publish**, tránh cập nhật ứng dụng đang hoạt động bằng phiên bản có lỗi.

## 4. Vì sao các lượt Dependabot vẫn có thể xuất hiện?

Xóa `.github/dependabot.yml` sẽ dừng các **bản cập nhật phiên bản theo lịch** từ cấu hình này. Tuy nhiên:

- Các lượt chạy cũ vẫn tồn tại trong lịch sử GitHub Actions.
- **Dependabot security updates** có thể tiếp tục mở PR nếu bạn đã bật tính năng đó trong **Settings → Security & analysis / Code security** của repository. Muốn dừng luôn các bản cập nhật tự động này, cần tắt tùy chọn **Dependabot security updates** trong GitHub. Nên tiếp tục **bật Dependabot alerts** và theo dõi/vá cảnh báo thủ công.
- Trong ảnh của bạn, các run tên `pip in /`, `docker in /`, `github_actions in /` là từ Dependabot, không phải sáu job build image do workflow chính tạo ra.

## 5. Kiểm thử và giới hạn

- Đã xác nhận gốc lỗi từ log.
- Đã kiểm tra YAML: một workflow, một job, trigger push `main` và thao tác thủ công.
- 65/65 bài kiểm thử Python và các bài JavaScript đang có đều đạt với thư viện cục bộ **phiên bản cũ**.
- Chưa thể chạy bộ test trên `FastAPI 0.143.1`, `Starlette 1.8.0`, `cryptography 50.0.2` trong môi trường này (không có quyền tải package). Lần chạy GitHub Actions mới sẽ kiểm tra các phiên bản đó; không bảo đảm trước rằng job mới sẽ xanh.
- Chưa kiểm chứng Docker build/Portainer thực tế.

Việc sửa CI này **không thay đổi** cấu trúc database, volume và thư mục dữ liệu `/opt/troflow/`.
