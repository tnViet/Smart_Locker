# Kế hoạch code backend Smart Locker

Tài liệu gốc (viết tắt dùng bên dưới): Quy chuẩn API = **API**, Định dạng gói tin = **GT**, Thiết kế backend = **BE**, Hệ thống ngoài mô phỏng = **HTN**, Kiến trúc hệ thống = **KT**.
File này không chép lại nội dung tài liệu gốc, chỉ trỏ sang mục tương ứng. Tài liệu của thành viên khác không dùng.

## 1. Quy tắc chung, dán vào đầu mọi lần giao việc

1. Mỗi lần chỉ làm một bước ở mục 4. Không làm trước bước sau.
2. Tên trường, mã lỗi, trạng thái, đường dẫn lấy đúng từ tài liệu gốc. Không tự thêm cái mới. Gặp chỗ tài liệu và mục 2 của file này đều không nói thì dừng lại hỏi.
3. Chỉ tạo file và hàm có tên trong kế hoạch. Không thêm hàm phụ, class, decorator, middleware, thư viện.
4. View là hàm thường, trả `JsonResponse`. Không dùng Django REST Framework, không dùng class-based view.
5. Code dùng `if` và vòng `for` thường. Không dùng comprehension lồng nhau, lambda, toán tử `:=`, `*args`, `**kwargs`.
6. Mọi lần đổi `status` của ngăn hoặc `state` của phiên phải gọi hàm trong `lockers/state.py`. View không tự gán.
7. Mọi hàm cần giờ hiện tại nhận tham số `now`. View lấy `now = timezone.now()` một lần ở đầu rồi truyền xuống.
8. Mỗi bước phải có test và `python manage.py test` chạy qua trước khi sang bước sau. Test chạy trên PostgreSQL trong docker-compose, không dùng SQLite.

## 2. Quyết định tạm cho những chỗ tài liệu chưa quy định

Tài liệu gốc chưa quy định các điểm này. Code theo bảng dưới, tài liệu gốc sẽ được sửa theo sau.

