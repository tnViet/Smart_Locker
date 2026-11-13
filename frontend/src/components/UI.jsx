import React from 'react';
import {AlertTriangle,ArrowRight,Box,CheckCircle2,ChevronRight,Clock3,DoorOpen,LockKeyhole,RefreshCw,WifiOff} from 'lucide-react';
import {money,label,stateClass,fmtDuration,shortTime} from '../utils/format';
export function Badge({value,children,variant}){return <span className={`badge ${variant||stateClass(value)}`}><span className="badge-dot"/>{children||label(value)}</span>}
export function PageHeader({eyebrow,title,description,actions}){return <div className="page-head"><div><div className="eyebrow">{eyebrow||'SMART LOCKER / TV7'}</div><h1>{title}</h1>{description&&<p>{description}</p>}</div>{actions&&<div className="page-actions">{actions}</div>}</div>}
export function SectionHeader({title,subtitle,action}){return <div className="section-header"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div>{action}</div>}
export function StatCard({label,value,detail,icon:Icon,tone='teal'}){return <div className="stat-card"><div className="stat-row"><span className="stat-label">{label}</span><span className={`stat-icon tone-${tone}`}>{Icon&&<Icon size={21} strokeWidth={1.8}/>}</span></div><div className="stat-value">{value}</div><div className="stat-detail">{detail}</div></div>}
export function ErrorBox({message,onRetry}){return <div className="error-box" role="alert"><AlertTriangle size={20}/><span>{message||'Không thể tải dữ liệu.'}</span>{onRetry&&<button className="btn btn-ghost small" onClick={onRetry}><RefreshCw size={14}/> Thử lại</button>}</div>}
export function EmptyState({title='Chưa có dữ liệu',description='Dữ liệu sẽ xuất hiện khi hệ thống ghi nhận hoạt động.',icon:Icon=Box}){return <div className="empty-state"><div className="empty-icon"><Icon size={28}/></div><h3>{title}</h3><p>{description}</p></div>}
export function Loading({text='Đang tải dữ liệu...'}){return <div className="loading-state"><span className="spinner"/>{text}</div>}
export function Button({children,icon:Icon,variant='primary',className='',...props}){return <button className={`btn btn-${variant} ${className}`} {...props}>{Icon&&<Icon size={17}/>}<span>{children}</span></button>}
export function Modal({title,description,children,onClose,footer}){
 return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose?.()}}><div className="modal" role="dialog" aria-modal="true" aria-label={title}><div className="modal-header"><div><h2>{title}</h2>{description&&<p>{description}</p>}</div><button className="icon-btn" onClick={onClose} aria-label="Đóng">×</button></div><div className="modal-body">{children}</div>{footer&&<div className="modal-footer">{footer}</div>}</div></div>
}
export function CompartmentCard({item,compact=false,action}){
 const status=item?.status||'FREE';return <div className={`comp-card status-${status.toLowerCase()} ${compact?'compact':''}`}>
  <div className="comp-top"><div className="comp-icon"><DoorOpen size={22}/></div><span className="comp-number">NGĂN {String(item.number).padStart(2,'0')}</span><Badge value={status}/></div>
  <div className="comp-inner"><div className="comp-visual"><div className="comp-shelf"><LockKeyhole size={25}/></div></div><div className="comp-caption">{status==='FREE'?'Sẵn sàng tiếp nhận':status==='OCCUPIED'?`Phiên #${item.session?.id||'—'}`:status==='ERROR'?'Cần quản trị viên xử lý':'Đang chờ thao tác cửa'}</div></div>
  <div className="comp-footer"><span>{item.door_closed?'Cửa đang đóng':'Cửa đang mở'}<br/>{item.has_item?'Có vật dụng':'Không có vật dụng'}</span>{item.session&&<span className="comp-fee">{money(item.session.current_fee)}<small>phí tạm tính</small></span>}</div>
  {action&&<div className="comp-actions">{action}</div>}
 </div>;
}
export function KeyValue({title,value}){return <div className="key-value"><span>{title}</span><strong>{value??'—'}</strong></div>}
export function AppNotice({children}){return <div className="notice"><AlertTriangle size={17}/><div>{children}</div></div>}
export function Table({headings,children}){return <div className="table-wrap"><table><thead><tr>{headings.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>}
