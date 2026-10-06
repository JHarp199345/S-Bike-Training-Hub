import {api,node} from './music-common.js';
const $=id=>document.getElementById(id),video=$('ride-video'),screen=$('watch-screen'),picker=$('video-picker'),list=$('video-list'),notice=$('video-notice');
let trail=[],request=0,lastCue='',expandUntil=0,pinned=false,status={};
export function watchMode(on){screen.hidden=!on;if(on)window.dispatchEvent(new Event('hub-video-play'));if(!on){video.pause();}else if(!video.getAttribute('src'))$('watch-empty').hidden=false;}
window.addEventListener('hub-ride-status',e=>{status=e.detail;const s=status,work=s.test||s.workout,step=work?.step||work?.stage||'',target=s.erg;
  const cue=[work?.name|| (s.test?'FTP test':''),step,target].filter(x=>x!==undefined&&x!==null&&x!=='').join(' · ');
  if(cue&&cue!==lastCue){expandUntil=Date.now()+7000;lastCue=cue;}
  $('watch-metrics').classList.toggle('expanded',pinned||Date.now()<expandUntil);
  $('watch-power').textContent=s.power===undefined?'—':s.power;
  $('watch-hr').textContent=s.hr>0?s.hr:(s.cadence??'—');$('watch-hr-unit').textContent=s.hr>0?'bpm':'rpm';$('watch-time').textContent=work?.elapsed!==undefined?`${Math.floor(work.elapsed/60)}:${String(Math.floor(work.elapsed%60)).padStart(2,'0')}`:s.bike?s.elapsed||'—':'—';
  $('watch-cue').textContent=target?`Target ${Math.round(target)} W${step?' · '+step:''}`:s.bike?'Free ride · '+(s.cadence||0)+' rpm':'Bike disconnected · preview';
});
$('watch-metrics').onclick=()=>{pinned=!pinned;$('watch-metrics').setAttribute('aria-pressed',String(pinned));$('watch-metrics').classList.toggle('expanded',pinned||Date.now()<expandUntil);};
$('watch-fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else $('ride-screen').requestFullscreen?.();};
video.onerror=()=>{$('watch-message').textContent='This video format could not play in this browser. It may need conversion in Plex. Choose another episode or use Plex’s player.';};
async function browse(parent='',offset=0,append=false){const stamp=++request;if(!append)list.replaceChildren();notice.textContent='Loading your Plex library…';
  try{const d=await api('video?parent='+encodeURIComponent(parent)+'&offset='+offset);if(stamp!==request)return;notice.textContent=d.items.length?'Choose a show, movie, or episode.':'No videos found in this library.';
    $('video-back').hidden=!trail.length;for(const row of d.items){const b=node('button',row.title),sub=node('small',row.folder?'Open':row.unavailable||row.detail||'Play video');b.append(sub);b.disabled=!!row.unavailable;
      b.onclick=()=>{if(row.folder){trail.push(parent);browse(row.id);return;}window.dispatchEvent(new Event('hub-video-play'));video.pause();video.src=row.url;video.hidden=false;video.load();$('watch-empty').hidden=true;$('watch-message').textContent='';picker.close();
        video.play().catch(()=>{$('watch-message').textContent='Press Play on the video to begin.';});};list.append(b);}
    if(d.next!==null&&d.next!==undefined){const more=node('button','Load more');more.onclick=()=>{more.remove();browse(parent,d.next,true);};list.append(more);}
  }catch(e){if(stamp===request)notice.textContent=e.message;}
}
$('video-choose').onclick=()=>{trail=[];picker.showModal();browse();};$('video-back').onclick=()=>browse(trail.pop()||'');
// Opening a picker does not start a workout or change a trainer setting.
const workouts=$('ride-workouts'),workList=$('ride-workout-list'),workNotice=$('ride-workout-notice');
$('ride-workout-open').onclick=async()=>{workouts.showModal();workList.replaceChildren();workNotice.textContent='Loading workouts and routes…';
  let data;try{const response=await fetch('/api/ride/menu');data=await response.json();if(!response.ok)throw Error(data.error||'Could not load your rides.');}catch(e){workNotice.textContent=e.message;return;}
  paintLibrary(data);
};
function paintLibrary(data,order='match'){
  workList.replaceChildren();
  const guidance=data.guidance||{};
  workNotice.textContent=[guidance.warning,guidance.not_ready?'The Hub recommends recovery from cycling today. Preview rides here and review the current readings in Fitness.':guidance.suggested_tier?`Current cycling guidance: ${guidance.suggested_tier.replaceAll('_',' ')} · ${guidance.phase||'training'} phase.`:'Load guidance is unavailable.',...(guidance.why||[])].filter(Boolean).join(' ');
  const explanation=node('p',guidance.basis);workList.append(explanation);
  if(data.scheduled.length){workList.append(node('h3','Scheduled today'));for(const session of data.scheduled){const p=node('p',`${session.name} · ${session.minutes||'—'} min`);workList.append(p);}workList.append(node('a','Open today’s training plan',{href:'/coach#today'}));}
  const sort=node('select',undefined,{'aria-label':'Order rides'});for(const [id,label] of [['match','Load match / schedule'],['lighter','Lower load / gentler terrain'],['harder','Higher load / hillier terrain'],['recent','Least recently started']])sort.append(node('option',label,{value:id}));sort.value=order;sort.onchange=()=>paintLibrary(data,sort.value);workList.append(node('label','Order rides'),sort);
  const groups=[['ERG workouts',data.workouts,'workout'],['Saved routes',data.routes,'route']];
  for(const [heading,original,kind] of groups){const rows=[...original];if(order!=='match')rows.sort((a,b)=>{const aa=kind==='route'?a.climb_m:a.stats.tss,bb=kind==='route'?b.climb_m:b.stats.tss;return order==='recent'?(a.last_used||'').localeCompare(b.last_used||''):order==='harder'?bb-aa:aa-bb;});workList.append(node('h3',heading));if(!rows.length)workList.append(node('p','Nothing saved yet. Create or import one in Plan a ride.'));
  for(const row of rows){row.terrain_kind=row.terrain_kind||row.kind;row.kind=kind;row.ftp=data.ftp;const b=node('button',row.name),small=node('small',kind==='route'?`${row.km} km · ${row.climb_m} m climb · ${row.max_grade}% max grade · ${row.terrain_kind||'terrain'}`:`${row.stats.minutes} min · ${row.stats.tss} estimated TSS · ${row.stats.if} intensity factor`);b.append(small);
    if(row.scheduled)b.append(node('small','On today’s schedule'));
    if(row.match_basis)b.append(node('small','Ordered by load match to '+row.match_basis));
    if(row.last_used)b.append(node('small','Last started '+row.last_used));
    b.onclick=async()=>{const back=node('button','Back to rides');back.onclick=()=>paintLibrary(data,order);workList.replaceChildren(back,node('h3',row.name),node('p',row.note||small.textContent));
      if(row.steps?.length){const breakdown=node('ol');for(const step of row.steps)breakdown.append(node('li',`${step.minutes} min · ${step.watts??Math.round(step.pct*row.ftp/100)} W`));workList.append(breakdown);}
      const start=node('button',guidance.not_ready?'Recovery recommended · review in Fitness':'Start this ride');start.disabled=!!guidance.not_ready;workList.append(start,node('a','Review current load and readiness',{href:'/coach#fitness'}));start.onclick=async()=>{start.disabled=true;try{const r=await fetch('/status');if(!r.ok)throw Error('Reconnect the Hub first.');const s=await r.json();
          if(s.workout||s.test||s.route)throw Error('Finish the active ride before starting another.');if(!s.bike||s.no_bike)throw Error('Connect your bike in Settings first. You can still preview rides.');
          const res=await fetch('/api/ride/menu/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:row.id,kind:row.kind})}),d=await res.json();if(!res.ok||d.error)throw Error(d.error||'This ride could not start.');workouts.close();
        }catch(e){workNotice.textContent=e.message;}finally{start.disabled=false;}};};workList.append(b);}}
}