| Mã | Nội dung | Dùng ở bước |
| --- | --- | --- |
| Q1 | `/scan` gửi đồ: không còn ngăn FREE thì `NO_FREE_COMPARTMENT`. Còn ngăn FREE nhưng chưa ngăn nào nghỉ đủ 60 giây thì `TOO_SOON` | B6 |
| Q2 | `/scan` dùng lại khoản thu PENDING còn hạn: `pay_timeout_sec` là số giây còn lại, làm tròn xuống, nhỏ nhất là 1 | B7 |
| Q3 | Sự kiện có ngăn: backend tự lấy phiên đang chạy của ngăn đó (state là CREATED, OPEN, OCCUPIED, RELEASING). `session_id` bằng 0 thì dùng phiên này | B5 |
| Q4 | `session_id` khác 0 mà không trùng phiên đang chạy của ngăn: trả `SESSION_NOT_FOUND`. Nếu ngăn không có phiên đang chạy thì vẫn áp bảng API 6.3 như sự kiện không có phiên. Nếu ngăn đang có phiên khác thì chỉ ghi log | B5 |
| Q5 | Ngăn ERROR còn phiên OCCUPIED, lệnh mở được ack DONE: phiên sang RELEASING, ngăn giữ ERROR. `DOOR_CLOSED` sau đó chỉ đổi phiên, ngăn vẫn ERROR cho tới khi reset | B4, B5 |
| Q6 | `DOOR_OPENED` tới khi ngăn FREE hoặc OCCUPIED nhưng đang có lệnh OPEN ở trạng thái PENDING cho ngăn đó: không chuyển ERROR | B4 |
| Q7 | `last_unlock_at` của lệnh thủ công ghi lúc ack DONE. `/heartbeat` và `/sync` không trả lệnh nếu ngăn của lệnh chưa nghỉ đủ 60 giây | B5 |
| Q8 | `display` chỉ dùng 4 chuỗi có trong API 2.1, 2.2, 2.7. Mọi trường hợp khác trả chuỗi rỗng. `message` theo bảng ở mục 3.3 | B3, B5, B6, B7 |
| Q9 | Khoản thu hết hạn: chỉ đưa `payment_status` của phiên về NONE khi nó đang là PENDING | B4 |
| Q10 | `/scan` đọc `request_log` trước khi gọi hệ thống ngoài, có thì trả luôn. Bước ghi `request_log` trong transaction ở BE 1.3 vẫn giữ | B6 |
| Q11 | Cột `char(n)` trong BE chương 2 khai báo bằng `CharField(max_length=n)`, PostgreSQL tạo `varchar(n)` | B2 |
| Q12 | `device_id` trong gói khác thiết bị của token: `DEVICE_UNAUTHORIZED` | B3 |
| Q13 | `/events` gặp `request_id` đã có trong bảng `events` nhưng không còn trong `request_log`: trả thành công với trạng thái hiện tại, `unlock_ms` 0, `display` rỗng, không xử lý lại | B5 |
| Q14 | `occupied_at`, `door_opened_at`, `closed_at` lấy giờ server lúc xử lý, kể cả sự kiện gửi bù. `device_time` chỉ lưu vào bảng `events` | B4 |
| Q15 | Phiên CREATED mà ngăn chuyển ERROR: CANCELLED. Phiên CREATED nhận `DOOR_CLOSED`: xử lý như phiên OPEN | B4 |
| Q16 | BOOT hủy phiên OPEN: ngăn giữ nguyên OPEN, chờ sự kiện cửa sau `/sync` hoặc mốc 10 phút | B4 |
| Q17 | `/commands/{id}/ack`: lệnh không tồn tại hoặc không thuộc thiết bị thì `INVALID_PAYLOAD`. Thành công trả `"data":{}`. Lệnh đã EXPIRED mà nhận DONE thì vẫn đổi trạng thái ngăn và phiên như lệnh PENDING. Lệnh đã DONE, FAILED, REJECTED thì trả thành công, không làm gì | B5 |
| Q18 | `/payment/check` khi phiên RELEASING và cửa đã mở: `paid` true, `unlock_ms` 0, `timeout_sec` 0, `display` rỗng. Phiên OCCUPIED đã PAID mà ngăn ERROR: `COMPARTMENT_ERROR` | B7 |
| Q19 | `/payments/callback` tự so `expires_at` với `now`, không dựa vào state EXPIRED | B7 |
| Q20 | `/scan`, `/events`, `/events/batch`, ack, `/payment/check` khóa các dòng `compartments` của thiết bị bằng `select_for_update()` ngay sau khi mở transaction. Index unique ở BE 2 vẫn giữ | B5, B6, B7 |
| Q21 | Thêm thư viện `django-cors-headers` để dashboard chạy khác cổng gọi được API. Bỏ `CsrfViewMiddleware` vì API không dùng cookie | B1 |
| Q22 | Mã dùng chung nằm ở `config/common.py`. `DATABASE_URL` tách bằng `urllib.parse`. Các mốc thời gian và `unlock_ms` mặc định là hằng số trong `settings.py` | B1, B3 |
| Q23 | Sai method HTTP hoặc đường dẫn không tồn tại: `INVALID_PAYLOAD` | B3 |

## 3. Cấu trúc và thành phần dùng chung

### 3.1 Thư mục

```
backend/
  manage.py
  requirements.txt        Django>=4.2, psycopg[binary], PyJWT, requests, django-cors-headers
  Dockerfile
  .env.example
  config/     settings.py  urls.py  common.py
  devices/    models.py  views.py  urls.py  tests.py
              management/commands/create_device.py
  lockers/    models.py  state.py  fee.py  views.py  urls.py  tests.py
  identity/   models.py  adapters.py  tests.py
  payments/   models.py  charges.py  views.py  urls.py  tests.py
  dashboard/  auth.py  views.py  urls.py  tests.py
docker-compose.yml        db, backend. Hai máy chủ mô phỏng do TV7 thêm sau
```

### 3.2 Model nằm ở app nào

`db_table` đặt đúng tên bảng trong BE chương 2. Cột, kiểu, ràng buộc lấy đúng BE chương 2.

| App | Model | Bảng | Ghi chú kỹ thuật |
| --- | --- | --- | --- |
| devices | Device, RequestLog, Command | devices, request_log, commands | `Command.id` là `AutoField` |
| lockers | Compartment, Session, Event, FeeRule | compartments, sessions, events, fee_rules | `Session.id` là `AutoField`. `FeeRule.id` là `SmallIntegerField(primary_key=True)` |
| identity | CardUser | users | Đặt tên `CardUser` để không lẫn với `auth.User` |
| payments | Payment | payments | |

Các model khác dùng `BigAutoField`. Hai index unique có điều kiện của `sessions` khai báo bằng `UniqueConstraint(fields=[...], condition=Q(state__in=[...]))`.

### 3.3 `config/common.py`

