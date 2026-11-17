#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <time.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <ArduinoJson.h>

#include "config.h"

#if defined(USE_LCD1602_I2C)
  #include <LiquidCrystal_I2C.h>
  LiquidCrystal_I2C lcd(LCD_I2C_ADDR, LCD_COLUMNS, LCD_ROWS);
#elif defined(USE_OLED_SSD1306)
  #include <Adafruit_GFX.h>
  #include <Adafruit_SSD1306.h>
  Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
#endif

// Đối tượng phần cứng
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
Preferences preferences;

// Chu kỳ hệ thống
unsigned long lastHeartbeatMillis  = 0;
unsigned long lastSensorPollMillis = 0;
unsigned long lastCardScanMillis   = 0;
const unsigned long CARD_SCAN_COOLDOWN_MS   = 2000;
const unsigned long SENSOR_POLL_INTERVAL_MS = 250;

// Trạng thái thực tế của 2 ngăn (chỉ số 1 và 2)
uint32_t activeSessionId[3] = {0, 0, 0};
String   compStatus[3]      = {"FREE", "FREE", "FREE"};
bool     lastDoorClosed[3]  = {true, true, true};
bool     lastHasItem[3]     = {false, false, false};

// ==============================================================================
// CẤU TRÚC BẢN GHI NVS 16-BYTE (ĐỒNG BỘ VỚI BACKEND)
// ==============================================================================
typedef struct __attribute__((packed)) {
  uint8_t  event_type;   // 1:DOOR_OPENED, 2:DOOR_CLOSED, 3:ITEM_IN, 4:ITEM_OUT, 5:DOOR_TIMEOUT, 6:LOCK_FAILED, 7:BOOT, 8:CARD_READ_FAIL
  uint8_t  compartment;  // 0, 1 hoặc 2
  uint8_t  flags;        // bit0: has_item, bit1: door_closed, bit2: synced, bit3: offline
  uint8_t  checksum;     // XOR các byte còn lại
  uint32_t session_id;   // Little-endian
  uint32_t device_time;  // Unix timestamp (giây)
  uint32_t req_seq;      // Số thứ tự request_id
} ban_ghi_t;

static_assert(sizeof(ban_ghi_t) == 16, "Ban ghi NVS phai dung 16 byte");

uint8_t eventTypeToCode(const char* eventType) {
  if (strcmp(eventType, "DOOR_OPENED") == 0)    return 1;
  if (strcmp(eventType, "DOOR_CLOSED") == 0)    return 2;
  if (strcmp(eventType, "ITEM_IN") == 0)        return 3;
  if (strcmp(eventType, "ITEM_OUT") == 0)       return 4;
  if (strcmp(eventType, "DOOR_TIMEOUT") == 0)   return 5;
  if (strcmp(eventType, "LOCK_FAILED") == 0)    return 6;
  if (strcmp(eventType, "BOOT") == 0)           return 7;
  if (strcmp(eventType, "CARD_READ_FAIL") == 0) return 8;
  return 0;
}

const char* codeToEventType(uint8_t code) {
  switch (code) {
    case 1: return "DOOR_OPENED";
    case 2: return "DOOR_CLOSED";
    case 3: return "ITEM_IN";
    case 4: return "ITEM_OUT";
    case 5: return "DOOR_TIMEOUT";
    case 6: return "LOCK_FAILED";
    case 7: return "BOOT";
    case 8: return "CARD_READ_FAIL";
    default: return "BOOT";
  }
}

uint8_t calcChecksum(const ban_ghi_t* r) {
  const uint8_t* b = (const uint8_t*)r;
  uint8_t x = 0;
  for (int i = 0; i < 16; i++) {
    if (i == 3) continue;
    x ^= b[i];
  }
  return x;
}

// ==============================================================================
// 1. MODULE ÂM THANH / CẢNH BÁO (ĐÃ TẮT THEO CONFIG)
// ==============================================================================
void beep(int ms = 80) {
#if ENABLE_BUZZER
  digitalWrite(BUZZER_PIN, HIGH);
  delay(ms);
  digitalWrite(BUZZER_PIN, LOW);
#endif
}

void beepDouble() {
#if ENABLE_BUZZER
  beep(60);
  delay(60);
  beep(60);
#endif
}

void beepError() {
#if ENABLE_BUZZER
  beep(200);
  delay(100);
  beep(200);
#endif
}

// ==============================================================================
// 2. MODULE HIỂN THỊ OLED GME12864-49 (128x64 I2C)
// ==============================================================================
void displayInit() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
#if defined(USE_LCD1602_I2C)
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Smart Locker");
  lcd.setCursor(0, 1);
  lcd.print("Khoi dong...");
#elif defined(USE_OLED_SSD1306)
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3D)) {
      Serial.println("[OLED] Loi: Khong tim thay man hinh OLED GME12864-49!");
    }
  }
  display.clearDisplay();
  display.fillRect(0, 0, 128, 15, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
  display.setCursor(16, 4);
  display.println("SMART LOCKER IoT");
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(16, 32);
  display.println("Dang khoi dong...");
  display.display();
#endif
}

