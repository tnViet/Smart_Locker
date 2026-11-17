#ifndef CONFIG_H
#define CONFIG_H

// ==============================================================================
// 1. CẤU HÌNH KẾT NỐI WI-FI VÀ BACKEND SERVER
// ==============================================================================
#define WIFI_SSID           "NamPhung"        // Tên mạng Wi-Fi
#define WIFI_PASSWORD       "123456789"    // Mật khẩu Wi-Fi

// Địa chỉ Backend Server (IP máy tính của bạn trên mạng Wi-Fi iPhone Hotspot: cổng 8000)
#define BACKEND_BASE_URL    "http://172.20.10.2:8000/api/v1"

// Mã thiết bị (phải khớp với ID khi tạo thiết bị trên backend bằng lệnh create_device)
#define DEVICE_ID           "LOCKER01"

// Token 32 ký tự lấy từ kết quả lệnh: python manage.py create_device LOCKER01
#define DEVICE_TOKEN        "05af1eacdf664b9f26493caebbb90f6b"

// Phiên bản Firmware
#define FIRMWARE_VERSION    "1.0.3"

// ==============================================================================
// 2. CHỌN LOẠI MÀN HÌNH HIỂN THỊ (GME12864-49 là màn hình OLED 128x64 driver SSD1306)
// ==============================================================================
// #define USE_LCD1602_I2C     // Bỏ chọn LCD 1602
#define USE_OLED_SSD1306       // ĐÃ CHỌN: Dùng cho màn hình GME12864-49 (OLED 0.96" SSD1306 I2C)

#define OLED_I2C_ADDR       0x3C    // Địa chỉ I2C của GME12864-49 (thường là 0x3C, một số bản là 0x3D)
#define SCREEN_WIDTH        128
#define SCREEN_HEIGHT       64

#define LCD_I2C_ADDR        0x27    // Dự phòng nếu đổi sang LCD 1602
#define LCD_COLUMNS         16
#define LCD_ROWS            2

// ==============================================================================
// 3. SƠ ĐỒ CHÂN PHẦN CỨNG (GPIO PINOUT THEO MẠCH THỰC TẾ CỦA BẠN)
// ==============================================================================

// --- 1. Màn hình OLED GME12864-49 (I2C 0x3C) ---
#define I2C_SDA_PIN         21      // Chân SDA của OLED GME12864-49
#define I2C_SCL_PIN         22      // Chân SCK/SCL của OLED GME12864-49

// --- 2. Cảm biến hồng ngoại phát hiện đồ (LM393 IR) ---
// Đã đảo đúng theo dây thực tế trên tủ của bạn: Cảm biến bạn đang đặt đồ ở Ngăn 1 nối vào GPIO 19!
#define IR_SENSOR_COMP_1    19      // Cảm biến hồng ngoại ngăn 1 (GPIO 19: 0 = Có đồ, 1 = Trống)
#define IR_SENSOR_COMP_2    18      // Cảm biến hồng ngoại ngăn 2 (GPIO 18: 0 = Có đồ, 1 = Trống)
#define IR_DETECTED_LEVEL   LOW     // Mức logic LOW (0) khi đèn cảm biến sáng (phát hiện có đồ)

// --- 3. Module RFID RC522 (Giao tiếp SPI tùy chỉnh) ---
#define RFID_RST_PIN        13      // Chân RST của RC522
#define RFID_SS_PIN         26      // Chân SDA (SS / CS) của RC522
#define RFID_SCK_PIN        27      // Chân SCK của RC522
#define RFID_MOSI_PIN       14      // Chân MOSI của RC522
#define RFID_MISO_PIN       12      // Chân MISO (MI) của RC522

// --- 4. Cảm biến đóng/mở cửa từ MC-38 ---
#define SIMULATE_DOOR_SENSORS false // false: Đọc trực tiếp từ công tắc từ MC-38 thật
#define DOOR_PIN_COMP_1     32      // Công tắc từ MC-38 ngăn 1 (GPIO 32)
#define DOOR_PIN_COMP_2     33      // Công tắc từ MC-38 ngăn 2 (GPIO 33)
#define DOOR_CLOSED_LEVEL   LOW     // Tiếp điểm đóng khi cửa đóng (nối GND = LOW)

// --- 5. Module Relay điều khiển 2 Khóa điện LY-03 (12V) ---
// CHÚ Ý: Vì chân 26 và 27 của bạn đã dùng cho RC522 (SS và SCK), 
// hãy kiểm tra xem 2 Relay kích khóa LY-03 trên mạch của bạn nối vào 2 chân nào!
// Tạm thời đặt mặc định là GPIO 4 và GPIO 5 (hoặc 16 và 17, 23 và 25):
#define LOCK_PIN_COMP_1     16       // Kích Relay Khóa ngăn 1 (Thay đổi số chân nếu mạch dùng chân khác)
#define LOCK_PIN_COMP_2     17       // Kích Relay Khóa ngăn 2 (Thay đổi số chân nếu mạch dùng chân khác)

#define RELAY_ACTIVE_LEVEL   LOW     // Mức kích Relay ON để cấp 12V mở khóa
#define RELAY_INACTIVE_LEVEL HIGH    // Mức kích Relay OFF để ngắt 12V

// --- 6. Còi Buzzer (Đã tắt hoàn toàn theo yêu cầu) ---
#define ENABLE_BUZZER       false   // Tắt còi loa
#define BUZZER_PIN          -1      // Không sử dụng chân còi

// ==============================================================================
// 4. CÁC HẰNG SỐ VẬN HÀNH & TIMING
// ==============================================================================
#define DEFAULT_UNLOCK_MS        800     // Thời gian cấp xung điện mở khóa LY-03 mặc định (800ms)
#define MAX_UNLOCK_MS            2000    // Giới hạn an toàn tối đa cho cuộn hút LY-03 (2000ms)
#define DEFAULT_DOOR_TIMEOUT_SEC 30      // Thời gian chờ đóng cửa tối đa (30 giây theo chuẩn Backend)
#define HEARTBEAT_INTERVAL       5000    // Chu kỳ gửi Heartbeat & nhận lệnh mở từ Web Dashboard: 5 giây
#define PAYMENT_POLL_MS          2000    // Chu kỳ hỏi kết quả thanh toán /payment/check: 2 giây

#endif // CONFIG_H
