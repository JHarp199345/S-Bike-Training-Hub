/* Plan calendar: local dates, saved phases and read-only workout records. */
(function(root){
 'use strict';
 const pad=n=>String(n).padStart(2,'0');
 const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
 function date(value){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))throw Error('Choose a valid calendar date.');
  const [y,m,d]=value.split('-').map(Number),out=new Date(y,m-1,d,12);
  if(iso(out)!==value)throw Error('Choose a valid calendar date.');
  return out;
 }
 function addDays(value,n){const d=date(value);d.setDate(d.getDate()+n);return iso(d);}
 function monthOf(value){return value.slice(0,7);}
 function shiftMonth(value,n){const d=date(value+'-01');d.setMonth(d.getMonth()+n);return monthOf(iso(d));}
 function monthDays(value){
  const start=date(value+'-01'),offset=(start.getDay()+6)%7,days=[];
  for(let i=0;i<42;i++)days.push(addDays(iso(start),i-offset));
  return days;
 }
 function phaseAt(phases,value){return phases.find(p=>p.start<=value&&value<p.end)||null;}
 function phaseState(p,today){return p.end<=today?'Past':p.start>today?'Upcoming':'Current';}
 function overlapsMonth(p,m){return p.start<shiftMonth(m,1)+'-01'&&p.end>m+'-01';}
 function dayDifference(a,b){return Math.round((Date.UTC(...a.split('-').map((n,i)=>Number(n)-(i===1?1:0)))-Date.UTC(...b.split('-').map((n,i)=>Number(n)-(i===1?1:0))))/86400000);}
 function weekStart(value){const d=date(value);return addDays(value,-((d.getDay()+6)%7));}
 function recordIds(record){return [...(record?.activity_ids||[]),record?.activity_id,record?.id,record?.lifting?.source_activity_id].filter(Boolean);}
 function liftingKey(log){return log?.logged?`${log.date}:${log.logged}:${log.session}`:null;}
 function sessionsFor(row){
  const sessions=(row?.sessions||[]).map(s=>({...s,recordOnly:false}));
  const linked=new Set(sessions.flatMap(s=>recordIds(s.completion))),lifts=new Set(sessions.map(s=>liftingKey(s.completion?.lifting)).filter(Boolean));
  for(const a of row?.done||[]){if(recordIds(a).some(id=>linked.has(id))||(liftingKey(a.lifting)&&lifts.has(liftingKey(a.lifting))))continue;
   sessions.push({sport:a.sport,name:a.workout_name||`Recorded ${a.sport||'workout'}`,completion:a,minutes:a.planned_minutes,recordOnly:true});
  }
  return sessions;
 }
 const E=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const SPORT={ride:'Cycling',bike:'Cycling',swim:'Swimming',run:'Running',gym:'Strength',walk:'Walking',rest:'Rest',tri:'Triathlon',other:'Event'};
 const COLORS={blue:'#359cff',teal:'#2bd7c3',purple:'#b393ff',gold:'#f0c15c',orange:'#ffab70'};
 const fullDate=value=>date(value).toLocaleDateString(undefined,{weekday:'long',month:'long',day:'numeric',year:'numeric'});
 function create(options){
  const {dialog,body,getProgram,getToday,loadWeek,icon=()=>'',sessionState=s=>s.skipped_id?'cancelled':s.completion||s.completed?'completed':s.missed?'missed':'planned',renderWorkout=()=>''}=options;
  let program={},plannedBy=new Map(),phases=[],events=[],start,end,selected=null,revision=0,observer=null,focusMonth=null,detailOpen=false,detailRow,focusedEventId=null;
  let records=new Map(),requests=new Map(),queued=new Set(),loading=new Set(),failed=new Set(),queue=[],busy=0,shownPhases=true;
  const notice=message=>{dialog.querySelector('#tc-status').textContent=message;};
  const eventWindow=document.createElement('dialog');eventWindow.id='tc-eventdialog';eventWindow.setAttribute('aria-labelledby','tc-eventtitle');document.body.append(eventWindow);
  const badgeFor=e=>root.EventGoals?root.EventGoals.badgeFor(e):null;
  function eventArt(e,large=false){const src=badgeFor(e);return src?`<img class="tc-event-art${large?' tc-event-art-large':''}" src="${src}" alt="${E(e.name)} organizer artwork">`:'';}
  function openEvent(index){
   const e=events[index];if(!e)return;const days=dayDifference(e.date,getToday()),past=days<0,p=phaseAt(phases,e.date);
   eventWindow.innerHTML=`<header class="tc-event-window-header"><span>${past?'Past event · Memory Road':'Upcoming event'}</span><button type="button" data-event-close aria-label="Close event details">✕</button></header><div class="tc-event-window-body"><div class="tc-event-hero">${eventArt(e,true)}<div><h2 id="tc-eventtitle">${E(e.name)}</h2><p>${E(fullDate(e.date))}</p><span class="tc-event-status">${past?'Past scheduled '+E(e.kind||'event'):days===0?'Today':`${days} days to go`}</span></div></div>${past?'<p class="tc-event-unconfirmed">Completion not confirmed for this event.</p>':''}<dl><div><dt>Sport</dt><dd>${E(SPORT[e.sport]||e.sport||'—')}</dd></div>${e.time?`<div><dt>Time</dt><dd>${E(e.time)}</dd></div>`:''}${e.location?`<div><dt>Location</dt><dd>${E(e.location)}</dd></div>`:''}${p?`<div><dt>Training phase</dt><dd>${E(p.label)}</dd></div>`:''}</dl>${['website','source_url','promotion_url'].filter(key=>root.EventGoals?.artworkURL(e[key])).map(key=>`<p><a href="${E(e[key])}" target="_blank" rel="noopener noreferrer">${({website:'Event website',source_url:'Event listing',promotion_url:'Promotion / social'})[key]} ↗</a></p>`).join('')}${e.note?`<section class="tc-event-note"><h3>Event notes</h3><p>${E(e.note)}</p></section>`:''}${badgeFor(e)?'<small class="tc-event-art-credit">Organizer artwork · permission recorded by athlete.</small>':''}</div><footer>${p?'<button type="button" data-event-plan>View training plan</button>':''}<button type="button" data-event-day>View this day’s workouts</button><button type="button" data-event-close>Back to calendar</button></footer>`;
   const planButton=eventWindow.querySelector('[data-event-plan]');if(planButton)planButton.onclick=()=>{eventWindow.close();jump(monthOf(p.start));select(p.start);};
   eventWindow.querySelector('[data-event-day]').onclick=()=>{eventWindow.close();jump(monthOf(e.date));select(e.date);};
   eventWindow.querySelectorAll('[data-event-close]').forEach(b=>b.onclick=()=>eventWindow.close());
   eventWindow.scrollTop=0;eventWindow.showModal();
  }
  function initialRange(){
   const today=getToday(),starts=[today,...phases.map(p=>p.start)].filter(Boolean).sort(),ends=[today,...phases.map(p=>addDays(p.end,-1)),program.goal?.target,...events.map(e=>e.date)].filter(Boolean).sort();
   // Render the full saved program plus a year ahead. Workouts load only for visible months.
   start=monthOf(starts[0]);end=[monthOf(ends.at(-1)),shiftMonth(monthOf(today),12)].sort().at(-1);
  }
  function months(){const out=[];for(let m=start;m<=end;m=shiftMonth(m,1))out.push(m);return out;}
  function eventGroups(){
   const today=getToday(),upcoming=events.filter(e=>e.date>=today),focused=upcoming.find(e=>e.id===focusedEventId)||upcoming[0];focusedEventId=focused?.id||null;const group=(items,past)=>items.map(e=>{const days=dayDifference(e.date,today);return `<button type="button" class="tc-event" data-event-index="${events.indexOf(e)}" title="${E(e.name)}" aria-haspopup="dialog">${eventArt(e)}<span><b>${E(e.name)}</b><small>${E(date(e.date).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}))}${past?' · Completion unconfirmed':days===0?' · Today':` · ${days} days`}</small></span></button>`;}).join('');
   return `<div class="tc-events"><section aria-label="Upcoming events"><h3><button type="button" data-upcoming-list aria-haspopup="dialog">Upcoming</button></h3><div class="tc-upcoming-layout" tabindex="0" aria-label="Upcoming event. Scroll or use arrow keys to switch."><div class="tc-event-list">${group(focused?[focused]:[],false)||'<p>No upcoming events saved.</p>'}</div><div class="tc-event-controls">${options.onAddEvent?'<button type="button" data-add-event aria-label="Add an event or goal">＋</button>':''}${focused&&options.onRemoveEvent?`<button type="button" data-remove-event="${E(focused.id)}" aria-label="Remove ${E(focused.name)} from scheduled events">−</button>`:''}</div></div></section><section aria-label="Past events · Memory Road"><h3>Past events · Memory Road</h3><div class="tc-event-list">${group(events.filter(e=>e.date<today).reverse(),true)||'<p>No past events saved.</p>'}</div></section></div>`;

  }
  const upcomingWindow=document.createElement('dialog');upcomingWindow.id='tc-upcoming-dialog';upcomingWindow.setAttribute('aria-labelledby','tc-upcoming-title');document.body.append(upcomingWindow);
  function refreshEventGroups(){body.querySelector('.tc-events').outerHTML=eventGroups();}
  function openUpcomingList(){const upcoming=events.filter(e=>e.date>=getToday());upcomingWindow.innerHTML=`<header><h2 id="tc-upcoming-title">Upcoming events</h2><button type="button" data-upcoming-close aria-label="Close upcoming events">✕</button></header><p>Choose an event to review its training context.</p><div class="tc-upcoming-full-list">${upcoming.map(e=>`<button type="button" data-upcoming-index="${events.indexOf(e)}"><b>${E(e.name)}</b><small>${E(fullDate(e.date))}</small></button>`).join('')||'<p>No upcoming events saved.</p>'}</div>`;upcomingWindow.querySelector('[data-upcoming-close]').onclick=()=>upcomingWindow.close();upcomingWindow.querySelectorAll('[data-upcoming-index]').forEach(button=>button.onclick=()=>{const index=Number(button.dataset.upcomingIndex);focusedEventId=events[index].id;refreshEventGroups();upcomingWindow.close();openEvent(index);});upcomingWindow.showModal();}
  let eventTransition=false;
  async function stepUpcoming(direction){if(eventTransition)return;const upcoming=events.filter(e=>e.date>=getToday()),index=upcoming.findIndex(e=>e.id===focusedEventId),next=Math.max(0,Math.min(upcoming.length-1,index+direction));if(!upcoming.length||next===index)return;eventTransition=true;const row=body.querySelector('.tc-upcoming-layout .tc-event'),reduced=root.matchMedia?.('(prefers-reduced-motion: reduce)').matches;try{if(row?.animate&&!reduced)await row.animate([{opacity:1},{opacity:0}],{duration:240,easing:'ease-in',fill:'forwards'}).finished;focusedEventId=upcoming[next].id;refreshEventGroups();body.querySelector('.tc-upcoming-layout').focus({preventScroll:true});const replacement=body.querySelector('.tc-upcoming-layout .tc-event');if(replacement?.animate&&!reduced)await replacement.animate([{opacity:0},{opacity:1}],{duration:320,easing:'ease-out'}).finished;}finally{eventTransition=false;}}
  body.addEventListener('wheel',e=>{if(!e.target.closest('.tc-upcoming-layout')||Math.abs(e.deltaY)<2)return;e.preventDefault();stepUpcoming(e.deltaY>0?1:-1);},{passive:false});
  body.addEventListener('keydown',e=>{if(!e.target.closest('.tc-upcoming-layout')||!['ArrowDown','ArrowUp'].includes(e.key))return;e.preventDefault();stepUpcoming(e.key==='ArrowDown'?1:-1);});
  function tile(value,m){
   const p=phaseAt(phases,value),inMonth=monthOf(value)===m,today=getToday();
   return `<button type="button" class="tc-day${inMonth?'':' tc-adjacent'}${value<today?' tc-past':''}${value===today?' tc-today':''}" data-date="${value}" ${inMonth?'':'tabindex="-1"'} style="--tc-phase:${COLORS[p?.color]||COLORS.blue}" aria-label="${E(fullDate(value))}" ${value===today?'aria-current="date"':''} aria-pressed="${value===selected}" ${p?'data-has-phase="true"':''}><span class="tc-date-number">${date(value).getDate()}</span>${value===today?'<span class="tc-today-label">Today</span>':''}<span class="tc-marks"></span>${events.some(e=>e.date===value)?'<span class="tc-event-dot" title="Event scheduled" aria-label="Event scheduled">◇</span>':''}</button>`;
  }
  function monthHtml(m){
   const ps=phases.filter(p=>overlapsMonth(p,m));
   return `<section class="tc-month" data-month="${m}" aria-label="${E(date(m+'-01').toLocaleDateString(undefined,{month:'long',year:'numeric'}))}"><h4>${E(date(m+'-01').toLocaleDateString(undefined,{month:'long'}))} <small>${m.slice(0,4)}</small></h4><div class="tc-weekdays">${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(x=>`<span>${x}</span>`).join('')}</div><div class="tc-days">${monthDays(m).map(value=>tile(value,m)).join('')}</div><div class="tc-phase-ribbons">${ps.map(p=>`<button type="button" data-phase-date="${E(p.start)}" style="--tc-phase:${COLORS[p.color]||COLORS.blue}"><span>${E(p.label)}</span><small>${E(p.start)} – ${E(addDays(p.end,-1))} · ${phaseState(p,getToday())}</small></button>`).join('')}</div><small class="tc-month-state">Workout records load when visible.</small></section>`;
  }
  function render(){
   observer?.disconnect();let html='',year='';
   for(const m of months()){if(m.slice(0,4)!==year){if(year)html+='</div></section>';year=m.slice(0,4);html+=`<section class="tc-year" aria-labelledby="tc-year-${year}"><h3 id="tc-year-${year}">${year}</h3><div class="tc-month-grid">`;}html+=monthHtml(m);}
   if(year)html+='</div></section>';
   body.innerHTML=`${eventGroups()}<div class="tc-range-tools"><button type="button" data-range="earlier">↑ Earlier months</button><span>${E(start)} – ${E(end)}</span></div><div class="tc-years">${html}</div><div class="tc-range-tools"><span>Saved workouts, plus your program’s planned sessions (faded).</span><button type="button" data-range="later">Later months ↓</button></div>`;
   body.classList.toggle('tc-hide-phases',!shownPhases);
   body.querySelectorAll('.tc-day').forEach(updateTile);
   observer=new IntersectionObserver(entries=>entries.filter(e=>e.isIntersecting).forEach(e=>loadMonth(e.target)),{root:dialog,rootMargin:'180px'});
   body.querySelectorAll('[data-month]').forEach(el=>{if(monthDays(el.dataset.month).filter(value=>monthOf(value)===el.dataset.month).every(value=>records.has(value)))el.querySelector('.tc-month-state').textContent='Saved plans and recorded sessions.';observer.observe(el);});
  }
  function plannedMap(prog){const m=new Map();for(const w of prog.weeks||[])for(const x of w.slots||[])if(x.date&&x.sport&&x.sport!=='rest'&&x.source!=='scheduled')(m.get(x.date)||m.set(x.date,[]).get(x.date)).push(x);return m;}
  function plannedFor(value,items){return items.length?[]:(plannedBy.get(value)||[]);}
  const plannedText=x=>`${SPORT[x.sport]||x.sport}${x.purpose?': '+x.purpose:''}${Array.isArray(x.minutes)?` · ${x.minutes[0]}–${x.minutes[1]} min`:''}`;
  function updateTile(el){
   const value=el.dataset.date,row=records.get(value),p=phaseAt(phases,value),items=sessionsFor(row),state=items.map(sessionState),marks=el.querySelector('.tc-marks');
   const plan=plannedFor(value,items);marks.innerHTML=plan.length?plan.slice(0,3).map(x=>`<span class="tc-mark tc-mark-planned tc-sport-${E(x.sport)}" title="${E('Planned · '+plannedText(x))}">${icon(x.sport)}</span>`).join(''):items.slice(0,3).map((s,i)=>`<span class="tc-mark tc-sport-${E(s.sport)}" title="${E((s.name||SPORT[s.sport]||s.sport)+' · '+state[i])}">${icon(s.sport)}<small>${({completed:'✓',partial:'◐',cancelled:'−',missed:'×'})[state[i]]||''}</small></span>`).join('')+(items.length>3?`<small>+${items.length-3}</small>`:'');
   el.setAttribute('aria-label',`${fullDate(value)}${p?' · '+p.label:''}${items.length?' · '+items.map((s,i)=>(s.name||SPORT[s.sport]||'Workout')+': '+state[i]).join(', '):plan.length?' · Planned: '+plan.map(plannedText).join(', '):row?' · No saved workouts':' · Select to load workouts'}`);
   el.title=el.getAttribute('aria-label');el.classList.toggle('tc-has-work',!!items.length);el.classList.toggle('tc-has-plan',!!plan.length);
   el.classList.toggle('tc-selected',value===selected);el.setAttribute('aria-pressed',String(value===selected));
  }
  function update(){body.querySelectorAll('.tc-day').forEach(updateTile);if(detailOpen&&selected&&records.has(selected)&&records.get(selected)!==detailRow)showDetails(selected);}
  function fetchWeek(value){
   const key=weekStart(value);if(requests.has(key))return requests.get(key);
   const token=revision;
   const request=loadWeek(key).then(rows=>{if(token===revision)rows.forEach(row=>records.set(row.date,row));return rows;}).catch(error=>{if(requests.get(key)===request)requests.delete(key);throw error;});
   requests.set(key,request);return request;
  }
  function monthWeeks(m){return [...new Set(monthDays(m).filter(value=>monthOf(value)===m).map(weekStart))];}
  function loadMonth(el){const m=el.dataset.month;if(queued.has(m))return;queued.add(m);queue.push({m,token:revision});pump();}
  function pump(){
   while(busy<2&&queue.length){const task=queue.shift();if(task.token!==revision)continue;busy++;loading.add(task.m);
    const el=body.querySelector(`[data-month="${task.m}"]`);if(el)el.querySelector('.tc-month-state').textContent='Loading workout records…';
    (async()=>{for(const w of monthWeeks(task.m)){if(task.token!==revision)return;await fetchWeek(w);}})().then(()=>{if(task.token!==revision)return;failed.delete(task.m);update();const node=body.querySelector(`[data-month="${task.m}"]`);if(node)node.querySelector('.tc-month-state').textContent='Saved plans and recorded sessions.';}).catch(()=>{if(task.token!==revision)return;failed.add(task.m);const node=body.querySelector(`[data-month="${task.m}"]`);if(node)node.querySelector('.tc-month-state').innerHTML='<button type="button" data-retry="'+task.m+'">Records unavailable · retry</button>';}).finally(()=>{busy--;loading.delete(task.m);pump();});
   }
  }
  function renderSession(s){
   const actual=s.completion,kind=sessionState(s),minutes=actual?.minutes??s.minutes;
   return `<article class="tc-session"><header>${icon(s.sport)}<div><h4>${E(s.explanation?.test?.title||s.name||SPORT[s.sport]||'Workout')}</h4><p>${E(SPORT[s.sport]||s.sport)}${minutes!=null?' · '+E(minutes)+' min':''}${actual?.km!=null?' · '+E(actual.km)+' km':''} · <span class="tc-session-state">${E(kind)}</span>${s.recordOnly?' · recorded session':''}</p></div></header>${s.note?`<p>${E(s.note)}</p>`:''}${s.steps?.length||s.swim_recipe||s.run_recipe||s.lifts?.length||s.workout?`<details><summary>Workout details</summary>${renderWorkout(s)||`<ol>${(s.steps||[]).map(x=>`<li>${E(x)}</li>`).join('')}</ol>`}</details>`:''}</article>`;
  }
  function showDetails(value,error=false){
   const el=dialog.querySelector('#tc-day-detail'),p=phaseAt(phases,value),row=records.get(value),items=sessionsFor(row),evs=events.filter(e=>e.date===value);
   detailOpen=true;detailRow=row;el.hidden=false;el.innerHTML=`<header><div><small>Selected day${value===getToday()?' · Today':''}</small><h3>${E(fullDate(value))}</h3></div><button type="button" data-detail-close aria-label="Close selected day">✕</button></header>${p?`<p class="tc-day-phase" style="--tc-phase:${COLORS[p.color]||COLORS.blue}">${E(p.label)} · ${phaseState(p,getToday())}<small>${E(p.purpose||'')}</small></p>`:''}${evs.map(e=>`<div class="tc-day-event"><b>${E(e.name)}</b><small>${E(e.kind)} · ${E(SPORT[e.sport]||e.sport)}</small>${e.note?`<p>${E(e.note)}</p>`:''}</div>`).join('')}${error?'<p role="status">Workout records could not load. <button type="button" data-detail-retry>Try again</button></p>':!row?'<p role="status">Loading this day…</p>':items.length?items.map(renderSession).join(''):plannedFor(value,items).length?`<section class="tc-planned"><h4>Planned in your program</h4>${plannedFor(value,items).map(x=>`<article class="tc-session tc-session-planned"><header>${icon(x.sport)}<div><h4>${E(x.purpose||SPORT[x.sport]||'Session')}</h4><p>${E(SPORT[x.sport]||x.sport)}${Array.isArray(x.minutes)?' · '+E(x.minutes[0])+'–'+E(x.minutes[1])+' min':''}${x.role?' · '+E(x.role==='improve'?'build':'maintain'):''}${Array.isArray(x.lift_groups)?' · '+E(x.lift_groups.join(', ')):''} · <span class="tc-session-state">planned</span></p></div></header></article>`).join('')}<small>A placeholder from your program. The actual workout is written the week before, from your reports.</small></section>`:'<p>No workouts saved for this day.</p>'}${row&&!items.length&&value<getToday()?'<small>No record does not establish that this was a rest day.</small>':''}`;
  }
  async function select(value){
   date(value);selected=value;showDetails(value);body.querySelectorAll('.tc-day').forEach(updateTile);
   try{if(!records.has(value))await fetchWeek(value);if(selected===value&&detailOpen){update();showDetails(value);}}
   catch(e){if(selected===value&&detailOpen)showDetails(value,true);}
  }
  function jump(m){
   date(m+'-01');dialog.querySelector('#tc-month').value=m;if(m<start||m>end){start=shiftMonth(m,-3);end=shiftMonth(m,8);render();}
   focusMonth=m;const el=body.querySelector(`[data-month="${m}"]`);if(el){el.scrollIntoView({block:'start',behavior:'instant'});loadMonth(el);}notice(date(m+'-01').toLocaleDateString(undefined,{month:'long',year:'numeric'}));
  }
  async function open(){
   const previous=dialog.open;program=getProgram()||{};plannedBy=plannedMap(program);phases=(program.phases||[]).slice().sort((a,b)=>a.start.localeCompare(b.start));
   events=(program.events||[]).filter(e=>/^\d{4}-\d{2}-\d{2}$/.test(e.date||'')).slice().sort((a,b)=>a.date.localeCompare(b.date));
   revision++;requests=new Map();records=new Map();queued=new Set();failed=new Set();queue=[];
   (options.getKnownDays?.()||[]).forEach(row=>records.set(row.date,row));
   if(!start)initialRange();dialog.querySelector('#tc-month').value=focusMonth||monthOf(getToday());render();if(!previous)dialog.showModal();if(detailOpen&&selected)select(selected);
   requestAnimationFrame(()=>{const m=focusMonth||monthOf(getToday());if(months().slice(0,3).includes(m)){dialog.scrollTop=0;loadMonth(body.querySelector(`[data-month="${m}"]`));notice(date(m+'-01').toLocaleDateString(undefined,{month:'long',year:'numeric'}));}else jump(m);});
  }
  dialog.addEventListener('click',e=>{
   const target=e.target.closest('button');if(!target)return;
   if(target.hasAttribute('data-upcoming-list')){openUpcomingList();return;}
   if(target.hasAttribute('data-add-event')){options.onAddEvent?.();return;}
   if(target.hasAttribute('data-remove-event')){target.disabled=true;Promise.resolve(options.onRemoveEvent?.(target.dataset.removeEvent)).then(()=>open()).catch(error=>{notice(error.message);target.disabled=false;});return;}
   if(target.dataset.date){select(target.dataset.date);return;}
   if(target.hasAttribute('data-event-index')){const index=Number(target.dataset.eventIndex),event=events[index];if(event?.date>=getToday()){focusedEventId=event.id;const remove=body.querySelector('[data-remove-event]');if(remove){remove.dataset.removeEvent=event.id;remove.setAttribute('aria-label','Remove '+event.name+' from scheduled events');}}openEvent(index);return;}
   if(target.dataset.phaseDate){const value=target.dataset.phaseDate;jump(monthOf(value));select(value);return;}
   if(target.hasAttribute('data-detail-close')){detailOpen=false;dialog.querySelector('#tc-day-detail').hidden=true;const chosen=body.querySelector(`[data-date="${selected}"]:not(.tc-adjacent)`);chosen?.focus();return;}
   if(target.hasAttribute('data-detail-retry')){select(selected);return;}
   if(target.dataset.retry){queued.delete(target.dataset.retry);loadMonth(body.querySelector(`[data-month="${target.dataset.retry}"]`));return;}
   if(target.dataset.range){const before=dialog.scrollHeight,scroll=dialog.scrollTop;if(target.dataset.range==='earlier')start=shiftMonth(start,-6);else end=shiftMonth(end,6);render();if(target.dataset.range==='earlier')requestAnimationFrame(()=>{dialog.scrollTop=scroll+dialog.scrollHeight-before;});}
  });
  dialog.querySelector('#tc-today').onclick=()=>{jump(monthOf(getToday()));select(getToday());};
  dialog.querySelector('#tc-jump').onclick=()=>{const input=dialog.querySelector('#tc-month');if(input.value)try{jump(input.value);}catch(e){notice(e.message);}else input.focus();};
  dialog.querySelector('#tc-month').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();dialog.querySelector('#tc-jump').click();}});
  dialog.querySelector('#tc-phases').onchange=e=>{shownPhases=e.target.checked;body.classList.toggle('tc-hide-phases',!shownPhases);};
  dialog.querySelector('#tc-close').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{if(eventWindow.open)eventWindow.close();if(upcomingWindow.open)upcomingWindow.close();observer?.disconnect();revision++;queue=[];});
  return {open,select,jump,refreshEvents:()=>{program=getProgram()||{};plannedBy=plannedMap(program);events=(program.events||[]).filter(e=>/^\d{4}-\d{2}-\d{2}$/.test(e.date||'')).slice().sort((a,b)=>a.date.localeCompare(b.date));refreshEventGroups();body.querySelectorAll('.tc-day').forEach(updateTile);},openEventById:(id,value,name)=>openEvent(events.findIndex(e=>id?e.id===id:e.date===value&&e.name===name))};
 }
 const api={date,iso,addDays,monthOf,shiftMonth,monthDays,phaseAt,phaseState,overlapsMonth,dayDifference,weekStart,sessionsFor,create};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.TrainingCalendar=api;
})(typeof window!=='undefined'?window:globalThis);