// Hiển thị màn hình thông báo 3 dòng rõ ràng trên OLED
void showStepScreen(const char* title, const char* line1, const char* line2 = "", const char* line3 = "") {
  Serial.printf("[OLED] [%s] %s | %s | %s\n", title, line1, line2, line3);
#if defined(USE_LCD1602_I2C)
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1);
  lcd.setCursor(0, 1);
  lcd.print(strlen(line2) > 0 ? line2 : title);
#elif defined(USE_OLED_SSD1306)
  display.clearDisplay();
  display.fillRect(0, 0, 128, 14, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
  display.setCursor(6, 3);
  display.println(title);

  display.setTextColor(SSD1306_WHITE);
  display.setCursor(2, 20);
  display.println(line1);
  if (strlen(line2) > 0) {
    display.setCursor(2, 35);
    display.println(line2);
  }
  if (strlen(line3) > 0) {
    display.setCursor(2, 50);
    display.println(line3);
  }
  display.display();
#endif
}

void showMessage(const char* line1, const char* line2 = "") {
  showStepScreen("SMART LOCKER", line1, line2, "");
}

// Màn hình chờ: Báo rõ "MỜI QUÉT THẺ" và hiển thị trạng thái thực tế của 2 ngăn
void showIdleStatus() {
#if defined(USE_OLED_SSD1306)
  display.clearDisplay();

  // Thanh banner nổi bật nhắc người dùng quét thẻ
  display.fillRect(0, 0, 128, 15, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
  display.setCursor(10, 4);
  display.println(">> MOI QUET THE <<");

  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 20);
  display.printf("Ngan 1:%-4s|%-5s", lastDoorClosed[1] ? "DONG" : "MO", lastHasItem[1] ? "CO DO" : "TRONG");

  display.setCursor(0, 34);
  display.printf("Ngan 2:%-4s|%-5s", lastDoorClosed[2] ? "DONG" : "MO", lastHasItem[2] ? "CO DO" : "TRONG");

  display.drawFastHLine(0, 47, 128, SSD1306_WHITE);
  display.setCursor(4, 52);
  display.println("Quet the: Gui/Lay do");
  display.display();
#else
  showMessage("Moi quet the!", "Gui / Lay do");
#endif
}

// ==============================================================================
// 3. MODULE THỜI GIAN VÀ BỘ ĐẾM NVS (ISO 8601 & REQUEST_ID)
// ==============================================================================
void setupTime() {
  configTime(7 * 3600, 0, "pool.ntp.org", "time.google.com");
  Serial.print("[TIME] Dang dong bo gio NTP...");
  struct tm timeinfo;
  int retry = 0;
  while (!getLocalTime(&timeinfo) && retry < 15) {
    Serial.print(".");
    delay(400);
    retry++;
  }
  Serial.println();
}

uint32_t getCurrentUnixTime() {
  time_t now;
  time(&now);
  if (now < 1700000000) {
    return 1794900000 + (millis() / 1000);
  }
  return (uint32_t)now;
}

void formatUnixToIso8601(uint32_t ts, char* buffer, size_t maxLen) {
  time_t raw = (time_t)(ts + 7 * 3600);
  struct tm* ti = gmtime(&raw);
  strftime(buffer, maxLen, "%Y-%m-%dT%H:%M:%S+07:00", ti);
}

void getDeviceTime(char* buffer, size_t maxLen) {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    formatUnixToIso8601(getCurrentUnixTime(), buffer, maxLen);
    return;
  }
  strftime(buffer, maxLen, "%Y-%m-%dT%H:%M:%S+07:00", &timeinfo);
}

uint32_t nextSeqNumber() {
  preferences.begin("locker", false);
  uint32_t seq = preferences.getUInt("req_seq", 0);
  seq++;
  if (seq > 999999) seq = 1;
  preferences.putUInt("req_seq", seq);
  preferences.end();
  return seq;
}

void formatRequestId(uint32_t seq, char* buffer, size_t maxLen) {
  snprintf(buffer, maxLen, "%s-%06u", DEVICE_ID, seq);
}

void getNextRequestId(char* buffer, size_t maxLen) {
  formatRequestId(nextSeqNumber(), buffer, maxLen);
}

// ==============================================================================
// 4. HÀNG ĐỢI SỰ KIỆN OFFLINE TRONG NVS (GỬI BÙ QUA /events/batch)
// ==============================================================================
uint16_t getPendingLogCount() {
  preferences.begin("locker", true);
  uint16_t head = preferences.getUShort("log_head", 0);
  uint16_t tail = preferences.getUShort("log_tail", 0);
  preferences.end();
  if (tail >= head) return tail - head;
  return (200 - head) + tail;
}

void saveOfflineEvent(uint8_t eventTypeCode, uint8_t compartment, bool hasItem, bool doorClosed, uint32_t sessionId, uint32_t unixTime, uint32_t seq) {
  ban_ghi_t rec;
  rec.event_type  = eventTypeCode;
  rec.compartment = compartment;
  rec.flags       = (hasItem ? 0x01 : 0x00) | (doorClosed ? 0x02 : 0x00) | 0x08;
  rec.checksum    = 0;
  rec.session_id  = sessionId;
  rec.device_time = unixTime;
  rec.req_seq     = seq;
  rec.checksum    = calcChecksum(&rec);

  preferences.begin("locker", false);
  uint16_t head = preferences.getUShort("log_head", 0);
  uint16_t tail = preferences.getUShort("log_tail", 0);

  char key[12];
  snprintf(key, sizeof(key), "log_%03u", tail);
  preferences.putBytes(key, &rec, sizeof(ban_ghi_t));

  uint16_t nextTail = (tail + 1) % 200;
  if (nextTail == head) {
    head = (head + 1) % 200;
    preferences.putUShort("log_head", head);
  }
  preferences.putUShort("log_tail", nextTail);
  preferences.end();
}

