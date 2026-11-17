# Smart Locker - Frontend (TV7)

Giao diện quản trị **React 19 + Vite 6** của hệ thống tủ gửi đồ thông minh 2 ngăn.
Đây là **Frontend thuần** để đưa vào GitHub chung của nhóm và kết nối với **Backend Django TV6**.

**Bản này đã bỏ toàn bộ** `server/`, Mock Backend Node/Express, các API `/_demo/*`, trang "Phòng thử mô phỏng", và các chức năng đăng nhập bằng tài khoản Demo. Không có máy chủ Backend trong ZIP này.

## Cài đặt và chạy trên Windows

Yêu cầu Node.js 20.19+ (khuyến nghị Node 22 LTS), npm.

Mở VS Code trong thư mục `frontend`, sau đó chạy:

```powershell
npm install
copy .env.example .env
npm run dev
```

Mở `http://localhost:5173`.

Hoặc nháy đúp `RUN_TV7_WINDOWS.bat` để cài thư viện nếu chưa có và mở Vite.

**Quan trọng:** Đây không phải ứng dụng độc lập. Để đăng nhập và xem dữ liệu thực, cần chạy Django Backend trên `http://127.0.0.1:8000` với các endpoint tương thích. Nếu Django chưa chạy, giao diện đăng nhập có thể mở nhưng API sẽ báo lỗi; điều này là bình thường.

## Cấu hình kết nối Django

Trong `.env` dùng mặc định:

```dotenv
VITE_API_BASE_URL=/api/v1
```

`vite.config.js` chuyển tiếp các request `/api` tới `http://127.0.0.1:8000`. Nếu Django chạy máy khác, đặt:

```dotenv
VITE_API_BASE_URL=http://IP_MAY_BACKEND:8000/api/v1
```

Khi gọi trực tiếp Backend ở máy/port khác cần thiết lập CORS đúng trên Django; khởi động lại Vite sau khi thay `.env`.

Không commit `.env` có secret hoặc thông tin nội bộ. File `.env.example` có thể đưa lên Git.

## Các trang hiện có

| Đường dẫn | Vai trò |
|---|---|
| `/login` | Đăng nhập bằng tài khoản của Django, nhận JWT |
| `/` | Dashboard tổng quan, trạng thái 2 ngăn, thống kê, phiên đang hoạt động |
| `/compartments` | Trạng thái ngăn và thao tác quản trị (Admin) |
| `/sessions` | Lịch sử và chi tiết phiên gửi/lấy đồ |
| `/users` | Quản lý người dùng/thẻ |
| `/statistics` | Thống kê, biểu đồ doanh thu |
| `/devices` | Tình trạng ESP32, heartbeat |
| `/fee-rules` | Quản lý bảng giá |

Các request tập trung ở `src/api/client.js`: Axios, header `Authorization: Bearer`, xử lý phản hồi và lỗi 401. **Không còn endpoint `/_demo/*`.** Polling Dashboard: ngăn mỗi 3s, phiên 10s, thống kê và thiết bị 30s, tạm dừng khi tab ẩn.

## Kiểm tra mã nguồn

```powershell
npm test
npm run build
```

`npm test` kiểm tra các hàm hiển thị/định dạng phía FE. `npm run build` tạo thư mục `dist/` (đã được gitignore).

## Cấu trúc

```text
frontend/
  src/
    api/client.js            # Gọi REST API của Django
    context/                 # JWT, trạng thái đăng nhập, toast
    components/              # Layout, thành phần UI
    hooks/usePolling.js      # Đồng bộ dữ liệu định kỳ
    pages/                   # 8 màn hình (kể cả Login)
    styles/main.css          # Giao diện responsive
    utils/format.js          # Tiền, thời gian và nhãn trạng thái
    main.jsx                 # Router
  tests/frontend.test.mjs
  docs/
  .env.example
  .gitignore
  package.json
  vite.config.js
  index.html
  RUN_TV7_WINDOWS.bat
```

## Phối hợp với TV6

- **TV7:** trang React, Axios, trải nghiệm Dashboard, kiểm thử và đối chiếu dữ liệu.
- **TV6:** Django API, PostgreSQL, JWT, quyền và logic phiên/ngăn/phí. Frontend không trực tiếp điều khiển phần cứng hay lưu trạng thái nghiệp vụ vào DB.
- Có một số response API mới có danh sách endpoint nhưng chưa chốt đủ JSON; xem `docs/CONTRACT_NOTES.md`. Cần kiểm tra thực tế trước khi tuyên bố FE đã tích hợp thành công.
- Dịch vụ định danh/thanh toán ngoài (student/parking) đã được **loại khỏi gói FE này**. Nếu nhóm cần dùng, hãy đưa thành dự án/thư mục riêng; giữ lại nguồn từ ZIP cũ.

## Đẩy nguyên folder lên GitHub nhóm

Đặt **nguyên folder `frontend/`** trong thư mục `Smart_Locker` đã `git clone`, không chép từng file:

```powershell
cd C:\Users\ADMIN\Smart_Locker
git switch -c feature/frontend-tv7
git add frontend
git commit -m "feat: add TV7 React frontend"
git push -u origin feature/frontend-tv7
```

Nếu nhánh đã tạo trước đó, bỏ qua lệnh `git switch -c ...`. Tạo Pull Request từ `feature/frontend-tv7` tới `main`/`develop` theo quy định nhóm.
