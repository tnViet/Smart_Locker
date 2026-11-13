# Hợp đồng API FE - Backend Django (TV6)

Bản Frontend chỉ **gọi** REST API; không chạy hoặc thay thế Django. Cần TV6 đối chiếu các request/response trước khi tích hợp E2E.

## Các endpoint Frontend sử dụng

- `POST /api/v1/auth/login`: nhận `access_token`, `role`, `expires_in` theo tài liệu nhóm.
- `GET /api/v1/compartments`.
- `GET /api/v1/sessions`, `GET /api/v1/sessions/{id}`, `POST /api/v1/sessions/{id}/pay`.
- `GET /api/v1/users`, `POST /api/v1/users`, `PATCH /api/v1/users/{id}`.
- `GET /api/v1/stats/overview`, `GET /api/v1/stats/revenue`.
- `GET /api/v1/devices`.
- `GET /api/v1/fee-rules`, `PATCH /api/v1/fee-rules`.
- `POST /api/v1/admin/open`, `POST /api/v1/admin/reset`.

Base URL ở `VITE_API_BASE_URL`, mặc định `/api/v1`. Với các API cần xác thực, Axios đính kèm `Authorization: Bearer <token>`.

`src/api/client.js` đang chấp nhận cấu trúc `{ "success": true, "data": ... }` và ném lỗi khi `success: false`. Nếu TV6 trả dạng khác cần chỉnh `req()`.

## Những chỗ cần kiểm chứng với code Django

1. Dữ liệu `/sessions`: giao diện kỳ vọng `{results, count, page, page_size}`; chi tiết gồm events và trường thanh toán.
2. Dữ liệu `/users`, `/devices`, `/stats/*`, `/fee-rules`: cấu trúc JSON chính xác phải đối chiếu Backend thực.
3. Các lệnh admin đang dùng `device_id: 'LOCKER01'`; cần xác nhận tên trường và giá trị có đúng hay không.
4. Viewer chỉ được xem; Backend phải kiểm quyền, không phụ thuộc vào việc ẩn nút tại FE.
5. Login sử dụng trường `access_token`, `role`, `expires_in` và username người đăng nhập. Thử thật với tài khoản do TV6 cấp.
6. Với URL Backend khác origin, cần CORS; mặc định Vite proxy HTTP `/api` sang `127.0.0.1:8000`.

## Phần không có trong gói này

Không có Mock Backend, không có route `/_demo/*`, không có Node Express hoặc server nguồn định danh ngoài. Gói FE không tự tạo dữ liệu mẫu hoặc cung cấp tài khoản đăng nhập.

Các dịch vụ ngoài sinh viên/thẻ gửi xe thuộc phạm vi tích hợp riêng với Backend, không phải API được gọi trực tiếp từ React Dashboard.