// ==============================================================================
// 5. MODULE PHẦN CỨNG: KHÓA ĐIỆN LY-03, CẢM BIẾN CÓ ĐỒ (IR), REED SWITCH (MC-38)
// ==============================================================================
bool checkHasItem(int compartment) {
  int pin = (compartment == 1) ? IR_SENSOR_COMP_1 : IR_SENSOR_COMP_2;
  int val = digitalRead(pin);
  return (val == IR_DETECTED_LEVEL);
}

// Đọc Reed Switch MC-38 (tự động nhận diện dù dây thứ 2 nối vào GND hay 3.3V)
bool readRawDoorClosed(int pin) {
  pinMode(pin, INPUT_PULLUP);
  delayMicroseconds(80);
  int vUp = digitalRead(pin);

  pinMode(pin, INPUT_PULLDOWN);
  delayMicroseconds(80);
  int vDown = digitalRead(pin);

  pinMode(pin, INPUT_PULLUP);
  return (vUp == vDown);
}

bool checkDoorClosed(int compartment) {
  int pin = (compartment == 1) ? DOOR_PIN_COMP_1 : DOOR_PIN_COMP_2;
  bool s1 = readRawDoorClosed(pin);
  delay(20);
  bool s2 = readRawDoorClosed(pin);
  return (s1 == s2) ? s1 : s2;
}

void setupHardware() {
  pinMode(LOCK_PIN_COMP_1, OUTPUT);
  pinMode(LOCK_PIN_COMP_2, OUTPUT);
  digitalWrite(LOCK_PIN_COMP_1, RELAY_INACTIVE_LEVEL);
  digitalWrite(LOCK_PIN_COMP_2, RELAY_INACTIVE_LEVEL);

  pinMode(IR_SENSOR_COMP_1, INPUT_PULLUP);
  pinMode(IR_SENSOR_COMP_2, INPUT_PULLUP);

  pinMode(DOOR_PIN_COMP_1, INPUT_PULLUP);
  pinMode(DOOR_PIN_COMP_2, INPUT_PULLUP);

#if ENABLE_BUZZER
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
#endif

  for (int c = 1; c <= 2; c++) {
    lastDoorClosed[c] = checkDoorClosed(c);
    lastHasItem[c]    = checkHasItem(c);
  }
}

// Cấp điện 12V trong khoảng ngắn (unlockMs = 800ms) để chốt LY-03 thụt vào mở cửa,
// sau đó tự động ngắt điện ngay để lò xo đẩy chốt ra sẵn sàng khóa lại khi đóng cửa.
void triggerUnlock(int compartment, unsigned int unlockMs) {
  if (compartment != 1 && compartment != 2) return;

  int pin = (compartment == 1) ? LOCK_PIN_COMP_1 : LOCK_PIN_COMP_2;
  if (unlockMs < 300) unlockMs = DEFAULT_UNLOCK_MS;
  if (unlockMs > MAX_UNLOCK_MS) unlockMs = MAX_UNLOCK_MS;

  Serial.printf("[LOCK LY-03] Mo khoa Ngan %d (%u ms)\n", compartment, unlockMs);
  digitalWrite(pin, RELAY_ACTIVE_LEVEL);
  delay(unlockMs);
  digitalWrite(pin, RELAY_INACTIVE_LEVEL);
  Serial.printf("[LOCK LY-03] Da ngat dien Ngan %d (chot tu tho ra nho lo xo)\n", compartment);
}

// Đọc nhanh xem có thẻ RFID đang đặt trên đầu đọc RC522 hay không (dùng khi quẹt thẻ gộp phí)
bool pollRfidUid(char* outUid) {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return false;
  }
  if (rfid.uid.size != 4) {
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    return false;
  }
  snprintf(outUid, 9, "%02X%02X%02X%02X",
           rfid.uid.uidByte[0], rfid.uid.uidByte[1],
           rfid.uid.uidByte[2], rfid.uid.uidByte[3]);
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  return true;
}

// ==============================================================================
// 6. MODULE GIAO TIẾP HTTP API VỚI BACKEND
// ==============================================================================
String postHttp(const char* endpoint, const String& jsonPayload) {
  if (WiFi.status() != WL_CONNECTED) return "";

  HTTPClient http;
  char url[128];
  snprintf(url, sizeof(url), "%s%s", BACKEND_BASE_URL, endpoint);

  http.begin(url);
  http.setTimeout(5000);
  http.addHeader("Content-Type", "application/json");

  char authHeader[64];
  snprintf(authHeader, sizeof(authHeader), "Device %s", DEVICE_TOKEN);
  http.addHeader("Authorization", authHeader);

  int httpCode = http.POST(jsonPayload);
  String response = "";

  if (httpCode > 0 && httpCode < 500) {
    response = http.getString();
    if (response.length() <= 2048) {
      Serial.printf("[HTTP POST %s] %d -> %s\n", endpoint, httpCode, response.c_str());
    } else {
      response = "";
    }
  } else {
    Serial.printf("[HTTP POST %s] Loi: %d\n", endpoint, httpCode);
  }

  http.end();
  return response;
}

