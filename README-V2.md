# TrọFlow 2.0 — Nâng cấp 12 phân hệ (Docker + Portainer + GHCR)

**Gói nâng cấp từ TrọFlow V1, không phải sản phẩm thay thế.** Giữ nguyên toàn bộ API, UI cũ tại `/`, thêm khu vực quản trị nâng cao tại `/advanced` (cùng phiên đăng nhập).

## Danh sách 12 hạng mục và cách sử dụng

| # | Chức năng | Ở đâu trong UI | Endpoint chính |
|---|---|---|---|
| 01 | Sổ cọc: thu / hoàn / khấu trừ, đối chiếu cọc theo hợp đồng | Pro → Tiền cọc | `/api/v2/deposits`, `/balances` |
| 02 | Bật/tắt tính tiền phòng theo số ngày thực tế trong kỳ. Giảm giá, phụ thu và điều chỉnh | Pro → Hóa đơn → Tính theo ngày; Lập nháp | `/api/v2/contracts/{id}/proration`, `/invoices/preview` |
| 03 | Biểu phí riêng của cơ sở, theo phòng, người hoặc số lượng; áp cho hợp đồng | Pro → Phí dịch vụ | `/api/v2/services`, `/contract-services` |
| 04 | Danh sách người cư trú, đại diện, ngày đến/ngày đi, CCCD | Pro → Người ở | `/api/v2/residents` |
| 05 | Chỉ số điện/nước hàng loạt, ảnh công tơ và kiểm tra bất thường/missing | Pro → Điện & nước | `/api/v2/readings/batch`, `/readings/alerts`, `/files` |
| 06 | Hóa đơn nháp, xem trước, duyệt, giảm giá, truy thu, lịch sử sửa đổi và PDF | Pro → Hóa đơn | `/api/v2/invoices/*` |
| 07 | VietQR số tiền nợ của từng hóa đơn, nội dung chuyển khoản chứa mã HD | Pro → VietQR, Hóa đơn → QR | `/api/v2/properties/{id}/bank`, `/invoices/{id}/vietqr` |
| 08 | Biên bản nhận/trả phòng, ảnh hiện trạng, chỉ số cuối, đối chiếu công nợ, hoàn/khấu trừ cọc, PDF | Pro → Bàn giao phòng | `/api/v2/handovers`, `/files` |
| 09 | Nhập phòng, người thuê, hợp đồng, chỉ số điện nước từ XLSX/CSV; xem trước không ghi dữ liệu | Pro → Nhập Excel | `/api/v2/imports/{entity}` |
| 10 | Phân quyền quản trị toàn hệ thống, quản lý, kế toán, thu tiền, bảo trì, chỉ xem; hạn chế theo cơ sở | Pro → Phân quyền | `/api/v2/access` |
| 11 | Sao lưu theo lịch, giữ bản gần đây, integrity check, phục hồi có xác nhận sau restart; script đẩy backup ngoài server | Pro → Sao lưu | `/api/v2/backups/*`, `deploy/sync-backups-offsite.sh` |
| 12 | Lịch lập hóa đơn từng cơ sở, tạo nháp và cảnh báo thiếu chỉ số, chạy thử thủ công | Pro → Tự động hóa | `/api/v2/schedules/*` |

## Quy tắc nghiệp vụ

