import React,{useCallback,useState} from 'react';
import {AlertOctagon,DoorOpen,Info,LockKeyhole,RefreshCw,RotateCcw} from 'lucide-react';
import {api} from '../api/client';
import {usePolling} from '../hooks/usePolling';
import {useAuth} from '../context/AuthContext';
import {useToast} from '../context/ToastContext';
import {apiError,money} from '../utils/format';
import {AppNotice,Badge,Button,CompartmentCard,ErrorBox,Loading,Modal,PageHeader,SectionHeader} from '../components/UI';
export default function Compartments(){
 const [items,setItems]=useState(null),[error,setError]=useState(''),[modal,setModal]=useState(null),[reason,setReason]=useState(''),[busy,setBusy]=useState(false);
 const {isAdmin}=useAuth(),toast=useToast();
 const reload=useCallback(async()=>{try{setItems(await api.compartments());setError('')}catch(e){setError(apiError(e))}},[]);
 usePolling(reload,3000);
 const act=async()=>{setBusy(true);try{
   if(modal.type==='open'){await api.adminOpen(modal.item.number,reason);toast('Đã xếp hàng lệnh mở. ESP32 nhận ở nhịp heartbeat tiếp theo.');}
   else{await api.adminReset(modal.item.number);toast(`Đã reset ngăn ${modal.item.number} về FREE`);}
   setModal(null);setReason('');await reload();
  }catch(e){toast(apiError(e),'error')}finally{setBusy(false)}};
 return <><PageHeader title="Quản lý ngăn tủ" eyebrow="LOCKER01 / COMPARTMENTS" description="Theo dõi cảm biến, trạng thái khóa và xử lý sự cố theo đúng quyền quản trị." actions={<Button icon={RefreshCw} variant="outline" onClick={reload}>Làm mới</Button>}/>
 <div className="info-strip"><Info size={18}/><span>Chỉ Backend được quyết định trạng thái ngăn. Dashboard hiển thị bốn trạng thái: FREE, OPEN, OCCUPIED, ERROR.</span></div>
 {error&&<ErrorBox message={error} onRetry={reload}/>}
 {!items?<Loading/>:<div className="comp-grid large">{items.map(item=><CompartmentCard key={item.number} item={item} action={isAdmin?<><Button icon={DoorOpen} variant="outline" disabled={item.status==='ERROR'} onClick={()=>{setReason('');setModal({type:'open',item})}}>Mở thủ công</Button><Button icon={RotateCcw} variant="soft" disabled={item.status!=='ERROR'} onClick={()=>setModal({type:'reset',item})}>Reset ngăn lỗi</Button></>:<span className="readonly-note"><LockKeyhole size={15}/> Tài khoản viewer chỉ có quyền xem</span>}/>)}</div>}
 <section className="panel help-panel"><SectionHeader title="Quy tắc thao tác" subtitle="Áp dụng theo thiết kế Backend của nhóm"/><div className="help-grid"><div><span>01</span><h3>Mở ngăn thủ công</h3><p>Lệnh được tạo ở Backend và chờ ESP32 nhận qua /heartbeat. Dashboard không trực tiếp cấp điện cho khóa.</p></div><div><span>02</span><h3>Ngăn lỗi</h3><p>Chỉ cho phép reset khi ngăn đang ERROR. Thao tác có thể kết thúc hoặc hủy phiên tương ứng.</p></div><div><span>03</span><h3>Bảo vệ dữ liệu</h3><p>Viewer chỉ được quan sát, các lệnh quản trị phải được Backend kiểm tra quyền và ghi nhận.</p></div></div></section>
 {modal&&<Modal title={modal.type==='open'?`Mở thủ công ngăn ${modal.item.number}`:`Xác nhận reset ngăn ${modal.item.number}`} description={modal.type==='open'?'Lệnh được đặt hàng chờ, không có tác dụng mở tức thì.':'Ngăn ERROR sẽ trở về FREE; phiên đang gắn có thể bị kết thúc.'} onClose={()=>setModal(null)} footer={<><Button variant="outline" onClick={()=>setModal(null)}>Hủy</Button><Button disabled={busy||(modal.type==='open'&&reason.trim().length<3)} onClick={act}>{busy?'Đang gửi...':modal.type==='open'?'Tạo lệnh mở':'Xác nhận reset'}</Button></>}>
 {modal.type==='open'?<div className="form-field"><label htmlFor="open-reason">Lý do mở ngăn (bắt buộc)</label><textarea id="open-reason" rows="3" value={reason} onChange={e=>setReason(e.target.value)} placeholder="Ví dụ: Hỗ trợ khách hàng lấy đồ bị kẹt..."/><small>Thao tác chỉ dành cho admin. Không mở ngăn khi đang ERROR.</small></div>:<AppNotice>Reset ngăn lỗi là thao tác quản trị có thể ảnh hưởng tới phiên sử dụng. Hãy kiểm tra thực tế trước khi xác nhận.</AppNotice>}</Modal>}
 </>;
}