String getHttp(const char* endpointWithQuery) {
  if (WiFi.status() != WL_CONNECTED) return "";

  HTTPClient http;
  char url[128];
  snprintf(url, sizeof(url), "%s%s", BACKEND_BASE_URL, endpointWithQuery);

  http.begin(url);
  http.setTimeout(5000);
  char authHeader[64];
  snprintf(authHeader, sizeof(authHeader), "Device %s", DEVICE_TOKEN);
  http.addHeader("Authorization", authHeader);

  int httpCode = http.GET();
  String response = "";

  if (httpCode > 0 && httpCode < 500) {
    response = http.getString();
    if (response.length() <= 2048) {
      Serial.printf("[HTTP GET %s] %d -> %s\n", endpointWithQuery, httpCode, response.c_str());
    } else {
      response = "";
    }
  }

  http.end();
  return response;
}

void flushOfflineEvents() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (getPendingLogCount() == 0) return;

  preferences.begin("locker", false);
  uint16_t head = preferences.getUShort("log_head", 0);
  uint16_t tail = preferences.getUShort("log_tail", 0);

  StaticJsonDocument<4096> batchDoc;
  batchDoc["device_id"] = DEVICE_ID;
  JsonArray arr = batchDoc.createNestedArray("events");

  uint16_t count = 0;
  uint16_t cursor = head;
  while (cursor != tail && count < 20) {
    char key[12];
    snprintf(key, sizeof(key), "log_%03u", cursor);
    ban_ghi_t rec;
    size_t len = preferences.getBytes(key, &rec, sizeof(ban_ghi_t));
    if (len == sizeof(ban_ghi_t) && calcChecksum(&rec) == rec.checksum) {
      JsonObject ev = arr.createNestedObject();
      char reqId[24];
      char devTime[32];
      formatRequestId(rec.req_seq, reqId, sizeof(reqId));
      formatUnixToIso8601(rec.device_time, devTime, sizeof(devTime));

      ev["device_id"]        = DEVICE_ID;
      ev["request_id"]       = reqId;
      ev["device_time"]      = devTime;
      ev["event_type"]       = codeToEventType(rec.event_type);
      ev["session_id"]       = rec.session_id;
      ev["compartment"]      = rec.compartment;
      ev["has_item"]         = (rec.flags & 0x01) != 0;
      ev["firmware_version"] = (rec.event_type == 7) ? FIRMWARE_VERSION : "";
      count++;
    }
    cursor = (cursor + 1) % 200;
  }

  if (count == 0) {
    preferences.putUShort("log_head", cursor);
    preferences.end();
    return;
  }

  String body;
  serializeJson(batchDoc, body);
  preferences.end();

  String resp = postHttp("/events/batch", body);
  if (resp.length() == 0) return;

  StaticJsonDocument<2048> respDoc;
  if (deserializeJson(respDoc, resp) == DeserializationError::Ok && (respDoc["success"] | false)) {
    preferences.begin("locker", false);
    preferences.putUShort("log_head", cursor);
    preferences.end();
  }
}

bool sendHardwareEvent(const char* eventType, uint32_t sessionId, uint8_t compartment, bool hasItem, const char* firmwareVer = "") {
  uint32_t seq = nextSeqNumber();
  uint32_t unixTime = getCurrentUnixTime();
  char reqId[24];
  char devTime[32];
  formatRequestId(seq, reqId, sizeof(reqId));
  getDeviceTime(devTime, sizeof(devTime));

  StaticJsonDocument<256> doc;
  doc["device_id"]        = DEVICE_ID;
  doc["request_id"]       = reqId;
  doc["device_time"]      = devTime;
  doc["event_type"]       = eventType;
  doc["session_id"]       = sessionId;
  doc["compartment"]      = compartment;
  doc["has_item"]         = hasItem;
  doc["firmware_version"] = firmwareVer;

  String body;
  serializeJson(doc, body);

  String resp = postHttp("/events", body);
  if (resp.length() == 0) {
    bool doorClosed = (compartment >= 1 && compartment <= 2) ? checkDoorClosed(compartment) : true;
    saveOfflineEvent(eventTypeToCode(eventType), compartment, hasItem, doorClosed, sessionId, unixTime, seq);
    return false;
  }

  StaticJsonDocument<512> respDoc;
  if (deserializeJson(respDoc, resp) != DeserializationError::Ok) return false;
  return respDoc["success"] | false;
}

void sendCommandAck(int commandId, const char* result) {
  char reqId[24];
  char devTime[32];
  getNextRequestId(reqId, sizeof(reqId));
  getDeviceTime(devTime, sizeof(devTime));

  StaticJsonDocument<256> doc;
  doc["device_id"]   = DEVICE_ID;
  doc["request_id"]  = reqId;
  doc["device_time"] = devTime;
  doc["result"]      = result;

  String body;
  serializeJson(doc, body);

  char endpoint[64];
  snprintf(endpoint, sizeof(endpoint), "/commands/%d/ack", commandId);
  postHttp(endpoint, body);
}