| Tên | Việc |
| --- | --- |
| `ERROR_HTTP` | dict mã lỗi sang HTTP status, đúng API chương 5 |
| `ERROR_MESSAGE` | dict mã lỗi sang `message`, bảng dưới |
| `ok(data)` | Trả khung thành công API 1.3 |
| `fail(error_code)` | Trả khung thất bại API 1.3 kèm HTTP status |
| `get_device(request)` | Đọc header `Authorization: Device <token>`, băm SHA-256, tra `devices.token_hash`. Trả `Device` hoặc `None` |
| `read_body(request, max_bytes)` | Thân vượt `max_bytes` hoặc không phải JSON object thì trả `None`, ngược lại trả dict |
| `find_logged(device, request_id)` | Trả `response` đã lưu trong `request_log` hoặc `None` |
| `server_error(request)`, `not_found(request, exception)` | Gắn vào `handler500`, `handler404` trong `config/urls.py`, trả `SERVER_ERROR` và `INVALID_PAYLOAD` theo khung chung |

**Bắt buộc vì kỹ thuật:** `ok` và `fail` phải gọi `JsonResponse(..., json_dumps_params={"separators": (",", ":")})`. Mặc định Django chèn dấu cách sau dấu phẩy và dấu hai chấm, phản hồi `/events/batch` 20 phần tử sẽ vượt 2048 byte của bộ đệm firmware (GT 1.6).

Kiểm tra kiểu: số nguyên phải là `type(x) is int` (vì `True` cũng là `int` trong Python), bool phải là `type(x) is bool`, chuỗi kiểm tra độ dài tối đa theo GT chương 2. Giới hạn kích thước thân theo GT 1.6.

Bảng `message` (ASCII, tối đa 64 ký tự). Chỉ dòng đầu có trong tài liệu, các dòng còn lại là tạm:

| error_code | message |
| --- | --- |
| CARD_NOT_FOUND | The khong hop le |
| CARD_BLOCKED | The da bi khoa |
| NO_FREE_COMPARTMENT | Het ngan trong |
| SESSION_NOT_FOUND | Khong co phien phu hop |
| SESSION_CONFLICT | Phien dang mo cua |
| TOO_SOON | Vui long cho |
| COMPARTMENT_ERROR | Ngan dang loi |
| PAYMENT_UNAVAILABLE | Thu lai sau |
| DEVICE_UNAUTHORIZED | Token sai |
| INVALID_PAYLOAD | Goi tin sai |
| SERVER_ERROR | Loi may chu |
| PAYMENT_NOT_FOUND | Khong co khoan thu |
| INVALID_SIGNATURE | Chu ky sai |

`CARD_READ_FAIL` có trong API chương 5 nhưng backend không bao giờ trả, nó chỉ là `event_type`.

### 3.4 Hằng số trong `settings.py`

Giá trị lấy từ API 6.4 và 1.7: `UNLOCK_MS = 800`, `DOOR_TIMEOUT_SEC = 30`, `WAIT_OPEN_SEC = 30`, `OPEN_MAX_SEC = 600`, `LOCK_REST_SEC = 60`, `PAY_TIMEOUT_SEC = 120`, `COMMAND_TTL_SEC = 300`, `REQUEST_LOG_TTL_SEC = 600`, `EXTERNAL_TIMEOUT_SEC = 1`, `JWT_TTL_SEC = 28800`.

## 4. Các bước

### B1. Khung dự án

- Tạo project `config` và 5 app ở mục 3.1.
- `settings.py`: theo BE 1.1 (múi giờ, PostgreSQL), đọc biến môi trường ở BE 1.6, hằng số ở mục 3.4, Q21.
- `docker-compose.yml`: service `db` (PostgreSQL) và `backend` (cổng 8000).
- `.env.example` liệt kê đủ biến ở BE 1.6, giá trị giả.

Xong khi: `docker compose up` chạy, `python manage.py check` không lỗi.

### B2. Model và dữ liệu khởi tạo

- Viết 9 model theo mục 3.2, tạo migration.
- Một data migration tạo: dòng `fee_rules` id 1 với giá trị mặc định, hai group `viewer` và `admin`.
- Lệnh `create_device <device_id>`: sinh token 32 ký tự bằng `secrets`, lưu SHA-256, tạo 2 ngăn số 1 và 2 ở trạng thái FREE, cửa đóng, in token đúng một lần.

Xong khi, có test cho:
- Tạo hai phiên OCCUPIED cùng `user` thì lỗi `IntegrityError`. Một phiên CLOSED và một phiên OCCUPIED cùng `user` thì được.
- Tương tự với cùng `compartment`.
- `create_device` tạo đúng 1 thiết bị, 2 ngăn, `token_hash` dài 64.

### B3. Lớp dùng chung

