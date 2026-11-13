import {useEffect,useRef} from 'react';
/** Call immediately, pause when tab hidden, refresh on visibility return. */
export function usePolling(callback,intervalMs,enabled=true){
 const cb=useRef(callback);cb.current=callback;
 useEffect(()=>{
  if(!enabled)return;
  let running=false;
  async function run(){if(document.hidden||running)return;running=true;try{await cb.current();}finally{running=false;}}
  function onVisible(){if(!document.hidden)void run();}
  void run();const timer=setInterval(run,intervalMs);
  document.addEventListener('visibilitychange',onVisible);
  return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',onVisible);};
 },[intervalMs,enabled]);
}
