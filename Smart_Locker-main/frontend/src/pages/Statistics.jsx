import React,{useCallback,useEffect,useMemo,useState} from 'react';
import {BarChart3,CalendarDays,CircleDollarSign,RefreshCw,TrendingUp,Users} from 'lucide-react';
import {ResponsiveContainer,BarChart,Bar,XAxis,YAxis,CartesianGrid,Tooltip} from 'recharts';
import {api} from '../api/client';
import {money,number,toISODate,apiError} from '../utils/format';
import {Button,EmptyState,ErrorBox,Loading,PageHeader,SectionHeader,StatCard,Table} from '../components/UI';
const backDays=n=>toISODate(new Date(Date.now()-(n-1)*86400000));
export default function Statistics(){
 const [from,setFrom]=useState(backDays(7)),[to,setTo]=useState(toISODate()),[rows,setRows]=useState(null),[overview,setOverview]=useState(null),[error,setError]=useState('');
 const load=useCallback(async()=>{try{setError('');const [r,s]=await Promise.all([api.revenue(from,to),api.overview()]);setRows(Array.isArray(r)?r:r?.results||[]);setOverview(s)}catch(e){setError(apiError(e))}},[from,to]);
 useEffect(()=>{void load()},[load]);
 const total=useMemo(()=>(rows||[]).reduce((a,b)=>a+Number(b.revenue||0),0),[rows]);
 return <><PageHeader title="Thống kê & doanh thu" eyebrow="PHÂN TÍCH HOẠT ĐỘNG / ANALYTICS" description="Theo dõi doanh thu, số phiên và mức sử dụng của mô hình tủ thông minh." actions={<Button variant="outline" icon={RefreshCw} onClick={load}>Tải lại báo cáo</Button>}/>
 <div className="stats-grid"><StatCard label="Doanh thu trong khoảng" value={rows?money(total):'—'} detail="Tổng doanh thu từ các phiên đã đóng" icon={CircleDollarSign} tone="teal"/><StatCard label="Phiên hôm nay" value={overview?.sessions_today??'—'} detail="Tổng phiên tạo trong ngày" icon={Users} tone="blue"/><StatCard label="Tỷ lệ lấp đầy" value={overview?`${overview.occupancy_rate}%`:'—'} detail="Theo trạng thái OCCUPIED hiện tại" icon={TrendingUp} tone="purple"/><StatCard label="Ngăn gặp lỗi" value={overview?.errors??'—'} detail="Số ngăn ở trạng thái ERROR" icon={BarChart3} tone="amber"/></div>
 <section className="panel"><SectionHeader title="Doanh thu theo ngày" subtitle="Lấy từ GET /stats/revenue khi người dùng mở trang hoặc đổi bộ lọc"/><div className="filterbar"><div className="form-field compact-field"><label htmlFor="from">Từ ngày</label><input id="from" type="date" value={from} max={to} onChange={e=>setFrom(e.target.value)}/></div><div className="form-field compact-field"><label htmlFor="to">Đến ngày</label><input id="to" type="date" value={to} min={from} onChange={e=>setTo(e.target.value)}/></div><div className="filter-chips"><button onClick={()=>{setFrom(backDays(7));setTo(toISODate())}}>7 ngày</button><button onClick={()=>{setFrom(backDays(30));setTo(toISODate())}}>30 ngày</button></div></div>
 {error&&<ErrorBox message={error} onRetry={load}/>}{!rows?<Loading/>:rows.length===0?<EmptyState title="Không có số liệu trong khoảng này"/>:<div className="chart-wrap"><ResponsiveContainer width="100%" height={320}><BarChart data={rows} margin={{top:16,right:12,left:8,bottom:12}}><CartesianGrid vertical={false} strokeDasharray="4 4" stroke="#e9eef3"/><XAxis dataKey="date" tick={{fontSize:11,fill:'#78909f'}} tickFormatter={v=>v.slice(5)} axisLine={false} tickLine={false}/><YAxis tick={{fontSize:11,fill:'#78909f'}} tickFormatter={v=>v>=1000?`${Math.round(v/1000)}k`:v} axisLine={false} tickLine={false}/><Tooltip formatter={v=>[money(v),'Doanh thu']} labelFormatter={v=>`Ngày ${v}`}/><Bar name="Doanh thu" dataKey="revenue" fill="#089a8e" radius={[6,6,0,0]} maxBarSize={52}/></BarChart></ResponsiveContainer></div>}
 </section>
 <section className="panel table-panel"><SectionHeader title="Bảng số liệu theo ngày" subtitle="Các giá trị lấy từ API; không phải chỉ số đo độ trễ thực nghiệm"/>{rows&&rows.length>0?<Table headings={['NGÀY','SỐ PHIÊN KẾT THÚC','DOANH THU']}>{rows.map(r=><tr key={r.date}><td>{r.date}</td><td>{number(r.sessions)}</td><td><strong>{money(r.revenue)}</strong></td></tr>)}</Table>:<EmptyState title="Chưa có dữ liệu"/>}</section>
 </>;
}
