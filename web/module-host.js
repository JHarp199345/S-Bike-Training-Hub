/* Trusted Hub wrapper. The game runs on its own origin and receives only selected data. */
(()=>{'use strict';
 let frame=document.getElementById('module-game');const status=document.getElementById('status');
 const config=JSON.parse(document.getElementById('module-config').textContent);
 let token=null,capabilities={},closed=false,pollBusy=false,ready=false,gameOrigin='null';
 const post=m=>frame.contentWindow?.postMessage({type:'sbike-host',...m},gameOrigin==='null'?'*':gameOrigin);
 // Chrome 142+ blocks an opaque sandbox frame from loading anything from this computer (Local Network Access), so on
 // this computer the game gets its own name, <pack>.game.localhost on the Hub's port (module_sandbox.game_pack): a
 // separate site the browser walls off. Browsers that can't reach that name (Safari), and devices reaching the Hub
 // over the network, keep the opaque frame.
 const dev=new URLSearchParams(location.search).has('dev')?'?dev=1':'';
 const own=location.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(location.hostname)&&/^[a-z0-9-]{1,60}$/.test(config.id);
 const gameBase=own?`http://${config.id}.game.localhost${location.port?':'+location.port:''}`:'';
 (async()=>{
  if(gameBase){
   try{
    await fetch(gameBase+'/web/module-runtime.js',{mode:'no-cors',cache:'no-store'});
    // a fresh frame: one that started opaque stays blank when its sandbox is loosened afterwards (Chrome 152)
    const own=frame.cloneNode(false);own.setAttribute('sandbox','allow-scripts allow-same-origin');
    own.src=`${gameBase}/modes/${config.id}/sandbox${dev}#hub=${encodeURIComponent(location.origin)}`;
    gameOrigin=gameBase;frame.replaceWith(own);frame=own;return;
   }catch(e){}
  }
  frame.src=`/modes/${config.id}/sandbox${dev}`;
 })();
 async function api(action,args={}){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),4000);
  try{
   const r=await fetch('/api/modes/session',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action,...(token?{token}:{}),...args}),signal:controller.signal});
   const body=await r.json();if(!r.ok)throw Error(body.error||'Game request refused');return body;
  }finally{clearTimeout(timer);}
 }
 async function poll(){
  if(closed||!token||pollBusy)return;pollBusy=true;
  try{const out=await api('snapshot');post({action:'snapshot',data:out.data,connected:true,
   lean:capabilities.lean?(window.sbike?.lean||0):0,leanSource:capabilities.lean?(window.sbike?.leanSource||''):''});}
  catch(e){post({action:'snapshot',data:{},connected:false});}
  finally{pollBusy=false;}
 }
 const initialized=api('open',{id:config.id}).then(out=>{
  token=out.token;capabilities=out.capabilities;return poll();
 }).catch(e=>{closed=true;status.textContent=e.message;});
 addEventListener('message',async e=>{
  if(e.source===frame.contentWindow&&e.origin===gameOrigin){
   const m=e.data;
   if(!m||m.type!=='sbike-module'||!Number.isSafeInteger(m.id)||m.id<0||m.id>1e9)return;
   if(!['ready','start','grade','mark','end','recenter'].includes(m.action))return;
   const args=m.args;
   if(!args||typeof args!=='object'||Array.isArray(args))return;
   await initialized;if(closed||!token)return;
   let result;
   try{
    if(m.action==='ready'){ready=true;status.hidden=true;await poll();result={ok:true,capabilities};}
    else if(m.action==='recenter'){if(!capabilities.lean)throw Error('Lean is not declared');window.sbike?.recenter?.();result={ok:true};}
    else if(m.action==='start'){if(Object.keys(args).length)throw Error('Unexpected game arguments');result=await api('start');}
    else if(m.action==='grade'){
     if(!capabilities.hills||Object.keys(args).join()!=='value'||!Number.isFinite(args.value))throw Error('Invalid hill request');
     result=await api('grade',{value:args.value});
    }else{
     if(Object.keys(args).join()!=='text'||typeof args.text!=='string'||args.text.length>120)throw Error('Invalid game text');
     result=await api(m.action,{text:args.text});
    }
   }catch(err){result={ok:false,why:err.message};}
   post({action:'reply',id:m.id,result});
  }
  // Existing game menu navigation is forwarded as a fixed set of UI actions.
  if(e.source!==frame.contentWindow||e.origin!==gameOrigin)return;
  if(['hub-leave-mode','hub-ride-setup','hub-ride-fullscreen'].includes(e.data?.type)){
   if(parent===window && ['hub-leave-mode','hub-ride-setup'].includes(e.data.type))
    location.assign('/ride?setup=1');
   else parent.postMessage({type:e.data.type},location.origin);
  }
 });
 setInterval(()=>{if(ready)poll();},100);
 addEventListener('pagehide',()=>{
  closed=true;if(token)navigator.sendBeacon('/api/modes/session',new Blob([JSON.stringify({action:'close',token})],{type:'application/json'}));
 });
})();
