import axios from 'axios';
const baseURL=import.meta.env.VITE_API_BASE_URL||'/api/v1';
export const client=axios.create({baseURL,timeout:15000});
client.interceptors.request.use(config=>{
  const session=JSON.parse(sessionStorage.getItem('tv7_auth')||'null');
  if(session?.token)config.headers.Authorization=`Bearer ${session.token}`;
  return config;
});
client.interceptors.response.use(response=>response,err=>{
  if(err?.response?.status===401 && !String(err.config?.url||'').includes('/auth/login')){
    sessionStorage.removeItem('tv7_auth');
    window.dispatchEvent(new Event('tv7:unauthorized'));
  }
  return Promise.reject(err);
});
async function req(method,url,data,config={}){
 const result=await client.request({method,url,...(data!==undefined?{data}:{}),...config});
 const body=result.data;
 if(body && typeof body==='object'&&'success' in body){
  if(!body.success)throw new Error(body.message||body.error_code||'API error');
  return body.data;
 }
 return body;
}
export const api={
 login:(username,password)=>req('POST','/auth/login',{username,password}),
 compartments:()=>req('GET','/compartments'),
 sessions:(params={})=>req('GET','/sessions',undefined,{params}),
 session:id=>req('GET',`/sessions/${id}`),
 markPaid:id=>req('POST',`/sessions/${id}/pay`,{}),
 users:()=>req('GET','/users'),
 addUser:data=>req('POST','/users',data),
 setBlocked:(id,blocked)=>req('PATCH',`/users/${id}`,{blocked}),
 overview:()=>req('GET','/stats/overview'),
 revenue:(from,to)=>req('GET','/stats/revenue',undefined,{params:{from,to}}),
 devices:()=>req('GET','/devices'),
 feeRules:()=>req('GET','/fee-rules'),
 saveFeeRules:data=>req('PATCH','/fee-rules',data),
 adminOpen:(compartment,reason)=>req('POST','/admin/open',{device_id:'LOCKER01',compartment,reason}),
 adminReset:compartment=>req('POST','/admin/reset',{device_id:'LOCKER01',compartment}),
};
