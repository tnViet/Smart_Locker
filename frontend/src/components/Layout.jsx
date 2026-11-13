import React,{useState} from 'react';
import {NavLink,Outlet,useLocation} from 'react-router-dom';
import {BarChart3,Boxes,DoorOpen,LayoutDashboard,LogOut,Menu,ShieldCheck,SlidersHorizontal,Users,Wifi,X} from 'lucide-react';
import {useAuth} from '../context/AuthContext';
const menu=[
 {to:'/',name:'Tổng quan',icon:LayoutDashboard},
 {to:'/compartments',name:'Ngăn tủ',icon:Boxes},
 {to:'/sessions',name:'Phiên gửi đồ',icon:DoorOpen},
 {to:'/users',name:'Người dùng & thẻ',icon:Users},
 {to:'/statistics',name:'Thống kê',icon:BarChart3},
 {to:'/devices',name:'Thiết bị IoT',icon:Wifi},
 {to:'/fee-rules',name:'Bảng giá',icon:SlidersHorizontal},
];
const titles={'/':'Tổng quan','/compartments':'Ngăn tủ','/sessions':'Phiên gửi đồ','/users':'Người dùng & thẻ','/statistics':'Thống kê','/devices':'Thiết bị IoT','/fee-rules':'Bảng giá'};
export default function Layout(){
 const [menuOpen,setMenuOpen]=useState(false);const loc=useLocation();const {auth,logout,isAdmin}=useAuth();
 return <div className="app-frame">
  <div className={`mobile-scrim ${menuOpen?'active':''}`} onClick={()=>setMenuOpen(false)}/>
  <aside className={`sidebar ${menuOpen?'show':''}`}>
   <div className="brand"><div className="brand-icon"><Boxes size={22}/></div><div className="brand-copy"><strong>LOCKER<span>IQ</span></strong><small>CONTROL CENTER</small></div><button className="mobile-close" onClick={()=>setMenuOpen(false)} aria-label="Đóng menu"><X size={18}/></button></div>
   <div className="sidebar-context"><span className="context-led"/><div><span>HỆ THỐNG ĐANG GIÁM SÁT</span><strong>Smart Locker · 2 ngăn</strong></div></div>
   <div className="side-caption">KHÔNG GIAN LÀM VIỆC</div>
   <nav className="sidebar-nav" aria-label="Điều hướng chính">{menu.map(({to,name,icon:Icon})=><NavLink key={to} to={to} end={to==='/'} onClick={()=>setMenuOpen(false)} className={({isActive})=>`side-link ${isActive?'active':''}`}><Icon size={19} strokeWidth={1.9}/><span>{name}</span></NavLink>)}</nav>
   <div className="sidebar-bottom"><div className="side-info"><ShieldCheck size={20}/><div><strong>Phiên quản trị</strong><small>{isAdmin?'Administrator':'Viewer · chỉ xem'}</small></div></div><p>Giao diện TV7 · Prototype IoT</p></div>
  </aside>
  <div className="app-body"><header className="topbar"><div className="top-left"><button className="hamburger" aria-label="Mở menu" onClick={()=>setMenuOpen(true)}><Menu size={22}/></button><div className="breadcrumb">Hệ thống / <strong>{titles[loc.pathname]||'Chi tiết'}</strong></div></div><div className="top-right"><div className="top-avatar">{auth?.username?.slice(0,1).toUpperCase()||'U'}</div><div className="top-user"><strong>{auth?.username||'Người dùng'}</strong><small>{isAdmin?'Quản trị viên':'Người xem'}</small></div><button className="logout-btn" title="Đăng xuất" aria-label="Đăng xuất" onClick={logout}><LogOut size={18}/></button></div></header>
   <main className="page-content"><Outlet/></main>
   <footer className="app-footer"><span>© 2026 Smart Locker · TV7 Frontend & Testing</span><span>Phiên bản 1.0.0 · Kết nối Backend</span></footer>
  </div>
 </div>;
}