// ==============================================================================
// 7. QUY TRÌNH GỬI ĐỒ & LẤY ĐỒ CHUẨN THEO ĐỀ TÀI
// ==============================================================================
// Quy trình GỬI ĐỒ (DEPOSIT):
// 1. Mở khóa ngăn trống -> Báo DOOR_OPENED
// 2. Người dùng để đồ -> Cảm biến hồng ngoại xác nhận CÓ ĐỒ (ITEM_IN)
// 3. Người dùng đóng cửa (MC-38 đóng, hoặc tự động khóa sau 6s khi đã xác nhận có đồ)
// 4. Báo DOOR_CLOSED (has_item = true) -> Bắt đầu tính thời gian gửi đồ!
void runDepositFlow(int compartment, uint32_t sessionId, unsigned int unlockMs, unsigned int doorTimeoutSec) {
  activeSessionId[compartment] = sessionId;
  int otherComp = (compartment == 1) ? 2 : 1;
  bool otherInitialItem = checkHasItem(otherComp);

  char title[24];
  snprintf(title, sizeof(title), "GUI DO - NGAN SO %d", compartment);
  showStepScreen(title, "1. Dang mo khoa...", "Chot LY-03 thut vao", "Moi mo cua bo do!");

  // Kích xung 12V mở khóa LY-03 rồi ngắt điện ngay
  triggerUnlock(compartment, unlockMs);

  // Báo cửa mở lên Backend
  bool itemNow = checkHasItem(compartment) || (!otherInitialItem && checkHasItem(otherComp));
  lastDoorClosed[compartment] = false;
  lastHasItem[compartment]    = itemNow;
  sendHardwareEvent("DOOR_OPENED", sessionId, compartment, itemNow);

  unsigned long startTime     = millis();
  unsigned long itemPutMillis = itemNow ? millis() : 0;
  bool doorWasOpenedByReed    = !checkDoorClosed(compartment);

  while ((millis() - startTime) < (unsigned long)doorTimeoutSec * 1000) {
    // Nhận diện có đồ từ cảm biến của ngăn đang mở (hoặc nếu người dùng đặt trước mắt cảm biến còn lại đang trống)
    bool curItem = checkHasItem(compartment) || (!otherInitialItem && checkHasItem(otherComp));
    bool curDoor = checkDoorClosed(compartment);

    if (!curDoor) {
      doorWasOpenedByReed = true;
    }

    // Cập nhật khi cảm biến hồng ngoại phát hiện người dùng bỏ đồ vào / lấy ra
    if (curItem != lastHasItem[compartment]) {
      lastHasItem[compartment] = curItem;
      sendHardwareEvent(curItem ? "ITEM_IN" : "ITEM_OUT", sessionId, compartment, curItem);
      if (curItem) {
        itemPutMillis = millis();
      } else {
        itemPutMillis = 0;
      }
    }

    if (!curItem) {
      int remain = doorTimeoutSec - (int)((millis() - startTime) / 1000);
      char line3[24];
      snprintf(line3, sizeof(line3), "Cho bo do... (%ds)", remain > 0 ? remain : 0);
      showStepScreen(title, "2. Moi de do vao tu", "Cam bien: CHUA CO DO", line3);
    } else {
      // Đã xác nhận có đồ trong ngăn!
      // Nếu người dùng đã mở và đóng cửa MC-38, hoặc sau 4s xác nhận có đồ ổn định -> Chốt khóa tủ!
      unsigned long heldSec = (millis() - itemPutMillis) / 1000;
      if ((doorWasOpenedByReed && curDoor && heldSec >= 1) || (heldSec >= 4)) {
        break;
      }
      char line3[24];
      snprintf(line3, sizeof(line3), "Dong cua (tu khoa %lus)", 4 - heldSec);
      showStepScreen(title, "2. XAC NHAN CO DO!", "3. Moi dong cua lai", line3);
    }

    delay(150);
  }

  bool finalHasItem = checkHasItem(compartment) || (!otherInitialItem && checkHasItem(otherComp));
  lastDoorClosed[compartment] = checkDoorClosed(compartment);
  lastHasItem[compartment]    = finalHasItem;

  // Chốt sự kiện đóng & khóa tủ lên Backend
  sendHardwareEvent("DOOR_CLOSED", sessionId, compartment, finalHasItem);

  if (finalHasItem) {
    compStatus[compartment] = "OCCUPIED";
    showStepScreen(title, "DA DONG & KHOA TU!", "Cam bien: CO DO", "Bat dau tinh gio!");
  } else {
    activeSessionId[compartment] = 0;
    compStatus[compartment]      = "FREE";
    showStepScreen(title, "Khong co do!", "Da huy phien gui", "Ngan tro ve TRONG");
  }
  delay(2500);
}

