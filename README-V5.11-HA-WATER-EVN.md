# TrọFlow V5.11 — Home Assistant cho nước, chốt điện kỳ trước và xóa kỳ nhà cung cấp

**Nền tảng:** Toàn bộ mã nguồn V5.10 (tiền thuê tháng hiện tại, điện/nước phòng tháng trước và phát hành lại hóa đơn) vẫn được giữ nguyên. Bản này thay đổi **Công tơ điện nước tổng → Sản lượng và hóa đơn nhà cung cấp**, không thay dữ liệu chỉ số từng phòng hay các hóa đơn khách thuê đã phát hành.

## Quy tắc kỳ và thời gian (múi giờ Việt Nam, UTC+7)

| Loại | Ngày đồng bộ | Kỳ ghi vào cơ sở dữ liệu | Điều kiện |
|---|---|---|---|
| Điện tạm tính | Cả tháng | Tháng hiện tại (khi chọn mặc định `period_offset=0`) | Lấy 4 sensor cũ: chỉ số đầu/cuối tạm, sản lượng, tiền tạm tính. |
| Điện chính thức | Ngày 01–07 đầu tháng | **Tháng trước** | Phải khai báo sensor Tiêu thụ kỳ trước + Tiền kỳ trước; khi **chỉ số đầu kỳ/cuối kỳ trước thay đổi** so với lần đồng bộ trước, cập nhật chỉ số cuối kỳ trước và tính chỉ số đầu kỳ = cuối kỳ − tiêu thụ kỳ trước. |
| Nước chính thức | Ngày 06–12 đầu tháng | **Tháng trước** | Chỉ ghi khi nhóm sensor chỉ số/sản lượng/tiền thay đổi so với lần đồng bộ trước. |
| Thanh toán nước | Trong khoảng ngày 06–12; hoặc sau ngày 12 nếu kỳ đã được HA đồng bộ | **Giữ nguyên kỳ tháng trước đã có**, không lấy chỉ số kỳ mới | Dùng sensor số tiền đã thanh toán + ngày thanh toán. Không tự giảm khoản đã trả. |

Ví dụ: vào **tháng 10/2026**, số nước chốt ngày 07/10 và điện chốt ngày 03/10 sẽ ghi vào kỳ **09/2026**; điện đang tạm tính vẫn thuộc **10/2026**. Vào **tháng 01/2027**, kỳ trước là **12/2026**.

### Cấu hình HA — công tơ điện

Vào **Công tơ điện nước tổng → HA** trên dòng **Điện**. Giữ 4 sensor hiện tại; bổ sung:

- **Tiêu thụ kỳ trước (kWh)** — bắt buộc để tự chốt tháng trước.
- **Tiền điện kỳ trước (VND)** — bắt buộc cùng sensor trên.
- **Chỉ số cuối kỳ trước (kWh)** — không bắt buộc nếu đã dùng cùng sensor ở ô “Chỉ số đầu kỳ / cuối kỳ trước”; nếu có sensor riêng thì nhập để đọc trực tiếp.

Nên đặt **Gán dữ liệu tạm tính vào kỳ = Tháng hiện tại**. Chế độ cũ “Tháng trước” vẫn tồn tại để tương thích cấu hình V5.9 nhưng **không tự chốt thêm kỳ trước** trong chế độ này.

### Cấu hình HA — đồng hồ nước

Bấm **HA** trên dòng **Nước**, nhập đủ 6 sensor:

1. Chỉ số trước kỳ mới nhất (`old_entity`).
2. Chỉ số sau kỳ mới nhất (`new_entity`).
3. Tiêu thụ kỳ mới nhất (`usage_entity`), tương ứng sản lượng nhà cung cấp tính tiền. Nếu nhà cung cấp dùng điều chỉnh sản lượng, giữ giá trị sensor; không tự ép bằng hiệu chỉ số.
4. Tiền nước kỳ mới nhất (`amount_entity`).
5. Ngày thanh toán (`paid_on_entity`), trạng thái `YYYY-MM-DD`, `DD/MM/YYYY` hoặc `DD-MM-YYYY` (có thể để `unknown`/trống nếu chưa trả).
6. Đã thanh toán kỳ hóa đơn (`paid_amount_entity`), trả về số nguyên VND, đặt **0** khi chưa thanh toán.

Trước khi ghi thanh toán, 2 sensor thanh toán phải nhất quán: **số tiền dương phải có ngày**, chưa thanh toán thì số tiền 0 và ngày trống. Tiền đã trả không được lớn hơn tiền nhà cung cấp tính. Giá trị sensor số phải là số thuần với **dấu chấm thập phân**, không kèm đơn vị, không dùng dấu phẩy phân cách hàng nghìn.

