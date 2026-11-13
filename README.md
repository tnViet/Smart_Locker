# Smart Locker – Backend

Backend cho tủ gửi đồ tự phục vụ 2 ngăn, viết bằng Django + PostgreSQL, chạy bằng docker-compose.
Backend là nơi duy nhất quyết định trạng thái ngăn và phiên; firmware ESP32 chỉ gửi sự kiện và làm theo phản hồi.

Tài liệu gốc nằm trong [`backend docs/`](backend%20docs/):

| File | Nội dung |
| --- | --- |
| `quy chuẩn api.docx` | Hợp đồng API giữa backend, firmware và dashboard, bảng chuyển trạng thái (chương 6) |
| `định dạng gói tin.docx` | Bảng trường, kiểu, giới hạn kích thước của từng gói |
| `thiết kế backend.docx` | Công nghệ, các app Django, thiết kế CSDL |
| `hệ thống ngoài.docx` | Giao thức hai máy chủ mô phỏng (nguồn 1, nguồn 2) |
| `kiến trúc hệ thống.docx` | Sơ đồ tổng thể |
| `ke-hoach-backend.md` | Kế hoạch code B1–B9 và các quyết định tạm Q1–Q23, Phụ lục A (JSON của API dashboard) |

## Chạy thử

Cần Docker Desktop.

```bash
cp backend/.env.example backend/.env      # rồi đổi SECRET_KEY, JWT_SECRET (>= 32 ký tự)
docker compose up -d --build              # db + backend ở cổng 8000, tự chạy migrate
```

Tạo thiết bị (token chỉ in ra **một lần**, nạp vào NVS của firmware):

```bash
docker compose exec backend python manage.py create_device LOCKER01
```

Tạo tài khoản dashboard (group `admin` hoặc `viewer`):

```bash
docker compose exec backend python manage.py shell -c "from django.contrib.auth.models import User, Group; u=User.objects.create_user('admin', password='doi-mat-khau'); u.groups.add(Group.objects.get(name='admin'))"
```

Chạy test (trên PostgreSQL trong container, không dùng SQLite):

```bash
docker compose exec backend python manage.py test
```

Chạy thử toàn luồng bằng ESP32 giả (BOOT, sync, gửi/lấy đồ, thu phí, gửi bù, mở thủ công; mất khoảng 4–5 phút vì khóa phải nghỉ 60 giây):

```bash
pip install requests
python tools/fake_esp32.py --device LOCKER01 --token <token> --admin-user admin --admin-pass <mk> --student-card <UID> --pay-secret <PAY_HMAC_SECRET>
```

Bước lấy đồ có phí cần máy chủ mô phỏng đang chạy; thiếu thì script tự bỏ qua bước đó.

> Trên Windows, nếu `docker compose build` trong Git Bash báo `docker-credential-desktop not found`, hãy chạy lệnh đó trong PowerShell.

## Cấu trúc

```
backend/
  config/      settings.py (biến môi trường, hằng số thời gian), urls.py, common.py (khung phản hồi, mã lỗi, token thiết bị)
  devices/     /heartbeat, /sync, /commands/{id}/ack, lệnh create_device
  lockers/     /scan, /events, /events/batch, state.py (máy trạng thái), fee.py (tính phí)
  identity/    adapters.py: tra thẻ ở nguồn 1 (GET) rồi nguồn 2 (POST + HMAC)
  payments/    charges.py (tạo khoản thu), /payment/check, /payments/callback
  dashboard/   auth.py (JWT), 15 API cho web dashboard
tools/fake_esp32.py   script đóng vai firmware
docker-compose.yml    db, backend (hai máy chủ mô phỏng sẽ thêm sau)
```

Quy tắc khi sửa code (xem `ke-hoach-backend.md` mục 1):

- Mọi thay đổi `status` của ngăn hoặc `state` của phiên phải đi qua `lockers/state.py`, view không tự gán.
- Hàm cần giờ hiện tại nhận tham số `now`; view lấy `timezone.now()` một lần.
- View là hàm thường trả `JsonResponse` qua `ok()` / `fail()` trong `config/common.py`. Không dùng DRF.
- Mỗi thay đổi phải có test và `python manage.py test` phải qua.

## API

Base URL: `http://<server>:8000/api/v1`. Mọi phản hồi theo khung:
`{"success":true,"data":{...}}` hoặc `{"success":false,"error_code":"...","message":"..."}`.

### Cho firmware ESP32 (header `Authorization: Device <token>`)

| API | Ghi chú |
| --- | --- |
| `POST /scan` | Trả `action` DEPOSIT / PICKUP / PAYMENT |
| `POST /events` | 8 loại sự kiện ở API 2.2 |
| `POST /events/batch` | Gửi bù tối đa 20 sự kiện, xử lý theo số đếm trong `request_id` |
| `GET /sync?device_id=...` | Trạng thái 2 ngăn + lệnh đang chờ |
| `POST /heartbeat` | Mỗi 30 giây, trả tối đa 1 lệnh mở |
| `POST /commands/{id}/ack` | `result` DONE / FAILED / REJECTED |
| `POST /payment/check` | Hỏi mỗi 2 giây khi đang hiện mã QR |

### Cho web dashboard (header `Authorization: Bearer <jwt>`, lấy từ `/auth/login`)

`POST /auth/login`, `GET /compartments`, `GET /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/pay`,
`GET|POST /users`, `PATCH /users/{id}`, `GET /stats/overview`, `GET /stats/revenue?from=&to=`, `GET /devices`,
`POST /admin/open`, `POST /admin/reset`, `GET|PATCH /fee-rules`.
JSON gửi lên và trả về xem `ke-hoach-backend.md` Phụ lục A. Viewer gọi API của admin nhận `FORBIDDEN` (403); token sai hoặc hết hạn nhận `UNAUTHORIZED` (401).

### Cho hệ thống ngoài

`POST /payments/callback` – không dùng token, xác thực bằng HMAC-SHA256 (`pay_code|amount|ts`, khóa `PAY_HMAC_SECRET`).

## Ghi chú cho từng phần

**Firmware (TV2, TV5)**

- JSON phản hồi **sắp xếp khóa theo bảng chữ cái** (ví dụ `{"data":{...},"success":true}`) để phản hồi gửi lại cho cùng `request_id` giống hệt từng byte. Hãy đọc theo tên trường, không theo thứ tự (Định dạng gói tin mục 1.4).
- `request_id` phải đúng dạng `<device_id>-<6 chữ số>`, `device_time` phải có múi giờ (`+07:00`).
- `device_id` trong thân gói phải trùng với thiết bị của token, khác thì nhận `DEVICE_UNAUTHORIZED`.

**Dashboard và máy chủ mô phỏng (TV7)**

- Hai máy chủ mô phỏng cần chạy trong docker-compose với tên service `source1` (cổng 9001) và `source2` (cổng 9002), khớp `SOURCE1_URL`, `SOURCE2_URL` trong `.env`.
- `SOURCE1_PAY_URL`, `SOURCE2_PAY_URL` là địa chỉ điện thoại của khách vào được, viết hoa, tối đa 38 ký tự.
- Backend gọi ra ngoài với timeout 1 giây và không gửi lại.
- CORS đã mở cho mọi origin để dashboard chạy ở cổng khác gọi được.

## Còn lại

- Ghép hai máy chủ mô phỏng của TV7 vào `docker-compose.yml` (bước B9, phần cuối).
- Một số điểm tài liệu gốc chưa quy định đã được quyết tạm (Q1–Q23 trong kế hoạch); khi tài liệu gốc được sửa cần đối chiếu lại.