- Viết `config/common.py` theo mục 3.3, gắn `handler500`, `handler404`.
- `config/urls.py` gắn mọi app dưới `/api/v1/`.

Xong khi, có test cho:
- `ok` và `fail` sinh JSON không có dấu cách, đúng HTTP status.
- `get_device`: token đúng, token sai, thiếu header, sai tiền tố.
- `read_body`: vượt kích thước, JSON hỏng, JSON là mảng.

### B4. `lockers/fee.py` và `lockers/state.py`

Bước quan trọng nhất, chưa có view. Nên giao cho model mạnh nhất bạn có.

`fee.py`:

| Hàm | Việc |
| --- | --- |
| `duration_minutes(occupied_at, now)` | Số phút, làm tròn xuống |
| `compute_fee(duration_min, rule, source)` | Theo BE 1.5 mục Tính phí. `source` là LOCAL thì trả 0 |

`state.py`. Mỗi hàm chỉ sửa và `save()` đối tượng, không mở transaction, không trả HTTP:

| Hàm | Việc | Nguồn |
| --- | --- | --- |
| `set_compartment(comp, status, now)` | Gán `status`, `status_changed_at` | |
| `running_session(comp)` | Phiên đang chạy của ngăn hoặc `None` | Q3 |
| `compartment_error(comp, now)` | Ngăn sang ERROR. Phiên CREATED, OPEN sang CANCELLED. Phiên RELEASING sang CLOSED. Phiên OCCUPIED giữ nguyên | API 6.2, Q15 |
| `run_time_checks(now)` | Sáu việc ở BE 1.5, đúng thứ tự liệt kê, cho mọi thiết bị | BE 1.5, API 6.4, Q9 |
| `start_session(user, comp, now)` | Tạo phiên CREATED, ngăn sang OPEN, ghi `last_unlock_at` | API 6.2, 6.3 |
| `start_releasing(session, now)` | Phiên sang RELEASING, `door_opened_at` về null, ngăn OCCUPIED sang OPEN, ghi `last_unlock_at` | API 6.2, 6.3, Q5 |
| `on_door_opened(comp, session, now)` | Xem dưới | API 6.2, 6.3, Q6 |
| `on_door_closed(comp, session, has_item, now)` | Xem dưới | API 6.2, 6.3, Q5, Q15 |
| `on_lock_failed(comp, now)` | Gọi `compartment_error` | API 6.3 |
| `on_boot(device, firmware_version, now)` | Ghi `firmware_version`. Phiên CREATED: CANCELLED, ngăn về FREE. Phiên OPEN: CANCELLED, ngăn giữ OPEN. Phiên RELEASING cửa chưa mở: OCCUPIED, ngăn về OCCUPIED | API 6.2, Q16 |
| `on_command_done(command, rule, now)` | Xem dưới | API 6.2, 6.3, Q5, Q7, Q17 |
| `reset_compartment(comp, now)` | Ngăn ERROR và không có phiên đang chạy thì về FREE, trả `True`. Ngược lại trả `False` | API 6.3 |

`on_door_opened`:
- Luôn gán `door_closed = False`.
- Phiên CREATED: sang OPEN, ghi `door_opened_at`.
- Phiên RELEASING: ghi `door_opened_at`.
- Ngăn đang FREE hoặc OCCUPIED: nếu có lệnh OPEN đang PENDING cho ngăn thì bỏ qua (Q6), ngược lại gọi `compartment_error`.

`on_door_closed`:
- Luôn gán `door_closed = True` và `has_item`.
- Ngăn OPEN, phiên OPEN hoặc CREATED: có đồ thì phiên OCCUPIED, ghi `occupied_at` nếu đang null, ngăn OCCUPIED. Không có đồ thì phiên CANCELLED, ghi `closed_at`, ngăn FREE.
- Ngăn OPEN, phiên RELEASING: không có đồ thì phiên CLOSED, ghi `closed_at`, ngăn FREE. Có đồ thì phiên OCCUPIED, ngăn OCCUPIED.
- Ngăn OPEN, không có phiên: không có đồ thì FREE, có đồ thì `compartment_error`.
- Ngăn ERROR, phiên RELEASING: đổi phiên như trên, ngăn giữ ERROR (Q5).
- Ngăn FREE hoặc OCCUPIED: không đổi trạng thái.

`on_command_done`:
- Lệnh sang DONE, ghi `acked_at`. Ghi `last_unlock_at` của ngăn (Q7).
- Ngăn FREE: sang OPEN.
- Ngăn OCCUPIED hoặc ERROR có phiên OCCUPIED: tính `duration_min` và `fee` bằng `fee.py`, lưu vào phiên, gọi `start_releasing`.