### Lưu mốc so sánh và các giới hạn quan trọng

- **Lần đồng bộ đầu tiên chỉ lưu mốc sensor**, không tự đoán rằng giá trị đang nằm trong HA là hóa đơn vừa chốt. Nếu lần đầu cài đặt sau khi nhà cung cấp đã thay đổi sensor, có thể nhập kỳ trước bằng **Ghi kỳ nhà cung cấp** trên giao diện; sau đó bật tự đồng bộ cho chu kỳ kế tiếp. Không tự dời các bản ghi cũ, tránh làm lệch thống kê.
- Những kỳ mà Admin đã **nhập/sửa tay** không bị HA ghi đè. Với điện, kỳ HA đã ghi nhận thanh toán cũng được giữ nguyên. Với nước, HA chỉ được cập nhật thanh toán trên kỳ vẫn có nguồn HA và không được xóa hoặc giảm giá trị đã trả.
- Sau **ngày 12**, nước không tự gán lại chỉ số/sản lượng/tiền vào kỳ mới. Chỉ cập nhật **thông tin thanh toán** của kỳ đã ghi nhận từ HA nếu phù hợp; ngoài khoảng chốt không tạo dữ liệu nhà cung cấp mới.
- Sau khi Admin **xóa một kỳ**, TroFlow lưu dấu mốc để lần tự đồng bộ không tạo lại kỳ vừa xóa. Nếu cần lập lại, dùng **Ghi kỳ nhà cung cấp** để tạo thủ công; bản ghi nhập thủ công sẽ loại bỏ dấu chặn tương ứng nhưng vẫn được bảo vệ khỏi HA.
- Dữ liệu HA đều là `sensor.state` **hiện tại**; TroFlow không thể khôi phục lịch sử nhà cung cấp đã bỏ lỡ chỉ từ Home Assistant REST API. Khi nguồn HA sai, hãy ngừng tự đồng bộ, đối chiếu hóa đơn nhà cung cấp và sửa tay.

## Xóa kỳ nhà cung cấp đã thanh toán

Trong **Sản lượng và hóa đơn nhà cung cấp**, Admin có nút xóa cho **mọi tháng/kỳ**, kể cả kỳ có số tiền **Đã trả**. Hệ thống hiển thị cảnh báo và ghi audit (công tơ, kỳ, số tiền tính, số đã trả, ngày đã trả, nguồn). Nhân viên có quyền xóa kỳ vẫn chỉ được xóa kỳ **chưa thanh toán**. Việc xóa thay đổi số liệu báo cáo nhà cung cấp; **không hoàn tiền và không xóa hóa đơn thu khách thuê**.

## Nâng cấp và kiểm tra

1. Dùng cơ chế sao lưu SQLite nhất quán **trước khi cập nhật**, ví dụ `docker exec troflow python /app/scripts/backup_sqlite.py`. Sao lưu riêng `uploads` và `secrets/integration.key`. **Không xóa** database, token HA hoặc volumes cũ.
2. Giữ nguyên Docker/Portainer, LAN, Cloudflare Tunnel, `TROFLOW_PUBLIC_MODE` và các biến bảo mật. Đưa nguyên thư mục `troflow` của bản Full Source lên repository hiện có, build lại image và redeploy như các lần nâng cấp trước.
3. Khi khởi động, migration V11 tự thêm cột mapping HA, bộ nhớ mốc sensor và bảng kỳ đã xóa; không tự đổi số liệu lịch sử. Kiểm tra:

   ```bash
   docker exec troflow python -c "import sqlite3; c=sqlite3.connect('/app/data/troflow.db'); print('version:',c.execute('PRAGMA user_version').fetchone()[0]); print('integrity:',c.execute('PRAGMA integrity_check').fetchone()[0])"
   ```

   Kết quả kỳ vọng: `version: 11`, `integrity: ok`.
4. Vào từng công tơ nước/điện và thêm Entity ID chính xác. Bấm **Xem trước**, kiểm tra giá trị với Home Assistant và hóa đơn thực tế, **Lưu sensor**, rồi bật tự đồng bộ khi đã xác nhận dữ liệu.

## Kiểm thử

Chạy `python -m unittest discover -s tests -p 'test_*.py' -q` và `for f in tests/*.js; do node "$f"; done`. Test V11 dùng dữ liệu HA mô phỏng và SQLite tạm; **chưa kết nối thử HA thực tế của người dùng**.