// Quy trình LẤY ĐỒ (PICKUP):
// 1. Mở đúng ngăn đã gửi -> Hiển thị thời gian & phí sử dụng
// 2. Người dùng lấy đồ ra -> Cảm biến xác nhận đã lấy đồ (ITEM_OUT)
// 3. Đóng cửa -> Giải phóng ngăn về FREE
void runPickupFlow(int compartment, uint32_t sessionId, int durationMin, int fee, unsigned int unlockMs, unsigned int doorTimeoutSec) {
  int otherComp = (compartment == 1) ? 2 : 1;
  bool usePrimary = checkHasItem(compartment);
  bool useOther   = !usePrimary && checkHasItem(otherComp);

  char title[24];
  snprintf(title, sizeof(title), "LAY DO - NGAN SO %d", compartment);

  char feeLine[24];
  snprintf(feeLine, sizeof(feeLine), "TG: %dp | Phi: %dd", durationMin, fee);
  showStepScreen(title, feeLine, "Dang mo khoa tu...", "Moi lay do ra!");

  // Kích xung 12V mở khóa LY-03 rồi ngắt điện ngay
  triggerUnlock(compartment, unlockMs);

  bool itemNow = usePrimary ? checkHasItem(compartment) : (useOther ? checkHasItem(otherComp) : false);
  lastDoorClosed[compartment] = false;
  lastHasItem[compartment]    = itemNow;
  sendHardwareEvent("DOOR_OPENED", sessionId, compartment, itemNow);

  unsigned long startTime       = millis();
  unsigned long itemTakenMillis = !itemNow ? millis() : 0;
  bool doorWasOpenedByReed      = !checkDoorClosed(compartment);

  while ((millis() - startTime) < (unsigned long)doorTimeoutSec * 1000) {
    bool curItem = usePrimary ? checkHasItem(compartment) : (useOther ? checkHasItem(otherComp) : checkHasItem(compartment));
    bool curDoor = checkDoorClosed(compartment);

    if (!curDoor) {
      doorWasOpenedByReed = true;
    }

    if (curItem != lastHasItem[compartment]) {
      lastHasItem[compartment] = curItem;
      sendHardwareEvent(curItem ? "ITEM_IN" : "ITEM_OUT", sessionId, compartment, curItem);
      if (!curItem) {
        itemTakenMillis = millis();
      } else {
        itemTakenMillis = 0;
      }
    }

    if (curItem) {
      showStepScreen(title, feeLine, "Moi lay do ra ngoai", "Cam bien: CON DO");
    } else {
      unsigned long emptySec = (millis() - itemTakenMillis) / 1000;
      if ((doorWasOpenedByReed && curDoor && emptySec >= 1) || (emptySec >= 3)) {
        break;
      }
      char line3[24];
      snprintf(line3, sizeof(line3), "Dong cua (%lus)...", 3 - emptySec);
      showStepScreen(title, feeLine, "DA LAY DO RA!", line3);
    }

    delay(150);
  }

  bool finalHasItem = usePrimary ? checkHasItem(compartment) : (useOther ? checkHasItem(otherComp) : false);
  lastDoorClosed[compartment] = checkDoorClosed(compartment);
  lastHasItem[compartment]    = finalHasItem;

  sendHardwareEvent("DOOR_CLOSED", sessionId, compartment, finalHasItem);

  if (!finalHasItem) {
    activeSessionId[compartment] = 0;
    compStatus[compartment]      = "FREE";
    showStepScreen(title, "DA LAY DO XONG!", feeLine, "Cam on & Hen gap lai");
  } else {
    showStepScreen(title, "Van con do trong tu", "Giu nguyen phien!", "");
  }
  delay(2500);
}

// Xử lý lệnh mở ngăn từ xa trên Web Dashboard
void executePendingCommands(JsonArray commands) {
  for (JsonObject cmd : commands) {
    int cmdId    = cmd["command_id"] | 0;
    int comp     = cmd["compartment"] | 0;
    int unlockMs = cmd["unlock_ms"] | DEFAULT_UNLOCK_MS;
    if (cmdId <= 0 || (comp != 1 && comp != 2)) continue;

    Serial.printf("[ADMIN COMMAND] Mo thu cong ngan %d (ID %d)\n", comp, cmdId);
    sendCommandAck(cmdId, "DONE");
    runPickupFlow(comp, activeSessionId[comp], 0, 0, unlockMs, DEFAULT_DOOR_TIMEOUT_SEC);
    showIdleStatus();
  }
}

void sendBootEvent() {
  Serial.println("[SYSTEM] Gui su kien BOOT...");
  sendHardwareEvent("BOOT", 0, 0, false, FIRMWARE_VERSION);
}

void syncWithBackend() {
  flushOfflineEvents();

  char endpoint[64];
  snprintf(endpoint, sizeof(endpoint), "/sync?device_id=%s", DEVICE_ID);
  String resp = getHttp(endpoint);
  if (resp.length() == 0) return;

  StaticJsonDocument<1024> doc;
  if (deserializeJson(doc, resp) != DeserializationError::Ok) return;
  if (!(doc["success"] | false)) return;

  JsonObject data = doc["data"];
  JsonArray comps = data["compartments"];
  for (JsonObject c : comps) {
    int num             = c["number"] | 0;
    const char* st      = c["status"] | "FREE";
    bool srvDoorClosed  = c["door_closed"] | true;
    uint32_t srvSession = c["session_id"] | 0;

    if (num >= 1 && num <= 2) {
      activeSessionId[num] = srvSession;
      compStatus[num]      = String(st);
      bool hwDoorClosed    = checkDoorClosed(num);
      bool hwHasItem       = checkHasItem(num);
      lastDoorClosed[num]  = hwDoorClosed;
      lastHasItem[num]     = hwHasItem;

      if (!SIMULATE_DOOR_SENSORS && (srvDoorClosed != hwDoorClosed)) {
        sendHardwareEvent(hwDoorClosed ? "DOOR_CLOSED" : "DOOR_OPENED", srvSession, num, hwHasItem);
      }
    }
  }

  JsonArray commands = data["pending_commands"];
  executePendingCommands(commands);
}

void sendHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    return;
  }

  flushOfflineEvents();

  StaticJsonDocument<256> doc;
  doc["device_id"]     = DEVICE_ID;
  doc["uptime_sec"]    = millis() / 1000;
  doc["rssi"]          = WiFi.RSSI();
  doc["free_heap"]     = ESP.getFreeHeap();
  doc["pending_count"] = getPendingLogCount();

  String body;
  serializeJson(doc, body);

  String resp = postHttp("/heartbeat", body);
  if (resp.length() == 0) return;

  StaticJsonDocument<512> respDoc;
  if (deserializeJson(respDoc, resp) == DeserializationError::Ok && (respDoc["success"] | false)) {
    JsonArray commands = respDoc["data"]["pending_commands"];
    executePendingCommands(commands);
  }
}

void monitorSensors() {
  if (SIMULATE_DOOR_SENSORS) return;

  for (int c = 1; c <= 2; c++) {
    bool nowDoorClosed = checkDoorClosed(c);
    bool nowHasItem    = checkHasItem(c);

    if (nowDoorClosed != lastDoorClosed[c]) {
      lastDoorClosed[c] = nowDoorClosed;
      showIdleStatus();
      sendHardwareEvent(nowDoorClosed ? "DOOR_CLOSED" : "DOOR_OPENED", activeSessionId[c], c, nowHasItem);
      showIdleStatus();
    }

    if (nowHasItem != lastHasItem[c]) {
      lastHasItem[c] = nowHasItem;
      showIdleStatus();
      sendHardwareEvent(nowHasItem ? "ITEM_IN" : "ITEM_OUT", activeSessionId[c], c, nowHasItem);
      showIdleStatus();
    }
  }
}

