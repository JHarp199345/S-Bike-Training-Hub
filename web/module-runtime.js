/* Runs inside the game frame: its own <pack>.game.localhost origin, or an opaque one. No Hub credentials or tokens. */
(()=>{'use strict';
 const ownOrigin=new URL(location.href).origin;
 // On its own name the frame is told which Hub address embeds it (module-host.js); only this computer's names count.
 const hint=new URLSearchParams(location.hash.slice(1)).get('hub');
 const parentOrigin=hint&&/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$/.test(hint)?hint:ownOrigin;
 let data={},connected=false,last=0,seq=0;
 const pending=new Map();
 const send=(action,args={})=>new Promise(resolve=>{
  const id=++seq;
  const timer=setTimeout(()=>{pending.delete(id);resolve({ok:false,why:'Game connection timed out'});},5000);
  pending.set(id,{resolve,timer});
  parent.postMessage({type:'sbike-module',action,id,args},parentOrigin);
 });
 const bridge={snapshot:()=>({connected:connected&&performance.now()-last<3000,data}),request:send};
 Object.defineProperty(window,'SBikeBridge',{value:bridge,writable:false,configurable:false});
 window.sbike={lean:0,leanSource:'',recenter:()=>send('recenter')};
 addEventListener('message',e=>{
  if(e.source!==parent||e.origin!==parentOrigin||e.data?.type!=='sbike-host')return;
  const m=e.data;
  if(m.action==='snapshot'){
   data=m.data||{};connected=!!m.connected;last=performance.now();
   window.sbike.lean=Number.isFinite(m.lean)?Math.max(-1,Math.min(1,m.lean)):0;
   window.sbike.leanSource=typeof m.leanSource==='string'?m.leanSource:'';
  }else if(m.action==='reply'&&pending.has(m.id)){
   const p=pending.get(m.id);clearTimeout(p.timer);pending.delete(m.id);p.resolve(m.result);
  }
 });
 // Older official packs use HTTPRequest. This shim supplies only the same narrow
 // telemetry/commands; bypassing it is still blocked by CSP and the server gate.
 const originalFetch=window.fetch.bind(window);
 window.fetch=async(input,options={})=>{
  const url=new URL(typeof input==='string'?input:input.url,location.href);
  const method=(options.method||(input instanceof Request?input.method:'GET')).toUpperCase();
  if(url.origin===ownOrigin&&url.pathname==='/status'&&method==='GET')
   return new Response(JSON.stringify(data),{status:bridge.snapshot().connected?200:503,headers:{'Content-Type':'application/json'}});
  if(url.origin===ownOrigin&&url.pathname.startsWith('/mode/')&&method==='POST'){
   const parts=url.pathname.split('/').slice(2).map(decodeURIComponent);
   let result;
   if(parts[0]==='start')result=await send('start');
   else if(parts[0]==='grade')result=await send('grade',{value:Number(parts[1])});
   else if(parts[0]==='mark')result=await send('mark',{text:parts[1]||''});
   else if(parts[0]==='end')result=await send('end',{text:parts[1]||''});
   else result={ok:false,why:'Game request is not allowed'};
   return new Response(JSON.stringify(result),{headers:{'Content-Type':'application/json'}});
  }
  return originalFetch(input,options);
 };
 send('ready');
})();
