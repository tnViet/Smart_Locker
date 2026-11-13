import React,{createContext,useContext,useState,useCallback} from 'react';
import {CheckCircle2,AlertCircle,Info,X} from 'lucide-react';
const ToastContext=createContext(null);
export function ToastProvider({children}){
 const [toasts,setToasts]=useState([]);
 const dismiss=useCallback(id=>setToasts(x=>x.filter(t=>t.id!==id)),[]);
 const toast=useCallback((message,type='success')=>{
  const id=Math.random().toString(36).slice(2);setToasts(x=>[...x,{id,message,type}]);
  setTimeout(()=>setToasts(x=>x.filter(t=>t.id!==id)),4400);
 },[]);
 return <ToastContext.Provider value={toast}>{children}<div className="toast-stack" aria-live="polite">{toasts.map(t=><div className={`toast-item ${t.type}`} key={t.id}>{t.type==='success'?<CheckCircle2 size={19}/>:t.type==='error'?<AlertCircle size={19}/>:<Info size={19}/>}<span>{t.message}</span><button aria-label="Đóng thông báo" onClick={()=>dismiss(t.id)}><X size={16}/></button></div>)}</div></ToastContext.Provider>;
}
export const useToast=()=>useContext(ToastContext);
