// Your library: a search bar, Audio | Video, and 36 random picks from your folder. Simple until it needs to be more.
// Playback goes through the ride's player (ctx); this view only finds and chooses.
import {api,node} from './music-common.js';
const artURL=t=>t&&t.art?'/api/music/library/art/'+t.art:'';
const initials=s=>(s||'?').replace(/[^\p{L}\p{N} ]/gu,'').split(/\s+/).filter(Boolean).map(w=>w[0]).join('').slice(0,2).toUpperCase()||'♪';
export const time=s=>{if(!Number.isFinite(s))return'';s=Math.round(s);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');};
export function cover(t,cls='lib-cover'){const box=node('div',undefined,{'class':cls});
  if(t?.kind==='video'){box.append(node('span','▶',{'class':'lib-initials'}));return box;}
  if(artURL(t)){const i=node('img',undefined,{src:artURL(t),alt:'',loading:'lazy',decoding:'async'});i.onerror=()=>i.replaceWith(node('span',initials(t.album||t.title),{'class':'lib-initials'}));box.append(i);}
  else box.append(node('span',initials(t?.album||t?.title),{'class':'lib-initials'}));return box;}
const svg=(d,cls='')=>{const s=document.createElementNS('http://www.w3.org/2000/svg','svg');s.setAttribute('viewBox','0 0 24 24');s.setAttribute('aria-hidden','true');if(cls)s.setAttribute('class',cls);s.innerHTML=d;return s;};
export const icons={
  prev:'<path d="M6.5 5v14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><path d="M19 5 9 12l10 7z" fill="currentColor"/>',next:'<path d="M17.5 5v14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><path d="M5 5l10 7-10 7z" fill="currentColor"/>',
  play:'<path d="M8 5v14l11-7z" fill="currentColor"/>',pause:'<path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor"/>',
  shuffle:'<path d="M3 7h3.5c2 0 3.3 1 4.5 3l2 4c1.2 2 2.5 3 4.5 3H21m0 0-3-3m3 3-3 3M3 17h3.5c1.4 0 2.5-.5 3.4-1.5M21 7h-3.5c-1.4 0-2.5.5-3.4 1.5M21 7l-3-3m3 3-3 3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  volume:'<path d="M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 0 1 0 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>',
  library:'<path d="M4 4v16M8 4v16M12 5l4 15M17 6l3 13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  gear:'<circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'};
export const icon=(name,cls)=>svg(icons[name],cls);

export function mountLibrary(dlg,ctx){
  let kind='audio',query='',seed=String(Math.random()).slice(2,10),items=[],timer=null,searchTimer=null;
  dlg.replaceChildren();
  const close=node('button','Close',{type:'button','class':'lib-close'});close.onclick=()=>dlg.close();
  const head=node('div',undefined,{'class':'lib-simple-head'});
  head.append(node('h2','Library'));
  const search=node('input',undefined,{type:'search',placeholder:'Search your folder','aria-label':'Search your folder'});
  const kinds=node('div',undefined,{'class':'lib-chips',role:'group','aria-label':'Audio or video'}),kindB={};
  for(const [id,label] of [['audio','Audio'],['video','Video']]){const b=node('button',label,{type:'button'});b.onclick=()=>{kind=id;load();};kindB[id]=b;kinds.append(b);}
  const fresh=node('button','New picks',{type:'button',title:'Another 36 at random'});fresh.onclick=()=>{seed=String(Math.random()).slice(2,10);load();};
  const shuffleAll=node('button','Shuffle all',{type:'button','class':'lib-gold',title:'Play everything at random'});
  const device=node('label','Play files from this device',{'class':'lib-device'});const files=node('input',undefined,{type:'file',multiple:'',accept:'audio/*,video/*',hidden:''});device.append(files);
  const tools=node('div',undefined,{'class':'lib-top'});tools.append(search,kinds,fresh,shuffleAll);
  const body=node('div',undefined,{'class':'lib-body'}),foot=node('p','',{'class':'lib-foot','aria-live':'polite'});
  dlg.append(close,head,tools,body,foot,device);
  search.oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{query=search.value.trim();load();},220);};
  shuffleAll.onclick=async()=>{try{const all=(await api('library')).tracks.filter(t=>(t.kind||'audio')==='audio');if(!all.length)return;
    for(let i=all.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[all[i],all[j]]=[all[j],all[i]];}ctx.play(all,0,true);dlg.close();}catch(e){foot.textContent=e.message;}};
  files.onchange=()=>{if(files.files.length){ctx.playFiles([...files.files]);files.value='';dlg.close();}};
  const tile=(t,i)=>{const b=node('button',undefined,{type:'button','class':'lib-tile'+(t.kind==='video'?' video':''),'aria-label':`Play ${t.title}${t.artist&&t.kind!=='video'?' by '+t.artist:''}`});
    const c=cover(t);if(t.bpm&&t.kind!=='video')c.append(node('span',Math.round(t.bpm)+' BPM',{'class':'lib-bpm'}));
    b.append(c,node('strong',t.title),node('small',t.kind==='video'?(time(t.duration)||'Video'):t.artist||''));
    b.onclick=()=>{if(t.kind==='video')ctx.playVideo(t);else ctx.play(items,i);dlg.close();};return b;};
  async function load(){
    for(const [id,b] of Object.entries(kindB))b.setAttribute('aria-pressed',String(id===kind));
    shuffleAll.hidden=kind!=='audio';fresh.hidden=!!query;
    let d;try{d=await api(`library/picks?${new URLSearchParams({kind,q:query,seed})}`);}catch(e){body.replaceChildren(node('p',e.message));return;}
    items=d.items;
    if(!d.folder){body.replaceChildren(node('div',undefined,{'class':'lib-empty'}));body.firstChild.append(node('h3','Choose your folder'),node('p','Pick the folder with your audio and video files in Music settings. The Hub reads it and never changes your files.'),Object.assign(node('button','Open Music settings',{type:'button'}),{onclick:()=>{dlg.close();ctx.openSettings();}}));foot.textContent='';return;}
    const total=d.counts[kind];
    if(!items.length)body.replaceChildren(node('p',query?`No ${kind} matches “${query}”.`:`No ${kind} files in ${d.display} yet.`,{'class':'lib-empty'}));
    else{const g=node('div',undefined,{'class':'lib-grid'});items.forEach((t,i)=>g.append(tile(t,i)));body.replaceChildren(g);}
    const sc=d.scan||{};
    foot.textContent=(sc.state==='reading'?`Reading your folder… ${sc.done} of ${sc.total} · `:sc.state==='tempo'?`Measuring tempo… ${sc.tempo_done} of ${sc.tempo_total} · `:'')
      +(query?`${items.length} match${items.length===1?'':'es'}`:`${items.length} random of ${total} ${kind==='audio'?'songs':'videos'}`)+` · ${d.display}`;
    clearTimeout(timer);if(dlg.open&&(sc.state==='reading'||sc.state==='tempo'))timer=setTimeout(load,3000);}
  dlg.addEventListener('close',()=>clearTimeout(timer));
  return {open(k){if(k)kind=k;dlg.showModal();load();},load};
}