Xong khi: mỗi dòng của ba bảng API 6.2, 6.3, 6.4 có ít nhất một test, cộng test cho từng dòng Q5, Q6, Q9, Q15, Q16. Test phí: với `free_min` 5, `block_min` 60, `block_fee` 2000 thì 5 phút là 0, 6 phút là 2000, 65 phút là 2000, 66 phút là 4000, 95 phút là 4000, thẻ LOCAL 95 phút là 0.

### B5. API không gọi hệ thống ngoài

Mọi view theo đúng 5 bước ở BE 1.3. Bảng trường và giá trị khi không dùng theo GT chương 2.

**`POST /events`** (lockers)
1. Kiểm tra `event_type` thuộc 8 giá trị ở API 2.2, sai thì `INVALID_PAYLOAD`.
2. Tra `request_log`, có thì trả lại. Tra `events`, có thì theo Q13.
3. Loại cần ngăn (cột cuối bảng API 2.2 có `compartment`) mà `compartment` không phải 1 hoặc 2: `INVALID_PAYLOAD`.
4. Xác định phiên theo Q3, Q4.
5. Gọi hàm tương ứng trong `state.py`. `ITEM_IN`, `ITEM_OUT`, `DOOR_TIMEOUT`, `CARD_READ_FAIL` chỉ ghi log.
6. Ghi một dòng `events` cho mọi sự kiện, kể cả sự kiện bị từ chối (`accepted` false kèm `error_code`).
7. Phản hồi theo GT 2.7. `unlock_ms` luôn 0. `display` là `Da khoa - Hen gap lai` khi `DOOR_CLOSED` đưa phiên từ OPEN sang OCCUPIED, còn lại rỗng (Q8).

**`POST /events/batch`** (lockers): theo BE 1.4. Sắp theo `int(request_id[-6:])`. Mỗi phần tử chạy trong `transaction.atomic()` lồng riêng, dùng lại đúng phần xử lý của `/events`. Phần tử ném exception thì `accepted` false, `error_code` là `SERVER_ERROR`, không ghi `events`. Mảng rỗng hoặc quá 20 phần tử: `INVALID_PAYLOAD`.

**`POST /heartbeat`** (devices): cập nhật 4 cột của thiết bị, gọi `run_time_checks`, trả tối đa 1 lệnh PENDING cũ nhất, áp Q7.

**`GET /sync`** (devices): chỉ đọc, không gọi `run_time_checks`. Phản hồi theo API 2.4. `pending_commands` giống `/heartbeat`.

**`POST /commands/{id}/ack`** (devices): theo API 2.6 và Q17. `result` ngoài ba giá trị: `INVALID_PAYLOAD`. DONE gọi `on_command_done`. FAILED và REJECTED chỉ đổi `state` của lệnh và ghi `acked_at`.

Xong khi, có test cho:
- Luồng gửi đồ bằng sự kiện: tạo sẵn phiên CREATED, gửi `DOOR_OPENED` rồi `DOOR_CLOSED` có đồ, phiên thành OCCUPIED.
- Gửi lại cùng `request_id`: phản hồi y hệt, bảng `events` vẫn một dòng.
- Batch gửi ngược thứ tự vẫn xử lý đúng. Batch gửi hai lần: lần hai mọi phần tử `accepted` true và trạng thái không đổi.
- Batch có một phần tử sai: phần tử khác vẫn được xử lý.
- Phản hồi batch 20 phần tử không quá 2048 byte.
- Q4: sự kiện của phiên đã hủy trên ngăn FREE làm ngăn thành ERROR.
- Lệnh thủ công: tạo lệnh, heartbeat nhận lệnh, ack DONE, trạng thái đổi đúng. Lệnh quá 5 phút không còn được trả.

### B6. identity và `/scan` không thu phí

`identity/adapters.py`. Ba hàm cùng trả một dict `{"source", "external_id", "name", "active"}` hoặc `None`:

| Hàm | Việc |
| --- | --- |
| `lookup_source1(card_uid)` | Theo HTN mục Nguồn 1. `source` là STUDENT |
| `lookup_source2(card_uid, now)` | Theo HTN mục Nguồn 2, ký HMAC. `source` là PARKING |
| `lookup(card_uid, now)` | Gọi nguồn 1, không thấy thì nguồn 2 |

Mọi lời gọi `requests` đặt `timeout=settings.EXTERNAL_TIMEOUT_SEC`. Bất kỳ lỗi nào (timeout, mất kết nối, status khác 200, JSON hỏng) đều trả `None`, không gửi lại (API 4.1, 4.2).

