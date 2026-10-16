# TroFlow V5.9 - Zalo hai chiều + Home Assistant + định dạng số

Cơ sở nâng cấp: TroFlow V5.7 Zalo Connection/Welcome + Cổng khách thuê.

## Các thay đổi

- Khi khách gửi yêu cầu sửa chữa: thông báo gửi cho (a) Zalo chủ nhà bật `on_ticket`, (b) Zalo của chính khách thuê bật `on_ticket_tenant`. Thông báo cho khách cũng gửi khi quản lý đổi trạng thái yêu cầu qua cả API V8 và API thông thường.
- Khi khách gửi chỉ số điện/nước: thông báo gửi đến nơi nhận **chủ nhà** đã bật `on_meter_submission`. Chủ nhà vào **Duyệt chỉ số khách thuê** để duyệt/từ chối.
- Bật kênh và quyền gửi tương ứng tại **Thông báo Zalo**. Không gửi thông tin yêu cầu của khách cho tài khoản của khách khác. Cả hai luồng dùng hàng đợi Zalo sẵn có, có nhật ký/gửi lại khi lỗi.
- Định dạng số ở giao diện quản lý, khách thuê, công tơ, hóa đơn và ảnh hóa đơn dùng quy tắc `1,234,567.89`. Chỉ thay cách trình bày, không sửa cấu trúc số trong JSON/SQLite. Ngày tháng vẫn hiển thị theo thói quen Việt Nam.
- **Home Assistant**: kết nối REST API `GET /api/` và `GET /api/states/<entity_id>` bằng Long-Lived Access Token. Mỗi công tơ điện tổng có thể khai báo 4 sensor: đầu kỳ, cuối kỳ, sản lượng, thành tiền. Lựa chọn tháng hiện tại hoặc tháng trước, đồng bộ thủ công hay định kỳ mỗi giờ.

## Cấu hình Home Assistant

1. Tạo **Long-Lived Access Token** trong Home Assistant: trang Profile (Hồ sơ người dùng) → Long-Lived Access Tokens. Không công khai token; không đưa vào GitHub hoặc YAML Docker Compose.
2. Tại TroFlow → **Công tơ điện nước tổng** → **Kết nối Home Assistant** nhập URL nội bộ, ví dụ `http://192.168.31.100:8123`, và token. Bấm **Lưu cấu hình**, sau đó **Kiểm tra kết nối**. Máy chủ Ubuntu hoặc container TroFlow phải truy cập được địa chỉ HA, không phải chỉ trình duyệt của người dùng.
3. Tạo công tơ loại **Điện** nếu chưa có. Bấm **HA** trên dòng công tơ. Nhập đúng 4 `sensor.entity_id` (tìm trong Home Assistant → Developer Tools → States):
   - `old_entity`: chỉ số đầu kỳ hoặc cuối kỳ trước (kWh).
   - `new_entity`: chỉ số cuối kỳ hoặc tạm chốt (kWh).
   - `usage_entity`: sản lượng của kỳ (kWh).
   - `amount_entity`: tiền điện của kỳ (đồng).
4. Chọn **Gán dữ liệu vào kỳ**: tháng hiện tại (0), hoặc tháng trước (-1). Lưu sensor và dùng **Xem trước** để đối chiếu. Chỉ khi số liệu đúng mới bật **Tự đồng bộ mỗi giờ**.
5. Bấm biểu tượng **Đồng bộ** trên dòng công tơ để nhập thử. Xem kỳ mới trong **Sản lượng và hóa đơn nhà cung cấp**. Chỉ hiện nhãn **HA · tạm tính** đối với bản ghi tự động.

**Quan trọng**:
- Mỗi lần đồng bộ đọc **trạng thái hiện tại** của 4 entity, không truy vấn dữ liệu lịch sử. Nếu sensor reset mỗi tháng hoặc hóa đơn điện tính lệch kỳ dương lịch, chọn đúng độ lệch kỳ và chỉ dùng sensor phù hợp. Không tự suy luận kỳ hóa đơn EVN.
- Số liệu HA không nhất thiết là số tiền EVN thực thu. TroFlow đặt `paid_amount=0`, ghi nguồn `home_assistant`, kèm ghi chú **tạm tính**. Khi nhận hóa đơn chính thức, quản lý có thể sửa bản ghi và lưu để khóa đồng bộ tự động.
- **Không ghi đè** kỳ đã nhập/sửa thủ công hoặc kỳ có tiền đã trả. Không xóa hóa đơn cũ. Muốn lấy dữ liệu tháng đã qua, cần lưu kỳ đó trước khi sensor đổi sang kỳ mới; chức năng hiện tại không đọc lịch sử Home Assistant.
- Sensor phải trả về trạng thái **số thuần với dấu chấm thập phân** như `4523.87`, `308.55`, `829594`. Chuỗi `unavailable`, `unknown`, hoặc chuỗi có đơn vị trong chính `state` sẽ bị từ chối. Đơn vị phải nằm trong `attributes.unit_of_measurement`.
- Token được mã hóa trong `/app/data/home-assistant-credentials.bin` bằng `/run/secrets/troflow_integration_key`; giữ nguyên `integration.key` sau nâng cấp và sao lưu an toàn. Không đổi tên hoặc xóa file này.
- Scheduler chạy trong `TROFLOW_SCHEDULER=1`, tối đa mỗi giờ. Nếu HA tắt/mất kết nối, lần đồng bộ thất bại được lưu `last_error`, kỳ cũ vẫn nguyên vẹn.

## Triển khai

1. Sao lưu database `/opt/troflow/data/troflow.db`, uploads và secrets bằng công cụ sao lưu hiện có. Không chép file SQLite đang mở trực tiếp trong lúc ghi; sử dụng script backup hoặc cơ chế SQLite Backup API của TroFlow.
2. Dùng ZIP **Full Source** để cập nhật repository, hoặc ZIP **Patch** để ghi đè các file tương ứng lên cùng cơ sở mã nguồn TroFlow V5.7 Zalo Connection/Welcome. Giữ cấu trúc thư mục và kiểm tra `git diff` trước khi commit/push.
3. Đợi GitHub Actions build image mới rồi redeploy qua Portainer. Database tự áp migration V9, có snapshot trước khi nâng cấp khi sử dụng dữ liệu có sẵn. Không cần đổi `TROFLOW_PUBLIC_MODE`, Cloudflare Tunnel hay cấu hình kết nối LAN.
4. Nếu muốn dùng `host.docker.internal:8123`, bảo đảm `extra_hosts: host.docker.internal:host-gateway` đang có và dịch vụ HA có thể truy cập từ container. Nếu HA ở LAN, nhập URL LAN thật.
5. Vào **Thông báo Zalo** bật `Bật gửi thông báo`, `Gửi yêu cầu sửa chữa ...` và `Gửi thông báo chủ nhà khi khách gửi chỉ số`. Sửa nơi nhận: bật `Nhận yêu cầu ... cho chủ` + `Báo chủ nhà ...` cho tài khoản không gắn khách; bật `Nhận xác nhận và tiến độ ...` cho tài khoản Zalo User đã liên kết đúng khách thuê.

## Test

- `python -m unittest discover -s tests -p 'test_*.py' -q`
- `for f in tests/*.js; do node "$f"; done`

Trạng thái thử nghiệm: kiểm thử REST/SQLite và JS cục bộ; chưa thử kết nối với HA hoặc Zalo Bot Server thực tế của người dùng.
