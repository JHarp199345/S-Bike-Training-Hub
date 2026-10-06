// Your music folder as a library: songs, albums, artists, and Workout Tempo (songs that fit your cadence band).
// Playback goes through the ride's music player (ctx); this view only lists and chooses.
import {api,node,cadenceOf} from './music-common.js';
const artURL=t=>t&&t.art?'/api/music/library/art/'+t.art:'';
const initials=s=>(s||'?').replace(/[^\p{L}\p{N} ]/gu,'').split(/\s+/).filter(Boolean).map(w=>w[0]).join('').slice(0,2).toUpperCase()||'♪';
export const time=s=>{if(!Number.isFinite(s))return'';s=Math.round(s);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');};
export function cover(t,cls='lib-cover'){const box=node('div',undefined,{'class':cls});
  if(artURL(t)){const i=node('img',undefined,{src:artURL(t),alt:'',loading:'lazy',decoding:'async'});i.onerror=()=>i.replaceWith(node('span',initials(t.album||t.title),{'class':'lib-initials'}));box.append(i);}
  else box.append(node('span',initials(t?.album||t?.title),{'class':'lib-initials'}));return box;}
const svg=(d,cls='')=>{const s=document.createElementNS('http://www.w3.org/2000/svg','svg');s.setAttribute('viewBox','0 0 24 24');s.setAttribute('aria-hidden','true');if(cls)s.setAttribute('class',cls);s.innerHTML=d;return s;};
export const icons={
  prev:'<path d="M6.5 5v14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><path d="M19 5 9 12l10 7z" fill="currentColor"/>',next:'<path d="M17.5 5v14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><path d="M5 5l10 7-10 7z" fill="currentColor"/>',
  play:'<path d="M8 5v14l11-7z" fill="currentColor"/>',pause:'<path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor"/>',
  shuffle:'<path d="M3 7h3.5c2 0 3.3 1 4.5 3l2 4c1.2 2 2.5 3 4.5 3H21m0 0-3-3m3 3-3 3M3 17h3.5c1.4 0 2.5-.5 3.4-1.5M21 7h-3.5c-1.4 0-2.5.5-3.4 1.5M21 7l-3-3m3 3-3 3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  metronome:'<path d="M9 3h6l4 18H5zM12 17l5-11M8 17h8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>',
  volume:'<path d="M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 0 1 0 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>',
  library:'<path d="M4 4v16M8 4v16M12 5l4 15M17 6l3 13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  gear:'<circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'};
export const icon=(name,cls)=>svg(icons[name],cls);

export function mountLibrary(dlg,ctx){
  let tracks=[],view='songs',chip='all',query='',detail=null,timer=null,info=null;
  dlg.replaceChildren();
  const nav=node('nav',undefined,{'class':'lib-nav','aria-label':'Library sections'}),main=node('div',undefined,{'class':'lib-main'}),side=node('aside',undefined,{'class':'lib-now','aria-label':'Now playing'});
  const shell=node('div',undefined,{'class':'lib-shell'});shell.append(nav,main,side);
  const close=node('button','Close',{type:'button','class':'lib-close'});close.onclick=()=>dlg.close();
  dlg.append(close,shell);
  nav.append(node('h2','Library'));const navB={};
  for(const [id,label] of [['songs','Songs'],['albums','Albums'],['artists','Artists'],['playlists','Playlists'],['tempo','Workout Tempo']]){
    const b=node('button',label,{type:'button'});if(id==='tempo'){b.classList.add('lib-tempo-nav');b.append(icon('metronome'));}
    b.onclick=()=>{if(id==='playlists'){dlg.close();ctx.openPlaylists();return;}view=id;detail=null;draw();};navB[id]=b;nav.append(b);}
  const search=node('input',undefined,{type:'search',placeholder:'Search your music','aria-label':'Search your music'});
  search.oninput=()=>{query=search.value.trim().toLowerCase();draw();};
  const chips=node('div',undefined,{'class':'lib-chips',role:'group','aria-label':'Order'}),chipB={};
  for(const [id,label] of [['all','All'],['recent','Recently added'],['tempo','By tempo']]){const b=node('button',label,{type:'button'});b.onclick=()=>{chip=id;draw();};chipB[id]=b;chips.append(b);}
  const top=node('div',undefined,{'class':'lib-top'});top.append(search,chips);
  const body=node('div',undefined,{'class':'lib-body'}),foot=node('p','',{'class':'lib-foot','aria-live':'polite'});
  main.append(top,body,foot);

  const band=()=>ctx.band();
  const fit=t=>cadenceOf(t.bpm,band());
  const visible=()=>{let list=tracks.filter(t=>!query||[t.title,t.artist,t.album].some(v=>(v||'').toLowerCase().includes(query)));
    if(chip==='recent')list=[...list].sort((a,b)=>(b.added||0)-(a.added||0));
    if(chip==='tempo')list=[...list].sort((a,b)=>(a.bpm||999)-(b.bpm||999));return list;};
  const badge=t=>t.bpm?node('span',Math.round(t.bpm)+' BPM',{'class':'lib-bpm',title:t.bpm_source==='tag'?'Tempo from the file':'Tempo measured by the Hub'}):null;
  const tile=(t,list,i)=>{const b=node('button',undefined,{type:'button','class':'lib-tile','aria-label':`Play ${t.title} by ${t.artist}`});const c=cover(t);const bp=badge(t);if(bp)c.append(bp);
    b.append(c,node('strong',t.title),node('small',t.artist));b.onclick=()=>ctx.play(list,i);return b;};
  const row=(t,list,i)=>{const b=node('button',undefined,{type:'button','class':'lib-row','aria-label':`Play ${t.title} by ${t.artist}`});const txt=node('span');txt.append(node('strong',t.title),node('small',t.artist));
    b.append(cover(t,'lib-cover small'),txt);const bp=badge(t);if(bp)b.append(bp);else b.append(node('span',''));b.append(node('span',time(t.duration),{'class':'lib-time'}));b.onclick=()=>ctx.play(list,i);return b;};
  const grid=(items,make)=>{const g=node('div',undefined,{'class':'lib-grid'});items.forEach((x,i)=>g.append(make(x,i)));return g;};
  const rows=list=>{const g=node('div',undefined,{'class':'lib-rows'});list.forEach((t,i)=>g.append(row(t,list,i)));return g;};
  const group=key=>{const m=new Map();for(const t of visible()){const k=key(t);if(!m.has(k))m.set(k,[]);m.get(k).push(t);}return [...m.entries()].sort((a,b)=>a[0].localeCompare(b[0]));};
  const groupTile=(name,list,sub,round)=>{const b=node('button',undefined,{type:'button','class':'lib-tile'+(round?' round':'')});b.append(cover(list.find(t=>t.art)||{album:name}),node('strong',name),node('small',sub));return b;};
  const matching=()=>tracks.filter(t=>fit(t)?.fits);
  const bandText=()=>{const b=band();return b?`For your ${b[0]}–${b[1]} rpm band`:'';};
  const shelf=()=>{const m=matching();if(!m.length||!band())return null;const s=node('section',undefined,{'class':'lib-shelf'});
    const h=node('div',undefined,{'class':'lib-shelf-head'});h.append(node('h3','Matches your cadence'),node('small',bandText()));
    const strip=node('div',undefined,{'class':'lib-strip'});m.slice(0,12).forEach((t,i)=>strip.append(row(t,m,i)));s.append(h,strip);return s;};
  const empty=()=>{const e=node('div',undefined,{'class':'lib-empty'});e.append(node('h3','Your library is empty'),node('p',info?`Nothing playable in ${info.display} yet. Add songs in Music settings, by dropping files or choosing your folder.`:'Loading…'));
    if(info)e.append(Object.assign(node('button','Open Music settings',{type:'button'}),{onclick:()=>{dlg.close();ctx.openSettings();}}));return e;};
  function draw(){
    for(const [id,b] of Object.entries(navB))b.setAttribute('aria-current',String(id===view));
    for(const [id,b] of Object.entries(chipB))b.setAttribute('aria-pressed',String(id===chip));
    top.hidden=view==='tempo';
    if(!tracks.length){body.replaceChildren(empty());return;}
    if(detail){const list=detail.list;const head=node('div',undefined,{'class':'lib-detail-head'});const back=node('button','‹ Back',{type:'button'});back.onclick=()=>{detail=null;draw();};
      const playAll=node('button','Play',{type:'button','class':'lib-gold'});playAll.onclick=()=>ctx.play(list,0);const txt=node('div');txt.append(node('h3',detail.name),node('small',`${list.length} song${list.length===1?'':'s'}`));
      head.append(back,cover(list.find(t=>t.art)||{album:detail.name}),txt,playAll);body.replaceChildren(head,rows(list));return;}
    if(view==='songs'){const list=visible();const parts=[];const s=!query&&chip==='all'?shelf():null;if(s)parts.push(s);parts.push(list.length?grid(list,(t,i)=>tile(t,list,i)):node('p','No songs match.'));body.replaceChildren(...parts);}
    else if(view==='albums'){const g=group(t=>t.album);body.replaceChildren(grid(g,([name,list])=>{const artists=[...new Set(list.map(t=>t.album_artist||t.artist))];const b=groupTile(name,list,artists.length>1?'Various artists':artists[0]);b.onclick=()=>{detail={name,list:[...list].sort((a,b)=>(a.track||0)-(b.track||0))};draw();};return b;}));}
    else if(view==='artists'){const g=group(t=>t.artist);body.replaceChildren(grid(g,([name,list])=>{const b=groupTile(name,list,`${list.length} song${list.length===1?'':'s'}`,true);b.onclick=()=>{detail={name,list};draw();};return b;}));}
    else if(view==='tempo'){const b=band(),m=matching(),near=b?tracks.filter(t=>{const f=fit(t);return f&&!f.fits&&Math.abs(f.rpm-(b[0]+b[1])/2)<=12;}):[],unmeasured=tracks.filter(t=>!t.bpm).length;
      const head=node('div',undefined,{'class':'lib-tempo-head'});const cad=ctx.cadence();
      head.append(node('h3','Workout Tempo'),node('p',b?`${bandText()}${cad?` · you're at ${cad} rpm`:''}. A song fits at its tempo or half of it: 174 BPM is one beat per pedal stroke at 87 rpm.`:'Start a ride to see your cadence band.'));
      const go=node('button',`Play ${m.length} matching song${m.length===1?'':'s'}`,{type:'button','class':'lib-gold'});go.disabled=!m.length;go.onclick=()=>{ctx.match.set(true);ctx.play(m,Math.floor(Math.random()*m.length),true);};
      const keep=node('label');const box=node('input',undefined,{type:'checkbox'});box.checked=ctx.match.get();box.onchange=()=>ctx.match.set(box.checked);keep.append(box,' Keep choosing songs that fit my cadence');
      head.append(go,keep);const parts=[head];
      if(m.length){parts.push(node('h4','Matches your cadence'),rows(m));}
      if(near.length){parts.push(node('h4','Close to your band'),rows(near));}
      if(unmeasured)parts.push(node('p',`${unmeasured} song${unmeasured===1?'':'s'} not measured yet.`,{'class':'lib-foot'}));
      body.replaceChildren(...parts);}
  }
  // now playing
  const npCover=node('div',undefined,{'class':'lib-now-cover'}),npTitle=node('strong','Nothing playing'),npArtist=node('small',''),npTempo=node('small','',{'class':'lib-now-tempo'});
  const seek=node('input',undefined,{type:'range',min:'0',max:'1000',value:'0','aria-label':'Position in song'}),npTimes=node('div',undefined,{'class':'lib-now-times'});
  const prev=node('button',undefined,{type:'button','aria-label':'Previous song'}),pp=node('button',undefined,{type:'button','class':'lib-play','aria-label':'Play'}),next=node('button',undefined,{type:'button','aria-label':'Next song'});
  prev.append(icon('prev'));next.append(icon('next'));prev.onclick=()=>ctx.prev();next.onclick=()=>ctx.next();pp.onclick=()=>ctx.toggle();
  const controls=node('div',undefined,{'class':'lib-now-controls'});controls.append(prev,pp,next);
  side.append(node('h2','Now playing'),npCover,npTitle,npArtist,npTempo,seek,npTimes,controls);
  let seeking=false;seek.oninput=()=>{seeking=true;};seek.onchange=()=>{const a=ctx.audio;if(a.duration)a.currentTime=seek.value/1000*a.duration;seeking=false;};
  const progress=()=>{const a=ctx.audio;if(!seeking)seek.value=a.duration?String(Math.round(a.currentTime/a.duration*1000)):'0';npTimes.replaceChildren(node('span',time(a.currentTime)),node('span',time(a.duration)));};
  function now(){const t=ctx.current();npCover.replaceChildren(cover(t||{album:'♪'},'lib-cover big'));npTitle.textContent=t?.title||t?.name||'Nothing playing';npArtist.textContent=t?.artist||'';
    npTempo.textContent=ctx.tempoText(t);pp.replaceChildren(icon(ctx.running()?'pause':'play'));pp.setAttribute('aria-label',ctx.running()?'Pause':'Play');prev.disabled=next.disabled=pp.disabled=!t;progress();}
  ctx.audio.addEventListener('timeupdate',()=>{if(dlg.open)progress();});ctx.onChange(()=>{if(dlg.open)now();});
  async function load(){try{info=await api('library');}catch(e){foot.textContent=e.message;return;}tracks=info.tracks;const sc=info.scan||{};
    foot.textContent=sc.state==='reading'?`Reading your folder… ${sc.done} of ${sc.total}`:sc.state==='tempo'?`Measuring tempo… ${sc.tempo_done} of ${sc.tempo_total}`:sc.state==='error'?'The folder could not be read: '+(sc.error||''):`${tracks.length} song${tracks.length===1?'':'s'} · ${info.display}`;
    draw();clearTimeout(timer);if(dlg.open&&(sc.state==='reading'||sc.state==='tempo'))timer=setTimeout(load,2500);}
  dlg.addEventListener('close',()=>clearTimeout(timer));
  return {open(){dlg.showModal();load();now();},tracks:()=>tracks,load};
}