// ==============================================================================
// 8. XỬ LÝ QUÉT THẺ RFID (POST /scan)
// ==============================================================================
void processCardScan(const char* cardUid) {
  Serial.printf("\n================ QUET THE: %s ================\n", cardUid);
  showStepScreen("DANG XAC THUC THE", "Ma the RFID:", cardUid, "Ket noi he thong...");

  char reqId[24];
  char devTime[32];
  getNextRequestId(reqId, sizeof(reqId));
  getDeviceTime(devTime, sizeof(devTime));

  StaticJsonDocument<256> reqDoc;
  reqDoc["device_id"]   = DEVICE_ID;
  reqDoc["card_uid"]    = cardUid;
  reqDoc["request_id"]  = reqId;
  reqDoc["device_time"] = devTime;

  String body;
  serializeJson(reqDoc, body);

  String resp = postHttp("/scan", body);
  if (resp.length() == 0) {
    showStepScreen("LOI KET NOI", "Khong goi duoc API", "Kiem tra Wi-Fi/IP", "");
    delay(2000);
    return;
  }

  StaticJsonDocument<768> doc;
  if (deserializeJson(doc, resp) != DeserializationError::Ok) {
    showStepScreen("LOI DU LIEU", "Phan hoi JSON loi", "", "");
    delay(2000);
    return;
  }

  bool success = doc["success"] | false;
  if (!success) {
    const char* errCode = doc["error_code"] | "UNKNOWN";
    const char* errMsg  = doc["message"] | "Loi thao tac";
    Serial.printf("[SCAN ERROR] %s: %s\n", errCode, errMsg);

    if (strcmp(errCode, "TOO_SOON") == 0) {
      showStepScreen("THONG BAO", "Khoa vua mo xong", "Vui long doi 3 giay", "roi quet lai the!");
    } else if (strcmp(errCode, "NO_FREE_COMPARTMENT") == 0) {
      showStepScreen("HET NGAN TRONG", "Ca 2 ngan deu bận", "Vui long quay lai", "sau!");
    } else if (strcmp(errCode, "CARD_BLOCKED") == 0) {
      showStepScreen("THE BI KHOA", cardUid, "Lien he quan tri", "vien!");
    } else {
      showStepScreen("THONG BAO", errMsg, cardUid, "");
    }
    delay(2500);
    return;
  }

  JsonObject data         = doc["data"];
  const char* action      = data["action"] | "";
  uint32_t sessionId      = data["session_id"] | 0;
  int compartment         = data["compartment"] | 0;
  unsigned int unlockMs   = data["unlock_ms"] | DEFAULT_UNLOCK_MS;
  unsigned int timeoutSec = data["timeout_sec"] | DEFAULT_DOOR_TIMEOUT_SEC;
  int durationMin         = data["duration_min"] | 0;
  int fee                 = data["fee"] | 0;

  // 1. GỬI ĐỒ: Tự chọn ngăn trống -> Mở khóa -> Để đồ -> Cảm biến xác nhận -> Đóng tủ -> Tính giờ
  if (strcmp(action, "DEPOSIT") == 0) {
    runDepositFlow(compartment, sessionId, unlockMs, timeoutSec);
  }
  // 2. LẤY ĐỒ: Tìm đúng ngăn đã gửi -> Mở tủ -> Hiển thị thời gian & phí -> Lấy đồ -> Giải phóng ngăn
  else if (strcmp(action, "PICKUP") == 0) {
    runPickupFlow(compartment, sessionId, durationMin, fee, unlockMs, timeoutSec);
  }
  // 3. CÓ PHÍ SỬ DỤNG: Hiển thị thời gian + phí -> Thanh toán QR hoặc Quét lại thẻ để gộp phí -> Mở tủ
  else if (strcmp(action, "PAYMENT") == 0) {
    const char* qr    = data["qr"] | "";
    int payTimeoutSec = data["pay_timeout_sec"] | 120;

    char title[24];
    snprintf(title, sizeof(title), "PHI NGAN %d: %dd", compartment, fee);
    char line1[24];
    snprintf(line1, sizeof(line1), "Thoi gian: %d phut", durationMin);
    showStepScreen(title, line1, "Quet lai the: Gop phi", "Hoac tra QR tren Web");

    unsigned long payStart = millis();
    unsigned long lastPoll = 0;
    bool paidSuccess = false;

    while ((millis() - payStart) < (unsigned long)payTimeoutSec * 1000) {
      // A. Cho phép quẹt lại đúng thẻ đó lần 2 để GỘP PHÍ vào thẻ Sinh viên / Bãi xe và mở tủ ngay!
      if ((millis() - payStart) > 1500) {
        char secondUid[9];
        if (pollRfidUid(secondUid)) {
          Serial.printf("[PAYMENT] Quet the gop phi: %s\n", secondUid);
          processCardScan(secondUid);
          return;
        }
      }

      // B. Kiểm tra trạng thái thanh toán QR (/payment/check) mỗi 2 giây
      if (millis() - lastPoll >= PAYMENT_POLL_MS) {
        lastPoll = millis();

        char chkReqId[24];
        char chkTime[32];
        getNextRequestId(chkReqId, sizeof(chkReqId));
        getDeviceTime(chkTime, sizeof(chkTime));

        StaticJsonDocument<256> chkDoc;
        chkDoc["device_id"]   = DEVICE_ID;
        chkDoc["request_id"]  = chkReqId;
        chkDoc["device_time"] = chkTime;
        chkDoc["session_id"]  = sessionId;

        String chkBody;
        serializeJson(chkDoc, chkBody);

        String chkResp = postHttp("/payment/check", chkBody);
        if (chkResp.length() > 0) {
          StaticJsonDocument<512> chkResDoc;
          if (deserializeJson(chkResDoc, chkResp) == DeserializationError::Ok && (chkResDoc["success"] | false)) {
            if (chkResDoc["data"]["paid"] | false) {
              paidSuccess = true;
              int openComp          = chkResDoc["data"]["compartment"] | compartment;
              unsigned int openMs   = chkResDoc["data"]["unlock_ms"] | DEFAULT_UNLOCK_MS;
              unsigned int openTout = chkResDoc["data"]["timeout_sec"] | DEFAULT_DOOR_TIMEOUT_SEC;

              runPickupFlow(openComp, sessionId, durationMin, fee, openMs, openTout);
              break;
            }
          }
        }
      }
      delay(80);
    }

    if (!paidSuccess) {
      showStepScreen("HET GIO THANH TOAN", "Giao dich tam dung", "Quet lai the de mo", "");
      delay(2000);
    }
  }
}

// ==============================================================================
// 9. SETUP & LOOP
// ==============================================================================
void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println("\n==================================================");
  Serial.println("   HE THONG TU GUI DO THONG MINH IoT (2 NGAN)     ");
  Serial.println("==================================================");

  displayInit();
  setupHardware();

  SPI.begin(RFID_SCK_PIN, RFID_MISO_PIN, RFID_MOSI_PIN, RFID_SS_PIN);
  rfid.PCD_Init();

  showStepScreen("KET NOI WI-FI", "Dang ket noi mang:", WIFI_SSID, "Vui long cho...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int wifiRetry = 0;
  while (WiFi.status() != WL_CONNECTED && wifiRetry < 30) {
    delay(500);
    Serial.print(".");
    wifiRetry++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    showStepScreen("WI-FI THANH CONG", "IP ESP32:", WiFi.localIP().toString().c_str(), "Dang dong bo Server");
  } else {
    showStepScreen("LOI WI-FI", "Khong ket noi duoc", WIFI_SSID, "Chay che do Offline");
  }
  delay(1200);

  setupTime();
  sendBootEvent();
  syncWithBackend();

  showIdleStatus();
}

void loop() {
  if (millis() - lastHeartbeatMillis >= HEARTBEAT_INTERVAL) {
    lastHeartbeatMillis = millis();
    sendHeartbeat();
  }

  if (millis() - lastSensorPollMillis >= SENSOR_POLL_INTERVAL_MS) {
    lastSensorPollMillis = millis();
    monitorSensors();
  }

  char cardUid[9];
  if (!pollRfidUid(cardUid)) {
    delay(30);
    return;
  }

  if (millis() - lastCardScanMillis < CARD_SCAN_COOLDOWN_MS) {
    return;
  }
  lastCardScanMillis = millis();

  processCardScan(cardUid);
  showIdleStatus();
}
