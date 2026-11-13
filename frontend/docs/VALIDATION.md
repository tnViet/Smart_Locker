# Kiểm tra bản Frontend thuần

- Đã xóa `server/` và `Simulator.jsx`.
- Đã xóa 9 API `/_demo/*` và mọi import/route/menu phụ thuộc.
- Script `npm run dev` chỉ chạy Vite; `package.json` không có Express, CORS, QRCode, concurrently.
- Đã chạy `npm test`: 5/5 bài kiểm thử FE đạt. Đã kiểm tra tĩnh: không còn import/route/API phụ thuộc Mock Server. Chưa chạy được `npm run build` vì môi trường đóng gói chưa cài các package npm; người dùng chạy `npm install` rồi `npm run build` trên máy của mình.
- Kết nối với Django thật **chưa được kiểm chứng** nếu chưa có source/instance Backend của TV6.