**`POST /scan`** (lockers), thứ tự:
1. Token, kích thước, kiểu trường. `card_uid` phải khớp `^[0-9A-F]{8}$`.
2. `run_time_checks` trong một transaction riêng.
3. `find_logged`, có thì trả (Q10).
4. Tra `users`. Chưa có thì gọi `identity.lookup` ở ngoài transaction.
5. Phần chuẩn bị khoản thu, làm ở B7.
6. Mở transaction: ghi `request_log`, khóa ngăn (Q20), rồi quyết định:
   - Không tìm thấy thẻ ở đâu: `CARD_NOT_FOUND`.
   - Thẻ mới tìm thấy: tạo dòng `users`, `blocked` là `not active`.
   - Thẻ `blocked`: `CARD_BLOCKED`.
   - Không có phiên đang chạy: cấp ngăn theo BE 1.4 và Q1, gọi `start_session`, trả DEPOSIT.
   - Phiên CREATED, OPEN, RELEASING: `SESSION_CONFLICT`.
   - Phiên OCCUPIED, ngăn ERROR: `COMPARTMENT_ERROR`.
   - Phiên OCCUPIED, ngăn chưa nghỉ đủ 60 giây: `TOO_SOON`.
   - Phiên OCCUPIED đã PAID: giữ nguyên `duration_min` và `fee` đã lưu, gọi `start_releasing`, trả PICKUP.
   - Phiên OCCUPIED, phí tính ra bằng 0: lưu `duration_min` và `fee`, gọi `start_releasing`, trả PICKUP.
   - Phiên OCCUPIED, phí lớn hơn 0: ở bước này tạm trả `PAYMENT_UNAVAILABLE`, B7 thay.
7. Lưu phản hồi (kể cả phản hồi lỗi) vào dòng `request_log`, commit.

Phản hồi theo API 2.1 và GT 2.6. `display` là `Ngan <số> - Moi bo do vao` hoặc `Ngan <số> - Moi lay do`.

Xong khi, có test (giả lập `requests` bằng `unittest.mock.patch`) cho:
- Chữ ký nguồn 2: khóa `demo-secret-123`, uid `A3F1C290`, ts `1794184790` cho ra `7f99b7afb93dd7db8d1948271acdc847d7fb81bcee460ec005df107e1ac1fb61`.
- Nguồn 1 timeout thì vẫn hỏi nguồn 2. Cả hai không thấy thì `CARD_NOT_FOUND`.
- Thẻ `inactive` thì tạo `users` với `blocked` true và trả `CARD_BLOCKED`.
- Thẻ đã có trong `users` thì không gọi ra ngoài.
- Cấp ngăn số nhỏ nhất. Hai ngăn đều bận: `NO_FREE_COMPARTMENT`. Q1.
- Quét lại khi phiên CREATED: `SESSION_CONFLICT`. Quét lấy đồ sau 10 giây: `TOO_SOON`.
- Gửi lại cùng `request_id`: không tạo phiên thứ hai, phản hồi y hệt.
- Thẻ LOCAL gửi 95 phút: PICKUP với `fee` 0.

### B7. payments

`payments/charges.py`:

| Hàm | Việc |
| --- | --- |
| `new_pay_code()` | 6 ký tự chữ hoa và số bằng `secrets.choice`, lặp tới khi chưa có trong `payments` |
| `sign(secret, text)` | HMAC-SHA256, hex chữ thường |
| `create_charge(source, pay_code, external_id, amount, session_id, now)` | `POST /charges` theo HTN mục Tạo khoản thu. Trả `True` khi status 200 và `received` true, mọi trường hợp khác trả `False` |

**Bổ sung `/scan`**, bước 5 (ngoài transaction): nếu thẻ có phiên OCCUPIED, chưa PAID, ngăn không ERROR, đã nghỉ đủ 60 giây và phí lớn hơn 0 thì:
- Có khoản thu PENDING còn hạn của phiên: dùng lại.
- Không có: sinh `pay_code`, gọi `create_charge` với `expires_in` 120.

Bước 6, nhánh phí lớn hơn 0:
- Dùng lại khoản thu: trả PAYMENT với `fee` là `amount` của khoản thu, `qr` cũ, `pay_timeout_sec` theo Q2.
- `create_charge` thành công: ghi `payments` (PENDING, `expires_at` là `now` cộng 120 giây), phiên ghi `payment_status` PENDING, `duration_min`, `fee`. Trả PAYMENT.
- `create_charge` thất bại: `PAYMENT_UNAVAILABLE`, phiên giữ nguyên.
- Bước 5 chưa chuẩn bị mà bước 6 lại cần (trạng thái đổi giữa chừng): ném exception để trả `SERVER_ERROR`, firmware gửi lại.

