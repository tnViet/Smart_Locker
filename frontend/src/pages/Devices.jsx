import React,{useCallback,useState} from 'react';
import {Activity,Box,Clock3,Cpu,HardDrive,RefreshCw,Radio,Wifi,WifiOff} from 'lucide-react';
import {api} from '../api/client';
import {usePolling} from '../hooks/usePolling';
import {dateTime,number,apiError,fmtDuration} from '../utils/format';
import {Badge,Button,EmptyState,ErrorBox,Loading,PageHeader,SectionHeader,StatCard,Table} from '../components/UI';
export default function Devices(){
 const [items,setItems]=useState(null),[error,setError]=useState('');
 const load=useCallback(async()=>{try{const r=await api.devices();setItems(Array.isArray(r)?r:r?.results||[]);setError('')}catch(e){setError(apiError(e))}},[]);
 usePolling(load,30000);
 return <><PageHeader title="Thiết bị IoT" eyebrow="GIÁM SÁT ESP32 / DEVICES" description="Độ ổn định kết nối dựa trên heartbeat, phiên bản firmware và thông số thiết bị." actions={<Button variant="outline" icon={RefreshCw} onClick={load}>Làm mới</Button>}/>
 <div className="info-strip"><Radio size={18}/><span>Backend đánh dấu thiết bị online khi nhận heartbeat trong 90 giây gần nhất; Dashboard hỏi lại /devices mỗi 30 giây.</span></div>
 {error&&<ErrorBox message={error} onRetry={load}/>}{!items?<Loading/>:items.length===0?<EmptyState title="Chưa ghi nhận thiết bị"/>:items.map(d=><React.Fragment key={d.device_id}>
 <section className="panel"><div className="device-page-hero"><div className="device-page-graphic"><Cpu size={47}/><span className={d.online?'glow on':'glow'}/></div><div><div className="eyebrow">ESP32 / EDGE DEVICE</div><h2>{d.device_id}</h2><p>Thiết bị điều khiển hai ngăn tủ với RC522, MC-38, IR và khóa điện.</p></div><div className="device-status"><Badge variant={d.online?'success':'danger'}>{d.online?'Đang trực tuyến':'Đang ngoại tuyến'}</Badge></div></div></section>
 <div className="stats-grid"><StatCard label="Kết nối" value={d.online?'Online':'Offline'} detail="Từ trạng thái heartbeat của Backend" icon={d.online?Wifi:WifiOff} tone={d.online?'teal':'amber'}/><StatCard label="Sóng Wi-Fi" value={d.rssi!=null?`${d.rssi} dBm`:'—'} detail="RSSI trong heartbeat gần nhất" icon={Radio} tone="blue"/><StatCard label="Bộ nhớ heap trống" value={d.free_heap!=null?`${number(Math.round(d.free_heap/1024))} KB`:'—'} detail="Dung lượng ghi nhận gần nhất" icon={HardDrive} tone="purple"/><StatCard label="Sự kiện chờ gửi" value={d.pending_count??'—'} detail="Số bản ghi trong NVS chưa đồng bộ" icon={Activity} tone="amber"/></div>
 <section className="panel"><SectionHeader title="Chi tiết kết nối" subtitle="Thông tin do thiết bị gửi lên Backend"/><div className="kv-grid device-kv"><div className="key-value"><span>Mã thiết bị</span><strong>{d.device_id}</strong></div><div className="key-value"><span>Firmware version</span><strong>{d.firmware_version||'Chưa ghi nhận'}</strong></div><div className="key-value"><span>Heartbeat cuối</span><strong>{dateTime(d.last_heartbeat_at)}</strong></div><div className="key-value"><span>Uptime gần nhất</span><strong>{d.uptime_sec!=null?fmtDuration(Math.floor(d.uptime_sec/60)):'—'}</strong></div></div>{!d.online&&<div className="inline-warning">Thiết bị mất kết nối hoặc quá hạn heartbeat. Trạng thái ngăn vẫn giữ theo dữ liệu Backend, không tự chuyển thành ERROR.</div>}</section>
 </React.Fragment>)}
 </>;
}