- **Bảo toàn tương thích:** `contracts.prorate` của hợp đồng cũ = `0`; hóa đơn cũ = `published`. Nếu không bật tính theo ngày, hóa đơn giữ nguyên công thức V1. Khi bật tính theo ngày, tiền phòng = giá tháng × (ngày giao hợp đồng nằm trong kỳ) / số ngày của tháng; cả ngày vào và ngày ra được tính. Hợp đồng đã chấm dứt không tiếp tục chiếm phòng.
- **Phí dịch vụ:** phí cơ sở vẫn được tính. Dịch vụ theo hợp đồng là khoản CỘNG THÊM; theo người đếm người ở có giao ngày với kỳ, theo số lượng dùng `quantity`. Giá và dòng hóa đơn được chụp vào bản ghi, thay đổi biểu phí sau đó không làm thay đổi hóa đơn đã tạo.
- **Hóa đơn:** tất cả hóa đơn tạo bởi lịch hoặc giao diện Pro đều là NHÁP. Sau duyệt/chốt mới được thu tiền. Hóa đơn tạo bằng chức năng V1 vẫn phát hành trực tiếp để không phá hành vi cũ. Chỉ số điện nước kỳ có hóa đơn (kể cả bản nháp) bị khóa chỉnh sửa.
- **Nợ kỳ trước:** hiển thị để đối chiếu, **không cộng vào tổng hóa đơn mới** nhằm tránh ghi nợ hai lần. Trả nợ cũ bằng thanh toán chính hóa đơn cũ.
- **Sổ cọc:** `contracts.deposit` là mức cọc yêu cầu, KHÔNG phải tiền đã thực thu. Phải ghi thu cọc qua sổ cọc. Các giao dịch không được sửa/xóa; sai sót điều chỉnh bằng giao dịch bù trừ. Không cho hoàn/khấu trừ quá số cọc đang giữ.
- **Kết thúc hợp đồng:** nút kết thúc trong giao diện V1 yêu cầu hợp đồng không còn tiền cọc đang giữ hoặc hóa đơn chưa thanh toán; nếu còn các khoản này phải đi qua luồng **Bàn giao phòng** của V2.
- **Trả phòng:** cảnh báo công nợ; phải xác nhận đã đối chiếu nếu còn nợ. Khấu trừ/hoàn cọc + cập nhật trạng thái hợp đồng diễn ra trong một transaction. Khi nhập chỉ số cuối, sẽ ghi chỉ số tháng trả phòng nếu chưa có hóa đơn; không được tự sửa chỉ số đã lập hóa đơn.
- **VietQR:** chỉ sinh link ảnh QR từ `img.vietqr.io`. Không có kết nối tự xác nhận tiền đã về; chủ trọ vẫn phải ghi nhận thanh toán hoặc triển khai đối soát ngân hàng riêng. Chỉ ngân hàng có BIN hoặc mã hợp lệ mới sinh được ảnh.
- **Nhập Excel:** tối đa 500 dòng / tệp 1,5 MB; dòng sai sẽ rollback toàn bộ; dry-run dùng rollback transaction. File chứa thông tin cá nhân, không chia sẻ công khai.
- **Sao lưu & phục hồi:** sao lưu bằng SQLite Online Backup API, chạy mỗi ngày một lần ở thời gian do admin định. Phục hồi từ bản đã kiểm tra và chỉ áp dụng **khi khởi động lại container**, trước khi API mở kết nối. Trước phục hồi tạo bản sao lưu trạng thái trước đó.

## Migration không mất dữ liệu

Cơ sở dữ liệu V1 cũ ở `/opt/troflow/data/troflow.db` được sử dụng nguyên đường dẫn. `app/migrations.py` nhận biết `PRAGMA user_version`; thêm cột/bảng V2, không xóa cấu trúc cũ hay đổi ID. Với DB V1 hiện hữu, TrọFlow tạo snapshot nhất quán **trước migration** tại:

```text
/opt/troflow/backups/migrations/troflow-v1-before-v2-YYYYMMDD-*.sqlite3
```

Các cơ sở, phòng, người thuê, hợp đồng, chỉ số, hóa đơn, giao dịch, nhân viên hiện hữu được giữ nguyên. Hợp đồng cũ tự tạo hồ sơ người đại diện trong bảng cư trú mới, không tạo lại hợp đồng.

**Trước cập nhật production:** tự tạo thêm một bản backup ngoài host, xác nhận đủ dung lượng trống và kiểm thử một bản sao DB trên môi trường staging. Sau cập nhật, kiểm tra `/api/health`, dashboard và hóa đơn cũ. Nếu rollback code về V1, V1 sẽ không hiểu nghiệp vụ mới (nháp, dịch vụ, thu cọc), vì vậy hãy rollback **code và dữ liệu** từ snapshot đồng bộ sau khi đã dừng dịch vụ; không chỉ đổi tag image.