`qr` ghép theo BE 1.4: `SOURCE1_PAY_URL` hoặc `SOURCE2_PAY_URL`, rồi `/P/`, rồi `pay_code`.

**`POST /payment/check`** (payments): theo API 2.7, BE 1.4 và Q18. Phiên phải thuộc thiết bị và đang OCCUPIED hoặc RELEASING, không thì `SESSION_NOT_FOUND`. Phiên RELEASING cửa chưa mở: trả lại `paid` true kèm `unlock_ms`, không ghi lại `last_unlock_at`. `display` khi mở là `Da thanh toan - Moi lay do`.

**`POST /payments/callback`** (payments): không dùng token thiết bị. Thứ tự kiểm tra:
1. Thiếu trường, sai kiểu: `INVALID_PAYLOAD`.
2. `ts` lệch quá 300 giây hoặc chữ ký sai (so bằng `hmac.compare_digest`): `INVALID_SIGNATURE`.
3. Không có `pay_code`, hoặc khoản thu EXPIRED, hoặc PENDING mà `expires_at` đã qua (Q19): `PAYMENT_NOT_FOUND`.
4. `amount` khác: `INVALID_PAYLOAD`.
5. Khoản thu đã PAID: thành công, `duplicate` true.
6. Còn lại: khoản thu sang PAID, ghi `paid_at`, phiên ghi `payment_status` PAID. Không đổi `state` của phiên.

Xong khi, có test cho:
- Chữ ký tạo khoản thu: khóa `demo-pay-456`, chuỗi `K7M2QX|B23DCCN924|4000|128|1794190500` cho ra `b799a43b68a13af64d6e7e7bbef2b5747848d17a36c21444b18e1f729ec33346`.
- Chữ ký callback: khóa `demo-pay-456`, chuỗi `K7M2QX|4000|1794190570` cho ra `2656f7718d84c5408b6294b025790e59ceeb01ceebc1062bdefd3570668be9b2`.
- Cả luồng: gửi 95 phút, `/scan` trả PAYMENT 4000 với `qr` không quá 47 ký tự, `/payment/check` trả false, callback, `/payment/check` trả true và phiên RELEASING.
- Quét lại trong 120 giây: cùng `qr`, không gọi `create_charge` lần hai.
- Quá 120 giây: khoản thu EXPIRED, callback trả `PAYMENT_NOT_FOUND`, quét lại sinh `pay_code` mới.
- Hệ thống ngoài timeout: `PAYMENT_UNAVAILABLE`, phiên vẫn OCCUPIED, `payment_status` vẫn NONE.
- Callback gửi hai lần: lần hai `duplicate` true.
- Đã PAID, mở ra đóng lại còn đồ, quét lại: PICKUP ngay, không tạo khoản thu.
- Admin đã đánh dấu PAID, khoản thu cũ hết hạn: `payment_status` vẫn PAID (Q9).

### B8. dashboard

Tài liệu API 3.1 mới có danh sách đường dẫn, chỉ `/auth/login` và `/compartments` có JSON. Các API còn lại code theo Phụ lục A. Phụ lục A là quyết định tạm giống mục 2, tài liệu Quy chuẩn API chương 3 sẽ được sửa theo sau.

- `dashboard/auth.py`: `make_token(user)` và `check_token(request, need_admin)` bằng PyJWT, HS256, khóa `JWT_SECRET`, hạn 8 giờ. Quyền lấy từ group (BE 1.2, API 3.4). Token sai hoặc hết hạn trả HTTP 401.
- `POST /auth/login` theo API 3.4.
- `GET /compartments` theo API 3.3, gọi `run_time_checks` trước (BE 1.5). `started_at` là `occupied_at`, `current_fee` tính bằng `fee.py` tại lúc gọi.
- 13 API còn lại theo bảng và định nghĩa ở Phụ lục A. API chỉ admin được gọi: `/sessions/{id}/pay`, `POST /users`, `PATCH /users/{id}`, `/admin/open`, `/admin/reset`, `PATCH /fee-rules` (API 3.4).
- `/admin/open`: kiểm tra nghỉ 60 giây, chưa đủ thì `TOO_SOON` (API 3.1). Tạo dòng `commands` PENDING với `unlock_ms` là `settings.UNLOCK_MS`.
- `/admin/reset`: gọi `state.reset_compartment`.
- `/sessions/{id}/pay`: chỉ đổi `payment_status` sang PAID, không tạo dòng `payments` (BE 2).

