/* Runs inside the game frame: its own <pack>.game.localhost origin, or an opaque one. No Hub credentials or tokens. */
(()=>{'use strict';
 const ownOrigin=new URL(location.href).origin;
 // The real Hub window, kept before game code runs: a game can replace window.parent, but not this.
 const hub=parent,tell=(m)=>hub.postMessage(m,parentOrigin);
 // On its own name the frame is told which Hub address embeds it (module-host.js); only this computer's names count.
 const hint=new URLSearchParams(location.hash.slice(1)).get('hub');
 const parentOrigin=hint&&/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$/.test(hint)?hint:ownOrigin;
 // No peer connections: WebRTC can reach any server, outside the frame's connect-src, and browsers ignore the CSP
 // webrtc directive (sandbox probe, 2026-10-29). This runs before any game code, which then finds nothing to call.
 for(const k of ['RTCPeerConnection','webkitRTCPeerConnection','RTCDataChannel','RTCSessionDescription','RTCIceCandidate','RTCRtpSender','RTCRtpReceiver','RTCRtpTransceiver']){
  try{delete window[k];Object.defineProperty(window,k,{value:undefined,writable:false,configurable:false});}catch(e){}
 }
 // Volume: every sound a game makes passes through a Hub-owned limiter on its way out (gain, then a hard compressor),
 // so no game can blast the speakers. Media elements are capped too. Originals are kept here, before game code runs.
 if(window.AudioNode&&window.AudioDestinationNode){
  const connect=AudioNode.prototype.connect,gain=BaseAudioContext.prototype.createGain,comp=BaseAudioContext.prototype.createDynamicsCompressor;
  const limiters=new WeakMap();
  const limiter=ctx=>{let l=limiters.get(ctx);if(!l){
   const g=gain.call(ctx),c=comp.call(ctx);g.gain.value=0.8;
   c.threshold.value=-12;c.knee.value=0;c.ratio.value=20;c.attack.value=0.002;c.release.value=0.1;
   connect.call(g,c);connect.call(c,ctx.destination);limiters.set(ctx,l=g);}return l;};
  Object.defineProperty(AudioNode.prototype,'connect',{configurable:false,enumerable:true,writable:false,value:function(dest,...rest){
   return connect.call(this,dest instanceof AudioDestinationNode?limiter(dest.context):dest,...rest);}});
 }
 if(window.HTMLMediaElement){const d=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'volume');
  if(d&&d.set)Object.defineProperty(HTMLMediaElement.prototype,'volume',{configurable:false,enumerable:d.enumerable,get:d.get,set(v){d.set.call(this,Math.min(0.8,Number(v)||0));}});}
 // No frames inside the game: a blank inner frame would hand back a fresh WebRTC (and anything else removed above),
 // and the CSP's frame-src doesn't cover blank frames. Every way the page can create or insert a frame is refused,
 // frames' insides are hidden, and if one ever appears anyway the Hub is told and stops the game. Games never need
 // frames; Godot draws to one canvas. These replacements can't be undone back to the originals by game code.
 const FRAME=/^(?:iframe|frame|frameset|object|embed|portal|fencedframe)$/i,FRAME_HTML=/<\s*(?:iframe|frame|frameset|object|embed|portal|fencedframe)\b/i;
 const SEL='iframe,frame,frameset,object,embed,portal,fencedframe';
 const refuse=()=>{throw new DOMException('Frames are not available to games','SecurityError');};
 const framed=n=>!!n&&typeof n==='object'&&(FRAME.test(n.localName||'')||(typeof n.querySelector==='function'&&!!n.querySelector(SEL)));
 const lock=(o,k,d)=>{try{Object.defineProperty(o,k,{...d,configurable:false});}catch(e){}};
 const wrap=(o,k,check)=>{const f=o&&o[k];if(typeof f!=='function')return;
  lock(o,k,{writable:false,enumerable:false,value:function(...a){if(check(a))refuse();return f.apply(this,a);}});};
 const html=a=>a.some(x=>FRAME_HTML.test(String(x)));
 for(const D of [Document.prototype])for(const k of ['createElement','createElementNS'])wrap(D,k,a=>FRAME.test(String(a[k==='createElement'?0:1]).split(':').pop()));
 for(const P of [Node.prototype])for(const k of ['appendChild','insertBefore','replaceChild'])wrap(P,k,a=>framed(a[0]));
 for(const P of [Element.prototype,DocumentFragment.prototype,Document.prototype,CharacterData.prototype])
  for(const k of ['append','prepend','before','after','replaceWith','replaceChildren','moveBefore'])wrap(P,k,a=>a.some(framed));
 wrap(Element.prototype,'insertAdjacentElement',a=>framed(a[1]));
 wrap(Element.prototype,'insertAdjacentHTML',a=>html([a[1]]));
 for(const P of [Element.prototype,typeof ShadowRoot!=='undefined'&&ShadowRoot.prototype].filter(Boolean))wrap(P,'setHTMLUnsafe',html);
 wrap(Document.prototype,'write',html);wrap(Document.prototype,'writeln',html);
 wrap(Document.prototype,'execCommand',a=>html([a[2]]));
 wrap(Range.prototype,'insertNode',a=>framed(a[0]));wrap(Range.prototype,'surroundContents',a=>framed(a[0]));
 wrap(Range.prototype,'createContextualFragment',html);
 for(const [P,k] of [[Element.prototype,'innerHTML'],[Element.prototype,'outerHTML'],[typeof ShadowRoot!=='undefined'&&ShadowRoot.prototype,'innerHTML']]){
  const d=P&&Object.getOwnPropertyDescriptor(P,k);if(!d||!d.set)continue;
  lock(P,k,{enumerable:d.enumerable,get:d.get,set(v){if(FRAME_HTML.test(String(v)))refuse();d.set.call(this,v);}});
 }
 for(const C of ['HTMLIFrameElement','HTMLFrameElement','HTMLObjectElement','HTMLEmbedElement'])
  for(const k of ['contentWindow','contentDocument'])if(window[C])lock(window[C].prototype,k,{enumerable:true,get:()=>null});
 for(const C of ['HTMLIFrameElement','HTMLObjectElement','HTMLEmbedElement'])if(window[C])lock(window[C].prototype,'getSVGDocument',{writable:false,value:()=>null});
 new MutationObserver(()=>{if(document.querySelector(SEL)||window.length){
  document.querySelectorAll(SEL).forEach(n=>n.remove());tell({type:'sbike-leaving'});}})
  .observe(document,{childList:true,subtree:true});
 // Leaving: pagehide fires as a navigation away commits, before the new page shows, so the Hub page removes the frame
 // at once (module-host.js); its own load-count guard is the backstop.
 addEventListener('pagehide',()=>tell({type:'sbike-leaving'}));
 let data={},connected=false,last=0,seq=0;
 const pending=new Map();
 const send=(action,args={})=>new Promise(resolve=>{
  const id=++seq;
  const timer=setTimeout(()=>{pending.delete(id);resolve({ok:false,why:'Game connection timed out'});},5000);
  pending.set(id,{resolve,timer});
  parent.postMessage({type:'sbike-module',action,id,args},parentOrigin);
 });
 // Saved settings come from the Hub (module_sandbox.saves_file) before the engine starts (module-start.js waits for
 // `ready`); the browser's own storage is wiped every launch, so this is the only memory a game has.
 let saves={};
 const ready=send('ready').then(r=>{if(r&&r.saves&&typeof r.saves==='object')saves=r.saves;return r;});
 const bridge={snapshot:()=>({connected:connected&&performance.now()-last<3000,data}),request:send,ready,
  saved:(name)=>typeof saves[name]==='string'?saves[name]:null,
  save:(name,text)=>send('save',{file:String(name),text:String(text)}).then(r=>{if(r&&r.ok)saves[name]=String(text);return r;})};
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
 // Heartbeat: if a game freezes the page (or hogs it), these stop and the Hub closes the game (module-host.js).
 setInterval(()=>tell({type:'sbike-alive'}),1000);
})();