## Deploy Portainer Stack

1. Trên Docker host:

   ```bash
   sudo mkdir -p /opt/troflow/data /opt/troflow/backups /opt/troflow/uploads
   sudo chown -R 10001:10001 /opt/troflow/{data,backups,uploads}
   sudo chmod 700 /opt/troflow/{data,backups,uploads}
   ```

2. Đưa mã nguồn vào cùng repository GitHub đang chạy TrọFlow; **giữ nguyên** `.github/workflows/build-deploy.yml`. Đẩy lên branch `main` bằng Git CMD/Git Bash:

   ```bash
   git add .
   git commit -m "Upgrade TroFlow to v2"
   git push origin main
   ```

3. GitHub Actions chạy kiểm thử, build `linux/amd64` và push `ghcr.io/<owner>/<repo>:latest` cùng tag SHA. Portainer dùng file `deploy/portainer-stack.yml` hiện có; hình thức GitOps, GHCR và tùy chọn webhook giữ nguyên. Kích hoạt **Re-pull image** và **Force redeployment**; cần URL webhook truy cập được từ GitHub Actions. Xem thêm `deploy/README-PORTAINER.md`.

4. Portainer Stack ánh xạ:

   ```yaml
   volumes:
     - /opt/troflow/data:/app/data
     - /opt/troflow/backups:/app/backups
     - /opt/troflow/uploads:/app/uploads
   ```

5. Vào `https://domain-nha-tro.example/` (hoặc IP LAN/port cấu hình), đăng nhập, mở menu **TrọFlow Nâng cao**; hoặc truy cập trực tiếp `/advanced`.

## Sao lưu ngoài máy chủ, tùy chọn

Cài và cấu hình `rclone` trên Docker HOST, tốt nhất dùng remote `crypt` được mã hóa; đặt `RCLONE_DEST` rồi chạy:

```bash
sudo env RCLONE_DEST=cryptremote:troflow-backups sh deploy/sync-backups-offsite.sh
```

Lịch offsite bằng `crontab -e` ở host (ví dụ 03:30 hàng ngày, sau backup 03:00):

```cron
30 3 * * * RCLONE_DEST=cryptremote:troflow-backups /bin/sh /path/to/repo/deploy/sync-backups-offsite.sh >> /var/log/troflow-offsite.log 2>&1
```

Điểm cần lưu ý: rclone và remote cloud là dịch vụ ngoài, tự cài trên host và đảm bảo quyền truy cập; mã nguồn chỉ cung cấp kịch bản tích hợp, không mặc định kết nối tài khoản đám mây của bạn. File `uploads` chứa ảnh giấy tờ/biên bản cần được sao lưu riêng nếu muốn khôi phục nguyên vẹn tất cả hình ảnh.

## Kiểm thử và hạn chế

Chạy trước khi push:

```bash
python -m pip install -r requirements.txt httpx
python -m unittest discover -s tests -v
```

Điểm đã được kiểm thử API gồm migration từ V1, bảo toàn hợp đồng, tạo người ở, sổ cọc, hóa đơn nháp / duyệt / PDF, phí dịch vụ, chỉ số, file ảnh, nhập XLSX thử & thật, VietQR URL, biên bản trả phòng, lịch nháp và phân quyền theo cơ sở. Không có Docker Engine trong môi trường phát triển để xác nhận image build và không có thông tin ngân hàng thật để kiểm thử quét QR tại ứng dụng ngân hàng.

**Chưa tích hợp:** xác nhận thanh toán ngân hàng tự động, gửi Zalo/SMS, chữ ký điện tử, lưu file ảnh trên object storage, đa tenant phân tán/quy mô lớn. TrọFlow không tạo hóa đơn điện tử thuế hợp pháp; PDF là chứng từ quản lý nội bộ.