Xong khi, có test cho:
- Đăng nhập đúng, sai mật khẩu, token hết hạn.
- Viewer gọi từng API của admin đều nhận `FORBIDDEN`.
- `/sessions` phân trang đúng `count`, `page`, `page_size`, `results`, lọc theo `date` và `state`.
- `/admin/open` tạo lệnh và heartbeat kế tiếp nhận được. Ngăn vừa mở dưới 60 giây: `TOO_SOON`.
- `/admin/reset` trên ngăn ERROR còn phiên OCCUPIED: bị từ chối. Sau khi phiên đóng: về FREE.
- `/sessions/{id}/pay` rồi quét thẻ: PICKUP ngay.
- Sửa `/fee-rules` rồi `/compartments` trả `current_fee` theo giá mới.

### B9. Chạy thử toàn luồng

Một script `tools/fake_esp32.py` dùng `requests`, đóng vai firmware, chạy lần lượt: BOOT, `/sync`, gửi đồ, lấy đồ miễn phí, lấy đồ có phí, mất mạng rồi gửi bù, lệnh mở thủ công. Sau đó ghép hai máy chủ mô phỏng của TV7 vào `docker-compose.yml`.

## Phụ lục A. JSON cho API dashboard (quyết định tạm)

Mọi phản hồi dùng khung API 1.3. Danh sách dùng phân trang API 3.2.

Mã lỗi riêng cho dashboard, chưa có trong API chương 5: `UNAUTHORIZED` (401, sai mật khẩu, token sai hoặc hết hạn), `FORBIDDEN` (403, viewer gọi API của admin), `NOT_FOUND` (404). Các mã `INVALID_PAYLOAD`, `TOO_SOON`, `SESSION_CONFLICT`, `COMPARTMENT_ERROR` dùng lại.

| API | Gửi lên | `data` trả về |
| --- | --- | --- |
| GET /sessions | `page`, `page_size`, `date`, `state`, `user_id` | Mỗi phần tử: `id`, `user_id`, `user_name`, `card_uid`, `compartment`, `state`, `created_at`, `occupied_at`, `closed_at`, `duration_min`, `fee`, `payment_status` |
| GET /sessions/{id} | | Như trên, thêm `events`: mảng `id`, `event_type`, `has_item`, `device_time`, `received_at`, `accepted`, `error_code` |
| POST /sessions/{id}/pay | thân rỗng | `id`, `payment_status`. Chỉ nhận phiên OCCUPIED, khác thì `SESSION_CONFLICT` |
| GET /users | `page`, `page_size` | Mỗi phần tử: `id`, `card_uid`, `name`, `source`, `external_id`, `blocked`, `created_at` |
| POST /users | `card_uid`, `name` | Một phần tử như trên, `source` là LOCAL. Trùng `card_uid` thì `INVALID_PAYLOAD` |
| PATCH /users/{id} | `blocked` | Một phần tử như trên |
| GET /stats/overview | | `sessions_today`, `revenue_today`, `occupancy_rate` |
| GET /stats/revenue | `from`, `to` | Mảng `date`, `revenue`, `sessions` |
| GET /devices | | Mảng `device_id`, `firmware_version`, `last_heartbeat_at`, `rssi`, `free_heap`, `pending_count`, `online` |
| POST /admin/open | `device_id`, `compartment`, `reason` | `command_id` |
| POST /admin/reset | `device_id`, `compartment` | `number`, `status`. Không reset được thì `COMPARTMENT_ERROR` |
| GET /fee-rules | | `free_min`, `block_min`, `block_fee`, `updated_at`, `updated_by` |
| PATCH /fee-rules | `free_min`, `block_min`, `block_fee` | Như GET |

Định nghĩa:
- `sessions_today`: số phiên có `created_at` trong ngày hôm nay theo giờ Việt Nam.
- Doanh thu: tổng `fee` của các phiên có `payment_status` PAID, tính theo ngày của `closed_at`. Phiên chưa đóng chưa tính.
- `occupancy_rate`: số ngăn không FREE chia tổng số ngăn tại lúc gọi, từ 0 tới 1.
- `online`: có heartbeat trong 90 giây gần nhất. Con số 90 lấy từ tài liệu TV7, tài liệu của bạn chưa có.
- `/admin/open`: nhận ngăn FREE, OCCUPIED, ERROR. Ngăn OPEN thì `SESSION_CONFLICT`.
