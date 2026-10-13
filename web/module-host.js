/* Trusted Hub wrapper. The game has an opaque origin and receives only selected data. */
(()=>{'use strict';
 const frame=document.getElementById('module-game'),status=document.getElementById('status');
 const config=JSON.parse(document.getElementById('module-config').textContent);
 let token=null,capabilities={},closed=false,pollBusy=false,ready=false;
 const post=m=>frame.contentWindow?.postMessage({type:'sbike-host',...m},'*');
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
  token=out.token;capabilities=out.capabilities;frame.src=frame.dataset.src;return poll();
 }).catch(e=>{closed=true;status.textContent=e.message;
  if(config.license_required)document.getElementById('game-activation').hidden=false;});
 const activation=document.getElementById('game-activation');
 activation?.addEventListener('submit',async e=>{
  e.preventDefault();const button=activation.querySelector('button'),message=document.getElementById('game-activation-message');
  button.disabled=true;message.textContent='Checking license…';
  try{
   const r=await fetch('/api/modes/activate',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:config.id,license_key:document.getElementById('game-license-key').value})});
   const result=await r.json();if(!r.ok)throw Error(result.error||'Activation failed');
   document.getElementById('game-license-key').value='';location.reload();
  }catch(error){message.textContent=error.message;}finally{button.disabled=false;}
 });
 addEventListener('message',async e=>{
  if(e.source===frame.contentWindow&&e.origin==='null'){
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
  if(e.source!==frame.contentWindow||e.origin!=='null')return;
  if(['hub-leave-mode','hub-ride-setup','hub-ride-fullscreen'].includes(e.data?.type)){
   if(parent===window && ['hub-leave-mode','hub-ride-setup'].includes(e.data.type))
    location.assign('/ride?setup=1');
   else parent.postMessage({type:e.data.type},location.origin);
  }
 });
 setInterval(poll,100);
 addEventListener('pagehide',()=>{
  closed=true;if(token)navigator.sendBeacon('/api/modes/session',new Blob([JSON.stringify({action:'close',token})],{type:'application/json'}));
 });
})();
