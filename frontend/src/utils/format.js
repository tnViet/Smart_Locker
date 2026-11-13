export const money=(n=0)=>`${new Intl.NumberFormat('vi-VN').format(Number(n)||0)} đ`;
export const number=(n=0)=>new Intl.NumberFormat('vi-VN').format(Number(n)||0);
export function dateTime(value){if(!value)return '—';const d=new Date(value);return Number.isNaN(d.getTime())?'—':d.toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit',year:'numeric'});}
export function shortTime(value){if(!value)return '—';const d=new Date(value);return Number.isNaN(d.getTime())?'—':d.toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'});}
export function onlyDate(value){if(!value)return '—';const d=new Date(value);return Number.isNaN(d.getTime())?'—':d.toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'});}
export const codeLabel={FREE:'Còn trống',OPEN:'Đang mở cửa',OCCUPIED:'Đang sử dụng',ERROR:'Gặp sự cố',CREATED:'Đã tạo phiên',RELEASING:'Đang lấy đồ',CLOSED:'Đã kết thúc',CANCELLED:'Đã hủy',NONE:'Chưa phát sinh',PENDING:'Chờ thanh toán',PAID:'Đã thanh toán',EXPIRED:'Hết hạn',DONE:'Đã thực hiện',FAILED:'Thất bại',REJECTED:'Từ chối',STUDENT:'Thẻ sinh viên',PARKING:'Thẻ gửi xe',LOCAL:'Thẻ nội bộ',PAYMENT:'Chờ thanh toán'};
export const label=code=>codeLabel[code]||code||'—';
export const stateClass=code=>{
 if(['FREE','PAID','DONE','CLOSED'].includes(code))return 'success';
 if(['OCCUPIED','CREATED'].includes(code))return 'info';
 if(['OPEN','RELEASING','PENDING'].includes(code))return 'warning';
 if(['ERROR','FAILED','CANCELLED','REJECTED','EXPIRED'].includes(code))return 'danger';
 return 'neutral';
};
export function apiError(error){return error?.response?.data?.message||error?.response?.data?.error||error?.message||'Không thể kết nối máy chủ';}
export function fmtDuration(min){const m=Number(min)||0;return m>=60?`${Math.floor(m/60)} giờ ${m%60} phút`:`${m} phút`;}
export const toISODate=(date=new Date())=>date.toLocaleDateString('en-CA',{timeZone:'Asia/Ho_Chi_Minh'});
