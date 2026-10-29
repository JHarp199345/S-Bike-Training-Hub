/* Trusted Hub wrapper. The game runs on its own origin and receives only selected data. */
(()=>{'use strict';
 let frame=document.getElementById('module-game');const status=document.getElementById('status');
 const config=JSON.parse(document.getElementById('module-config').textContent);
 let token=null,capabilities={},saves={},closed=false,pollBusy=false,ready=false,gameOrigin='null',alive=performance.now();
 const post=m=>frame.contentWindow?.postMessage({type:'sbike-host',...m},gameOrigin==='null'?'*':gameOrigin);
 // Chrome 142+ blocks an opaque sandbox frame from loading anything from this computer (Local Network Access), so on
 // this computer the game gets its own name, <pack>.game.localhost on the Hub's port (module_sandbox.game_pack): a
 // separate site the browser walls off. Browsers that can't reach that name (Safari), and devices reaching the Hub
 // over the network, keep the opaque frame.
 // A game loads exactly one page. If its frame loads another, the game is navigating somewhere (a way to carry the
 // readings it was given out in a web address), so it loses its connection and is taken off the screen.
 function guard(f){
  let loads=0;
  f.addEventListener('load',()=>{if(++loads>1)stopped('This game tried to leave its sandbox, so the Hub stopped it.');});
 }
 function stopped(why){
  if(closed)return;closed=true;ready=false;
  if(token)navigator.sendBeacon('/api/modes/session',new Blob([JSON.stringify({action:'close',token})],{type:'application/json'}));
  token=null;frame.remove();status.hidden=false;status.textContent=why;
 }
 const dev=new URLSearchParams(location.search).has('dev')?'?dev=1':'';
 const own=location.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(location.hostname)&&/^[a-z0-9-]{1,60}$/.test(config.id);
 const gameBase=own?`http://${config.id}.game.localhost${location.port?':'+location.port:''}`:'';
 (async()=>{
  if(gameBase){
   try{
    await fetch(gameBase+'/web/module-runtime.js',{mode:'no-cors',cache:'no-store'});
    // a fresh frame: one that started opaque stays blank when its sandbox is loosened afterwards (Chrome 152)
    const own=frame.cloneNode(false);own.setAttribute('sandbox','allow-scripts allow-same-origin');
    // Rules required of anything that loads in this frame (Chrome; module_sandbox.runtime_headers): the game's own page
    // accepts them; an outside page a game navigates to is refused, or, if it accepts, can run none of its own scripts.
    const files=`${gameBase}/modes/${config.id}/`,engine=`${gameBase}/module-engine/`;
    own.setAttribute('csp',`default-src 'none'; script-src 'unsafe-eval' 'wasm-unsafe-eval' ${engine} ${gameBase}/web/module-runtime.js ${gameBase}/web/module-start.js; `
     +`connect-src ${engine} ${files}; img-src data: blob: ${files}; media-src blob: ${files}; style-src 'unsafe-inline'; worker-src blob: ${engine}; `
     +`frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'`);
    own.src=`${gameBase}/modes/${config.id}/sandbox${dev}#hub=${encodeURIComponent(location.origin)}`;
    gameOrigin=gameBase;frame.replaceWith(own);frame=own;guard(own);return;
   }catch(e){}
  }
  frame.src=`/modes/${config.id}/sandbox${dev}`;guard(frame);
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
  token=out.token;capabilities=out.capabilities;saves=out.saves||{};return poll();
 }).catch(e=>{closed=true;status.textContent=e.message;});
 addEventListener('message',async e=>{
  if(e.source!==frame.contentWindow||e.origin!==gameOrigin)return;
  // The frame's own signals (module-runtime.js) and the existing game menu navigation, as a fixed set of UI actions.
  // Checked first: the request handling below returns on anything that isn't a game request.
  if(e.data?.type==='sbike-leaving'){stopped('This game tried to leave its sandbox, so the Hub stopped it.');return;}
  if(e.data?.type==='sbike-alive'){alive=performance.now();return;}
  if(['hub-leave-mode','hub-ride-setup','hub-ride-fullscreen'].includes(e.data?.type)){
   if(parent===window && ['hub-leave-mode','hub-ride-setup'].includes(e.data.type))
    location.assign('/ride?setup=1');
   else parent.postMessage({type:e.data.type},location.origin);
   return;
  }
  {
   const m=e.data;
   if(!m||m.type!=='sbike-module'||!Number.isSafeInteger(m.id)||m.id<0||m.id>1e9)return;
   if(!['ready','start','grade','mark','end','recenter','save'].includes(m.action))return;
   const args=m.args;
   if(!args||typeof args!=='object'||Array.isArray(args))return;
   await initialized;if(closed||!token)return;
   let result;
   try{
    if(m.action==='ready'){ready=true;status.hidden=true;await poll();result={ok:true,capabilities,saves};}
    else if(m.action==='save'){
     if(Object.keys(args).sort().join()!=='file,text'||typeof args.file!=='string'||typeof args.text!=='string')throw Error('Invalid save');
     result=await api('save',{file:args.file,text:args.text});
    }
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
 });
 setInterval(()=>{if(ready)poll();},100);
 // Watchdog: the frame's heartbeat (module-runtime.js) stops when a game freezes or hogs the page; after 20 s of
 // silence while you're looking at it, the Hub closes the game. Hidden tabs are slowed by the browser, so they reset it.
 addEventListener('visibilitychange',()=>{alive=performance.now();});
 setInterval(()=>{if(!closed&&document.visibilityState==='visible'&&performance.now()-alive>20000)
  stopped('This game stopped responding, so the Hub closed it.');},1000);
 addEventListener('pagehide',()=>{
  closed=true;if(token)navigator.sendBeacon('/api/modes/session',new Blob([JSON.stringify({action:'close',token})],{type:'application/json'}));
 });
})();
