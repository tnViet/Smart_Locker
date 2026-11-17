# Hướng Dẫn Cấu Hình & Kết Nối Phần Cứng ESP32 – Smart Locker

Thư mục này chứa toàn bộ mã nguồn firmware và cấu hình dành cho vi điều khiển **ESP32** kết nối với hệ sinh thái **Smart Locker** (Backend Django và Frontend Web Dashboard).

---

## 1. Danh sách linh kiện sử dụng trong hệ thống Demo (2 ngăn)

| STT | Tên linh kiện | Số lượng | Chức năng | Ghi chú nguồn điện |
| :--- | :--- | :---: | :--- | :--- |
| 1 | **ESP32 DevKit V1** (30 pin / 38 pin) | 1 | Bộ xử lý trung tâm, kết nối Wi-Fi | 5V (Micro-USB hoặc chân VIN) |
| 2 | **Khóa chốt điện từ LY-03** | 2 | Khóa chốt ngăn 1 và ngăn 2 | **Nguồn riêng 12V DC (1A - 2A)** |
| 3 | **Module Relay 2 kênh (Opto cách ly)** | 1 | Đóng ngắt cấp điện 12V cho 2 khóa | 5V DC từ nguồn ngoài / ESP32 |
| 4 | **Module RFID RC522 (13.56MHz)** | 1 | Đọc thẻ gửi / lấy đồ (MIFARE 1K) | **Bắt buộc 3.3V** (Cắm 5V sẽ cháy RC522) |
| 5 | **Module cảm biến hồng ngoại LM393** | 2 | Phát hiện vật thể bên trong 2 ngăn | 3.3V hoặc 5V |
| 6 | **Màn hình OLED GME12864-49 (0.96" 128x64 I2C)** | 1 | Hiển thị hướng dẫn, số ngăn, cước phí | 3.3V hoặc 5V |
| 7 | **Diode 1N4007** | 2 | Diode dập xung ngược cho cuộn hút LY-03 | Mắc song song ngược chiều với khóa LY-03 |
| 8 | **Nguồn tổ ong / Adapter 12V-2A** | 1 | Cấp nguồn cho khóa LY-03 | Cấp tải cho 2 khóa |
| 9 | **Module hạ áp LM2596 (tùy chọn)** | 1 | Hạ 12V xuống 5V nuôi ESP32 & Relay | Giúp hệ thống dùng chung 1 nguồn 12V duy nhất |

---

## 2. Cơ Chế Hoạt Động Của Khóa Điện Từ LY-03 (12V)

Khóa điện từ **LY-03** hoạt động theo nguyên lý cơ học - điện từ:
1. **Trạng thái bình thường (Không cấp điện - 0V):** Lò xo cơ học bên trong luôn đẩy chốt khóa thò ra ngoài. Khi cửa tủ đóng lại, vát chốt sẽ tự trượt vào bát khóa và giữ chặt cửa.
2. **Trạng thái mở khóa (Cấp điện 12V):** Cuộn dây điện từ tạo lực hút từ trường kéo chốt thụt vào trong thân khóa, giải phóng cánh cửa để mở ra.
3. **NGUYÊN TẮC AN TOÀN QUAN TRỌNG:**
   - Khóa LY-03 **không phải là động cơ servo hay động cơ bước** (không có lệnh "quay xuôi để mở, quay ngược để đóng").
   - Cuộn dây của khóa LY-03 có nội trở thấp và sinh nhiệt rất lớn. Nếu ngâm điện 12V liên tục quá 5 giây sẽ làm nóng chảy lớp men cách điện, **gây cháy hỏng cuộn hút**.
   - **Xử lý trên ESP32:** ESP32 chỉ kích đóng Relay trong khoảng thời gian rất ngắn (`unlock_ms` từ `800ms` đến `1000ms`, theo đúng tham số backend gửi xuống), sau đó **TỰ ĐỘNG NGẮT RELAY NGAY LẬP TỨC**. Lúc này, chốt khóa tự động đàn hồi thò ra nhờ lò xo, sẵn sàng cho lần đóng cửa tiếp theo.

---

## 3. Sơ Đồ Đấu Nối Dây (Pinout Table)

## 3. Sơ Đồ Đấu Nối Dây (Pinout Thực Tế Trên Mạch Của Bạn)

| Thiết bị | Chân trên linh kiện | Chân trên ESP32 | Giao tiếp / Chức năng |
| :--- | :--- | :--- | :--- |
| **Màn hình OLED GME12864-49** | `VCC` / `GND` | `3.3V` / `GND` | Nguồn nuôi 3.3V (hoặc 5V) |
| (I2C - Địa chỉ `0x3C`) | `SDA` | **GPIO 21** | I2C Data |
| | `SCK` (`SCL`) | **GPIO 22** | I2C Clock |
| **Cảm biến hồng ngoại 1** | `VCC` / `GND` | `3.3V` / `GND` | Nguồn nuôi 3.3V |
| (Phát hiện đồ ngăn 1) | `OUT` (`DO`) | **GPIO 18** | Ngõ vào số (`0` = Có vật, `1` = Trống) |
| **Cảm biến hồng ngoại 2** | `VCC` / `GND` | `3.3V` / `GND` | Nguồn nuôi 3.3V |
| (Phát hiện đồ ngăn 2) | `OUT` (`DO`) | **GPIO 19** | Ngõ vào số (`0` = Có vật, `1` = Trống) |
| **Đầu đọc thẻ RFID RC522** | `3.3V` / `GND` | `3.3V` / `GND` | **Bắt buộc 3.3V** (Không cắm 5V) |
| (SPI tùy chỉnh) | `RST` | **GPIO 13** | Chân Reset phần cứng |
| | `SDA` (`SS` / `CS`) | **GPIO 26** | Chân chọn chip SPI |
| | `SCK` | **GPIO 27** | Xung nhịp SPI |
| | `MOSI` | **GPIO 14** | Dữ liệu ESP32 → RC522 |
| | `MISO` (`MI`) | **GPIO 12** | Dữ liệu RC522 → ESP32 |
| | `IRQ` | *Bỏ trống* | Không sử dụng |
| **Cảm biến cửa từ MC-38** | Ngăn 1 | **GPIO 32** (và GND) | Công tắc từ báo đóng/mở cửa ngăn 1 |
| | Ngăn 2 | **GPIO 33** (và GND) | Công tắc từ báo đóng/mở cửa ngăn 2 |
| **Module Relay 2 kênh (Khóa LY-03)**| Relay Ngăn 1 | **GPIO 4** *(hoặc chân mạch dùng)* | Kích xung 12V mở khóa LY-03 ngăn 1 |
| | Relay Ngăn 2 | **GPIO 5** *(hoặc chân mạch dùng)* | Kích xung 12V mở khóa LY-03 ngăn 2 |

---

### 3.4. Kết nối Module Relay 2 kênh & 2 Khóa LY-03 (12V)

#### A. Nối giữa ESP32 và Module Relay:
- **VCC (Relay):** Nối chân `VIN (5V)` của ESP32 (hoặc nguồn 5V ngoài).
- **GND (Relay):** Nối chân `GND` của ESP32.
- **IN1 (Điều khiển Khóa ngăn 1):** Nối chân **GPIO 26** của ESP32.
- **IN2 (Điều khiển Khóa ngăn 2):** Nối chân **GPIO 27** của ESP32.

#### B. Sơ đồ mạch điện 12V cấp cho Khóa LY-03 qua tiếp điểm Relay:
Mỗi kênh Relay có 3 cọc tiếp điểm: **COM** (Chân chung), **NO** (Thường mở), **NC** (Thường đóng).
- Cực **Dương (+12V)** của nguồn 12V nối vào cọc **COM** của Relay 1 và Relay 2.
- Cọc **NO** của Relay 1 nối vào 1 đầu dây của **Khóa LY-03 (Ngăn 1)**.
- Cọc **NO** của Relay 2 nối vào 1 đầu dây của **Khóa LY-03 (Ngăn 2)**.
- Đầu dây còn lại của cả 2 Khóa LY-03 nối chung về cực **Âm (GND / 0V)** của nguồn 12V.
- **LƯU Ý ĐẶC BIỆT:** Phải nối **GND của nguồn 12V** chung với **GND của ESP32** để đồng nhất mức điện thế tham chiếu.

```
       [ Nguồn +12V ] ---------------------> Cọc COM (Relay)
                                               |
                                     (Khi ESP32 đóng Relay)
                                               v
                                            Cọc NO
                                               |
                                               +----[ Diode Cathode (vạch bạc) ]
                                               |                               |
                                      +-----------------+                      |
                                      |   Khóa LY-03    |                      |
                                      +-----------------+                      |
                                               |                               |
                                               +----[ Diode Anode ]------------+
                                               |
       [ Nguồn GND (0V) ] ---------------------+-----------------------------> GND ESP32
```

> **BẮT BUỘC:** Lắp 1 con Diode **1N4007** mắc song song ngược chiều với 2 đầu dây của mỗi khóa LY-03 (đầu có vạch trắng/bạc nối vào dây nối với cọc NO Relay, đầu còn lại nối về GND). Diode này triệt tiêu dòng điện cảm ứng tự cảm ngược sinh ra khi ngắt cuộn dây, giúp bảo vệ tiếp điểm Relay không bị đánh tia lửa điện và ngăn ESP32 bị reset/treo.

---

## 4. Hướng Dẫn Cài Đặt Thư Viện Trên Arduino IDE

Mở **Arduino IDE** -> Vào menu **Sketch** -> **Include Library** -> **Manage Libraries...** và cài đặt các thư viện sau:

1. **MFRC522** (bởi *GithubCommunity* hoặc *Miguel Balboa*): Dùng để đọc thẻ RFID RC522.
2. **ArduinoJson** (bởi *Benoit Blanchon*): Phiên bản 6.x hoặc 7.x (dùng đóng gói và phân tích JSON chuẩn).
3. **Adafruit SSD1306** (bởi *Adafruit*): Thư viện điều khiển màn hình OLED GME12864-49 (khi cài thư viện này sẽ yêu cầu cài thêm **Adafruit GFX Library**, hãy chọn *Install All*).
4. *(Tùy chọn dự phòng)*: **LiquidCrystal_I2C** (nếu sau này đổi sang màn LCD 1602).

---

## 5. Hướng Dẫn Cấu Hình File `config.h`

Mở file `esp32_smart_locker/config.h` và chỉnh sửa các thông số sau:

```cpp
// 1. Tên Wi-Fi và Mật khẩu của bạn
#define WIFI_SSID           "TEN_WIFI_NHA_BAN"
#define WIFI_PASSWORD       "MAT_KHAU_WIFI"

// 2. Địa chỉ IP của máy tính đang chạy Backend Django (chạy ipconfig trên Windows để xem IPv4)
#define BACKEND_BASE_URL    "http://192.168.1.50:8000/api/v1"

// 3. Mã thiết bị tủ (mặc định LOCKER01)
#define DEVICE_ID           "LOCKER01"

// 4. Token thiết bị 32 ký tự (xem mục 6 bên dưới để biết cách lấy)
#define DEVICE_TOKEN        "0123456789abcdef0123456789abcdef"
```

---

## 6. Các Bước Khởi Chạy Và Thử Nghiệm Hệ Thống

### Bước 1: Khởi động Backend
Mở terminal tại thư mục gốc của dự án `Smart_Locker-main`:
```bash
docker compose up -d
```

### Bước 2: Tạo thiết bị và lấy Token xác thực
Chạy lệnh tạo tủ `LOCKER01`:
```bash
docker compose exec backend python manage.py create_device LOCKER01
```
Lệnh sẽ in ra một chuỗi mã token hex 32 ký tự. Copy chuỗi này dán vào `#define DEVICE_TOKEN` trong file `config.h`.

### Bước 3: Đăng ký thẻ RFID thử nghiệm
Truy cập giao diện Web Dashboard hoặc dùng lệnh Django Shell để thêm mã thẻ (UID) vào hệ thống:
1. Quẹt thẻ vào đầu đọc RC522, nhìn trên Serial Monitor (tốc độ `115200 baud`) sẽ in ra mã thẻ 8 ký tự, ví dụ: `A3F1C290`.
2. Dùng Web Dashboard (đăng nhập bằng tài khoản admin) vào mục Quản lý người dùng/Thẻ để thêm thẻ `A3F1C290`.

### Bước 4: Nạp code lên ESP32
1. Chọn Board: **ESP32 Dev Module**.
2. Chọn đúng cổng COM của ESP32.
3. Nhấn **Upload** để nạp code.

---

## 7. Kịch Bản Vận Hành Thực Tế

1. **Khởi động:**
   - ESP32 kết nối Wi-Fi, đồng bộ giờ UTC+7 qua NTP.
   - Gửi sự kiện `BOOT` và gọi `/sync` để kiểm tra trạng thái 2 ngăn.
   - Màn hình LCD hiện: `San sang! / Moi quet the`.
2. **Khách gửi đồ:**
   - Quét thẻ -> ESP32 gửi `POST /scan` -> Backend kiểm tra và phân phối ngăn trống (ví dụ Ngăn 1).
   - ESP32 kích đóng Relay 1 trong `800ms` -> Chốt thụt vào -> Khách mở cửa.
   - Hết `800ms`, Relay tự ngắt -> Chốt khóa thò ra.
   - Khách đặt đồ vào bên trong -> Cảm biến hồng ngoại nhận biết đồ (`has_item = true`).
   - Cửa đóng lại -> ESP32 gửi sự kiện `DOOR_CLOSED` báo có đồ -> Phiên chuyển sang `OCCUPIED`.
3. **Khách lấy đồ:**
   - Quét lại đúng thẻ đó -> Backend tính thời gian gửi và cước phí (nếu có).
   - Nếu miễn phí (hoặc đã trả tiền): Khóa ngăn tương ứng tự bung mở trong `800ms`.
   - Khách lấy đồ ra ngoài -> Cảm biến hồng ngoại báo trống (`has_item = false`) -> Đóng cửa -> Ngăn trở về trạng thái `FREE`.
