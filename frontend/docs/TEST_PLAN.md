# Kế hoạch kiểm thử Frontend TV7

## Phạm vi

- React Dashboard, trạng thái ngăn, phiên gửi/lấy, người dùng/thẻ, thống kê doanh thu, trạng thái thiết bị, bảng giá.
- Xác thực JWT và phân quyền Admin/Viewer.
- Polling và lỗi mất kết nối Backend.
- Không bao gồm thử nghiệm ESP32, cảm biến hay hai hệ thống ngoài trong gói FE này.

## Kiểm thử độc lập

Chạy `npm test` để kiểm tra hàm tiền tệ, nhãn trạng thái, thời lượng, thông báo lỗi và dữ liệu thời gian trống/sai. Có thể chạy `npm run build` để kiểm tra cấu hình Vite và bundle.

## Checklist khi nhận Backend Django của TV6

1. **Đăng nhập:** Admin đúng thông tin -> nhận JWT và vào Dashboard; mật khẩu sai -> hiển thị lỗi; token hết hạn -> trở lại Login.
2. **Viewer:** Vào các trang được xem, nút Admin không khả dụng; thử API ghi dữ liệu bằng viewer phải được Backend trả 403.
3. **Ngăn tủ:** FREE/OPEN/OCCUPIED/ERROR hiển thị đúng; tự cập nhật mỗi 3 giây.
4. **Phiên gửi/lấy:** Lọc, phân trang, xem chi tiết; kiểm tra CREATED/OPEN/OCCUPIED/RELEASING/CLOSED/CANCELLED.
5. **Người dùng/thẻ:** Thêm thẻ hợp lệ, khóa/mở khóa, thông báo lỗi hợp lý.
6. **Thống kê:** Thay khoảng ngày; tổng doanh thu và biểu đồ nhất quán với API.
7. **Thiết bị:** Online/offline, heartbeat, RSSI, firmware hiển thị đúng; cập nhật mỗi 30 giây.
8. **Bảng giá:** Đọc và lưu với Admin; không ghi được bằng Viewer.
9. **Điều khiển:** Admin mở/reset ngăn -> Backend nhận đúng request; có thông báo khi lỗi.
10. **Mạng:** Backend mất kết nối -> hiển thị thông báo; phục hồi -> cập nhật lại; tab ẩn -> tạm dừng polling.

## Thu thập kết quả

Lập bảng *Mã TC / Phiên bản FE-BE / Bước thực hiện / Expected / Actual / Pass-Fail / Evidence*. Không ghi kết quả mô phỏng thành kết quả đo trên phần cứng thật.
