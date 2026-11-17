import React,{createContext,useCallback,useContext,useEffect,useMemo,useState} from 'react';
import {api} from '../api/client';
const AuthContext=createContext(null);
function initialAuth(){
 try{const x=JSON.parse(sessionStorage.getItem('tv7_auth')||'null');if(x?.expiresAt>Date.now())return x;}
 catch{}sessionStorage.removeItem('tv7_auth');return null;
}
export function AuthProvider({children}){
 const [auth,setAuth]=useState(initialAuth);
 const logout=useCallback(()=>{sessionStorage.removeItem('tv7_auth');setAuth(null);},[]);
 useEffect(()=>{const callback=()=>setAuth(null);window.addEventListener('tv7:unauthorized',callback);return()=>window.removeEventListener('tv7:unauthorized',callback)},[]);
 useEffect(()=>{
  if(!auth?.expiresAt)return;
  const timeout=setTimeout(logout,Math.max(0,auth.expiresAt-Date.now()));
  return()=>clearTimeout(timeout);
 },[auth,logout]);
 const login=useCallback(async(username,password)=>{
  const data=await api.login(username,password);
  const next={token:data.access_token,role:data.role,username,expiresAt:Date.now()+(data.expires_in||28800)*1000};
  sessionStorage.setItem('tv7_auth',JSON.stringify(next));setAuth(next);return next;
 },[]);
 const value=useMemo(()=>({auth,login,logout,isAdmin:auth?.role==='admin',isViewer:auth?.role==='viewer'}),[auth,login,logout]);
 return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
export const useAuth=()=>useContext(AuthContext);
