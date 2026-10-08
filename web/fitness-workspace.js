/* Shared observational dashboard. Reads normal Hub APIs; never writes athlete data. */
(()=>{
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>Number(n).toLocaleString(undefined,{maximumFractionDigits:2});
const GROUPS={'Feet & lower body':['feet','calves','quads','hamstrings','glutes','hip_flexors','adductors'],'Core & back':['abs','obliques','lower_back','trunk'],'Upper body':['shoulders','scapula','lats','serratus','pecs','traps','biceps','triceps','forearms','neck']};
const MUSCLES={shoulders:['front-deltoids','back-deltoids'],scapula:['upper-back'],lats:['upper-back'],serratus:['obliques'],pecs:['chest'],traps:['trapezius'],trunk:['abs','obliques','lower-back'],hip_flexors:['adductor'],glutes:['gluteal','abductors'],quads:['quadriceps'],hamstrings:['hamstring'],calves:['calves','left-soleus','right-soleus'],abs:['abs'],obliques:['obliques'],lower_back:['lower-back'],adductors:['adductor'],biceps:['biceps'],triceps:['triceps'],forearms:['forearm'],neck:['neck']};
const LOWER=new Set(GROUPS['Feet & lower body']);
let bodyContainer=null,bodyData=null,loading=null,liftingData=null,liftingSource=null;
const states=new WeakMap();
const ranges=(range)=>['28','90','all'].map(n=>`<button type="button" data-body-range="${n}" aria-pressed="${range===n}">${n==='all'?'All history':n+' days'}</button>`).join('');
function rowsFor(d,range){const start=range==='all'?d.history_start:new Date(Date.parse(d.as_of+'T12:00:00Z')-(+range-1)*86400000).toISOString().slice(0,10);return d.daily.filter(r=>r.date>=start);}
function sources(row,key){if(key==='muscle')return Object.fromEntries(Object.entries(row.sports).map(([s,v])=>[s,v.muscle]));return row.regions[key]?.sources||{};}
function value(row,key){return key==='muscle'?row.exposure.muscle:Object.values(sources(row,key)).reduce((a,v)=>a+(v||0),0);}
function rate(d,key){return d.daily.slice(-3).reduce((n,r)=>n+value(r,key),0)/3;}
function restore(container,html){const open=new Set([...container.querySelectorAll('details[open][data-preserve]')].map(e=>e.dataset.preserve));container.innerHTML=html;container.querySelectorAll('details[data-preserve]').forEach(e=>e.open=open.has(e.dataset.preserve));}
function lifting(container,d,F){if(!container)return;const old=container.querySelector('[data-lift-history]');const range=old?.dataset.range||'28';
 liftingData=d;liftingSource=F;
 const st=Object.entries(F.strength||{}),logs=F.recent||F.logs||[];
 restore(container,`<h3>Daily lifting volume</h3><div data-lift-history></div><h3>Completed sessions</h3>${d.lifts.slice().reverse().map((l,i)=>{const raw=logs.find(x=>x.date===l.date&&x.session===l.session)||{};return `<details class="wr-report" data-preserve="lift:${esc(l.date+':'+l.session)}"><summary>${esc(l.date+' · '+l.session)} · ${fmt(l.volume_lb)} lb</summary><p>${fmt(l.minutes)} min · ${l.j_per_min==null?'Rate unavailable':WorkRate.rateText(l.j_per_min)+' nominal mechanical work'}</p><div class="wr-scroll"><table class="wr-ledger"><tr><th>Exercise</th><th>Set</th><th>Load × reps</th><th>Poundage</th></tr>${l.sets.map(s=>`<tr><td>${esc(s.exercise)}</td><td>${s.set}</td><td>${fmt(s.weight)} ${esc(s.unit)} × ${s.reps}</td><td>${fmt(s.volume_kg/0.45359237)} lb</td></tr>`).join('')}</table></div>${l.excluded.length?`<p class="wr-note">Not included in nominal work: ${l.excluded.map(s=>esc(s.exercise)+' (set '+s.set+')').join(', ')}. Static work and unknown resistance remain recorded.</p>`:''}${(raw.lifts||[]).length?`<details data-preserve="original:${esc(l.date+':'+l.session)}"><summary>Original exercise details · including tempo and holds</summary>${raw.lifts.map(x=>`<p>${esc(x.name)} · ${esc(x.sets??'—')} sets · ${x.reps==null?'repetitions not recorded':esc(x.reps)+' reps'}${x.weight!=null?' · '+fmt(x.weight)+' '+esc(x.unit||'lb'):''}${x.per_side?' per side':''}${x.tempo?' · tempo '+esc(x.tempo):''}${x.seconds!=null?' · '+fmt(x.seconds)+' s':''}${x.sled?'<br> '+Object.entries(x.sled).filter(([,v])=>v!=null&&typeof v!=='object').map(([k,v])=>esc(k.replaceAll('_',' '))+': '+esc(v)).join(' · '):''}${x.hold!=null?' · hold '+esc(x.hold)+' s':''}${x.rpe!=null?' · effort '+esc(x.rpe):''}</p>`).join('')}</details>`:''}</details>`;}).join('')||'<p>No lifting sessions recorded.</p>'}<h3>Strength estimates</h3>${st.length?`<div class="wr-scroll"><table class="wr-ledger"><tr><th>Lift</th><th>Estimated maximum</th><th>Source set</th></tr>${st.map(([k,v])=>`<tr><td>${esc(k)}</td><td>${esc(v.e1rm)} ${esc(v.unit)}</td><td>${esc(v.from)}</td></tr>`).join('')}</table></div>`:'<p>No strength estimates recorded yet.</p>'}`);
 const h=container.querySelector('[data-lift-history]');h.dataset.metric='lifting';h.dataset.range=range;WorkRate.history(h,d,'lifting','28',{metricControls:false});
}
function calibration(container,L,T){if(!container)return;const known=new Set(Object.keys(T.calibration?.capacities||{}));const items=Object.entries(L.calibration_estimates||{}).filter(([k,v])=>v?.name&&!known.has(k)&&!(/block/i.test(v.name)));restore(container,items.length?`<details data-preserve="calculation"><summary>Additional calibration estimates & sources</summary><div class="wr-scroll"><table class="wr-ledger"><tr><th>Estimate</th><th>Value</th><th>Learned from</th><th>Confidence</th></tr>${items.map(([,v])=>`<tr><td>${esc(v.name)}</td><td>${v.value==null?'Not measured':esc(v.value)+' '+esc(v.unit||'')}</td><td>${esc(v.source||'Not tested')}</td><td>${v.confidence==null?'Not established':Math.round(v.confidence*100)+'%'}</td></tr>`).join('')}</table></div></details>`:'');}
// Body workload: the map with Overall and the three group buttons under it, and one main view beside it. Overall
// is a ring of every region's share of recorded work, with a spike for how concentrated it has been lately; a group
// shows all its regions as compact graphs (mouse: the rows under the pointer magnify, resting on one opens it;
// touch: tap opens it). The last view is remembered on this device; with none, Overall.
const VIEW_KEY='hub-body-view',OVERALL='Overall';
const FAMILY={'Feet & lower body':[203,70],'Core & back':[172,58],'Upper body':[40,72]};   // hue, saturation per group
function savedView(){try{return JSON.parse(localStorage.getItem(VIEW_KEY)||'null');}catch(e){return null;}}
function saveView(s){try{localStorage.setItem(VIEW_KEY,JSON.stringify({view:s.view,region:s.region,range:s.range}));}catch(e){}}
function body(container,d){
 if(!container||!d)return;bodyContainer=container;bodyData=d;
 const regions=d.daily.at(-1)?.regions||{};
 const groupFor=k=>k==='muscle'?'Feet & lower body':Object.keys(GROUPS).find(g=>GROUPS[g].includes(k));
 const keysFor=g=>(g==='Feet & lower body'?['muscle',...GROUPS[g]]:GROUPS[g]||[]).filter(k=>k==='muscle'||regions[k]);
 let state=states.get(container);
 if(!state){const saved=savedView()||{};const view=saved.view===OVERALL||GROUPS[saved.view]?saved.view:OVERALL;
  state={view,region:view!==OVERALL&&keysFor(view).includes(saved.region)?saved.region:null,range:['28','90','all'].includes(saved.range)?saved.range:'28',day:null};states.set(container,state);}
 const rows=rowsFor(d,state.range),days=Math.max(1,rows.length);
 const label=k=>k==='muscle'?'Leg muscles · combined index':regions[k]?.name||k;
 const totals={};for(const k of ['muscle',...Object.keys(regions)])totals[k]=rows.reduce((n,r)=>n+value(r,k),0);
 const dateCaption=`${rows[0]?.date||d.as_of} – ${d.as_of}`;
 clearTimeout(state.hoverTimer);
 container.innerHTML=`<div class="wr-heading"><div><h2>Body workload</h2><p class="wr-note">Recorded work by region. Choose Overall or a body group under the map; select a muscle on the map to open its graph.</p></div></div><div class="wr-tools" role="group" aria-label="Body workload period" data-body-periods>${ranges(state.range)}</div><p class="wr-note">${esc(dateCaption)} · averages over ${rows.length} available calendar days. Days before recorded history are unknown.</p><div class="fw-body-layout" data-body-layout><div class="fw-map-panel"><div class="fw-figures"><div><small>FRONT</small><div data-body-front></div></div><div><small>BACK</small><div data-body-back></div></div></div><p class="wr-note" data-body-map-caption></p><div class="fw-views" role="group" aria-label="Body workload view">${[OVERALL,...Object.keys(GROUPS)].map(v=>`<button type="button" data-body-view="${esc(v)}" aria-pressed="false">${v===OVERALL?'<span class="fw-ring-icon" aria-hidden="true"></span>':`<span class="fw-swatch" style="--h:${FAMILY[v][0]}" aria-hidden="true"></span>`}${esc(v)}</button>`).join('')}</div></div><div class="fw-main" data-body-main aria-live="polite"></div></div>`;
 const main=container.querySelector('[data-body-main]');
 function show(view,region=null,{scroll=false}={}){
  clearTimeout(state.hoverTimer);
  if(view!==state.view||region!==state.region)state.day=null;
  state.view=view;state.region=region;saveView(state);
  container.querySelectorAll('[data-body-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.bodyView===view)));
  if(view===OVERALL)overall();else group(view);
  drawMap();
  if(scroll&&matchMedia('(max-width: 700px)').matches)main.scrollIntoView({behavior:'smooth',block:'start'});
 }
 // ── Overall: share of work by region, spikes for recent concentration ──
 function overall(){
  const keys=Object.keys(GROUPS).flatMap(g=>GROUPS[g].filter(k=>regions[k]).map(k=>({k,g})));
  const sum=keys.reduce((n,x)=>n+totals[x.k],0);
  if(!sum){main.innerHTML=`<h3>Overall</h3><p class="wr-note">No regional work recorded in this period.</p>`;return;}
  const recentStart=d.windows['3'].start;
  const items=keys.map((x,i)=>{const usual=totals[x.k]/days,recent=rate(d,x.k);const ratio=usual>0?recent/usual:(recent>0?3:0);
   const within=GROUPS[x.g].indexOf(x.k),n=GROUPS[x.g].length,[h,s]=FAMILY[x.g];
   return {...x,share:totals[x.k]/sum,usual,recent,ratio,color:`hsl(${h} ${s}% ${68-within*(34/Math.max(1,n-1))}%)`};});
  const C=210,R0=92,R1=140,SPIKE=58,TWO=Math.PI*2;let a=-Math.PI/2;
  const pt=(r,t)=>`${(C+r*Math.cos(t)).toFixed(1)} ${(C+r*Math.sin(t)).toFixed(1)}`;
  // Slices are sized by the square root of each share, with a floor, so small regions keep room for their spikes;
  // the list and tooltips keep the true shares.
  const shown=items.filter(x=>x.share>0),roots=shown.map(x=>Math.sqrt(x.share)),rootSum=roots.reduce((n,v)=>n+v,0),floor=.45/shown.length;
  const raw=roots.map(v=>Math.max(floor,v/rootSum)),rawSum=raw.reduce((n,v)=>n+v,0);shown.forEach((x,i)=>x.arc=raw[i]/rawSum);
  const slices=shown.map(x=>{const a0=a,a1=a+x.arc*TWO;a=a1;const big=a1-a0>Math.PI?1:0,mid=(a0+a1)/2,gap=Math.min(.012,(a1-a0)/4);
   const p=`M${pt(R1,a0+gap)} A${R1} ${R1} 0 ${big} 1 ${pt(R1,a1-gap)} L${pt(R0,a1-gap)} A${R0} ${R0} 0 ${big} 0 ${pt(R0,a0+gap)}Z`;
   const len=Math.min(3,x.ratio)/3*SPIKE;
   return `<g class="fw-slice" data-ring-region="${x.k}" tabindex="0" role="button" aria-label="${esc(label(x.k))}: ${Math.round(x.share*100)}% of recorded work, recent ${fmt(x.ratio)} times usual"><title>${esc(label(x.k))} · ${Math.round(x.share*1000)/10}% of work · last 3 days ${fmt(x.recent)} vs usual ${fmt(x.usual)} pts/day</title><path d="${p}" fill="${x.color}"/>${len>0?`<line x1="${pt(R1+4,mid).split(' ')[0]}" y1="${pt(R1+4,mid).split(' ')[1]}" x2="${pt(R1+4+len,mid).split(' ')[0]}" y2="${pt(R1+4+len,mid).split(' ')[1]}" stroke="${x.color}" stroke-width="${x.ratio>1.5?4:2.5}" stroke-linecap="round"/><circle cx="${pt(R1+4+len,mid).split(' ')[0]}" cy="${pt(R1+4+len,mid).split(' ')[1]}" r="${x.ratio>1.5?4.5:3}" fill="${x.color}"/>`:''}</g>`;}).join('');
  const total=sum/days;
  main.innerHTML=`<h3>Overall</h3><p class="wr-note">Each slice is a region's share of recorded work, ${esc(dateCaption)}; the ring is compressed so small regions stay visible, and the list shows true shares. Spikes show how concentrated it has been lately: the last 3 calendar days (${esc(recentStart)} – ${esc(d.as_of)}) against that region's usual day in the period. The dashed ring marks “as usual”.</p><div class="fw-overall"><svg class="fw-ring" viewBox="0 0 420 420" role="img" aria-label="Share of recorded work by body region"><circle cx="${C}" cy="${C}" r="${R1+4+SPIKE/3}" fill="none" stroke="#9fc3da" stroke-opacity=".35" stroke-dasharray="3 5"/>${slices}<text x="${C}" y="${C-6}" text-anchor="middle" class="fw-ring-total">${fmt(Math.round(total*10)/10)}</text><text x="${C}" y="${C+16}" text-anchor="middle" class="fw-ring-unit">pts/day, all regions</text></svg><ol class="fw-legend">${items.slice().sort((x,y)=>y.share-x.share).map(x=>`<li><button type="button" data-ring-region="${x.k}"><i style="background:${x.color}"></i><span>${esc(label(x.k))}</span><b>${x.share?Math.round(x.share*100)+'%':'—'}</b><small class="${x.ratio>=1.5?'is-hot':''}">${x.share?(x.ratio>=1.05?'↑ ':x.ratio<=.95?'↓ ':'')+fmt(Math.round(x.ratio*10)/10)+'× usual':'no work recorded'}</small></button></li>`).join('')}</ol></div><p class="wr-note">Regions are separate estimates that overlap (one exercise loads several), so shares compare where recorded work went, not physical force.</p>`;
  main.querySelectorAll('[data-ring-region]').forEach(el=>{const open=()=>{const k=el.dataset.ringRegion;show(groupFor(k),k,{scroll:true});};el.onclick=open;el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}};
   el.onpointerenter=()=>main.querySelectorAll(`[data-ring-region="${el.dataset.ringRegion}"]`).forEach(x=>x.classList.add('is-hover'));el.onpointerleave=()=>main.querySelectorAll('.is-hover').forEach(x=>x.classList.remove('is-hover'));});
 }
 // ── A group: every region as a compact graph; the mouse magnifies, resting opens; a tap opens ──
 function group(g){
  const keys=keysFor(g);
  main.innerHTML=`<h3>${esc(g)}</h3><p class="wr-note">${matchMedia('(hover: hover)').matches?'Move over the graphs to magnify them; rest on one to open it.':'Tap a graph to open it.'}</p><div class="fw-group-rows" data-group-rows>${keys.map(k=>`<article class="fw-region-row" data-region-row="${k}"><button type="button" class="fw-region-toggle" data-region="${k}" aria-expanded="false"><span>${esc(label(k))}</span><span>${fmt(totals[k]/days)} <small>pts/day</small></span></button><div class="fw-region-mini" aria-hidden="true">${rows.map(r=>`<i style="height:${Math.max(3,value(r,k)/Math.max(1,...rows.map(x=>value(x,k)))*100)}%"></i>`).join('')}</div><div class="fw-region-expanded"><div class="fw-region-expanded-inner" data-region-detail="${k}"></div></div></article>`).join('')||'<p class="wr-note">No regions recorded in this group yet.</p>'}</div>`;
  const list=main.querySelector('[data-group-rows]');
  main.querySelectorAll('[data-region]').forEach(b=>b.onclick=()=>open(b.dataset.region===state.region?null:b.dataset.region));
  // Magnify by distance from the pointer; open after resting ~0.7 s. Only real pointer motion counts, so rows
  // moving under a still mouse (an opening graph) never open another one.
  let last=null;
  list.onpointermove=e=>{if(e.pointerType!=='mouse'||!matchMedia('(hover: hover)').matches)return;
   if(last&&Math.hypot(e.clientX-last.x,e.clientY-last.y)<4)return;last={x:e.clientX,y:e.clientY};
   for(const row of list.children){const r=row.getBoundingClientRect(),dist=Math.abs(e.clientY-(r.top+Math.min(r.height,70)/2));const m=Math.max(0,1-dist/150);row.style.setProperty('--mag',m.toFixed(3));row.classList.toggle('is-near',m>.72);}
   const row=e.target.closest('[data-region-row]');clearTimeout(state.hoverTimer);
   if(row&&row.dataset.regionRow!==state.region)state.hoverTimer=setTimeout(()=>open(row.dataset.regionRow),700);};
  list.onpointerleave=()=>{clearTimeout(state.hoverTimer);last=null;for(const row of list.children){row.style.removeProperty('--mag');row.classList.remove('is-near');}};
  open(state.region&&keys.includes(state.region)?state.region:null,true);
 }
 function open(key,initial=false){
  clearTimeout(state.hoverTimer);
  if(!initial&&key!==state.region){state.day=null;state.region=key;saveView(state);drawMap();}
  container.querySelectorAll('[data-region-row]').forEach(row=>{const active=row.dataset.regionRow===key;row.classList.toggle('is-active',active);row.querySelector('[data-region]').setAttribute('aria-expanded',String(active));const ex=row.querySelector('.fw-region-expanded');ex.inert=!active;ex.setAttribute('aria-hidden',String(!active));});
  if(key){const target=container.querySelector(`[data-region-detail="${key}"]`);if(target&&!target.childElementCount)renderDetail(target,key);}
 }
 function renderDetail(target,key){
  target.dataset.metric=key;target.dataset.range=state.range;if(state.day)target.dataset.selectedDay=state.day;else delete target.dataset.selectedDay;
  WorkRate.regional(target,d,key,{controls:false});
  const sourceRates={};for(const row of rows)for(const [source,v]of Object.entries(sources(row,key)))sourceRates[source]=(sourceRates[source]||0)+v/days;
  const sourceNames={run:'Running',bike:'Cycling',swim:'Swimming',lift:'Lifting',impact:'Impact',gym:'Gym'};
  target.querySelector('h3').insertAdjacentHTML('afterend',`<p class="fw-region-reading"><b>${fmt(totals[key]/days)} pts/day</b>${esc(dateCaption)} average · ${rows.length} available days<br><strong>${fmt(rows.slice(-28).reduce((n,r)=>n+value(r,key),0))} pts</strong> carried over the last 28 days<br><strong>${fmt(rate(d,key))} pts/day</strong> latest 3 calendar days · ${esc(d.windows['3'].start)} – ${esc(d.as_of)}</p><p class="wr-note">${key==='muscle'?'Combined leg index adds the recorded muscle contributions by sport. Individual region graphs use the largest source estimate for each day. These are different indices, not physical forces.':'Bars stack every source each day: muscle points by sport add up; impact (bone & tendon, from running) is a separate tissue measure, hatched on top.'} Source averages: ${Object.entries(sourceRates).filter(([,v])=>v>0).map(([source,v])=>esc(sourceNames[source]||source)+' '+fmt(v)+' pts/day').join(' · ')||'No exposure recorded'}.</p>`);
  target.querySelectorAll('[data-day]').forEach(b=>b.addEventListener('click',()=>{
   state.day=b.dataset.day;const row=rows.find(r=>r.date===state.day),ss=sources(row,key);target.querySelector('[data-body-sessions]')?.remove();target.insertAdjacentHTML('beforeend',`<div data-body-sessions><h4>${esc(state.day)} · contributing records</h4><p>${Object.entries(ss).filter(([,v])=>v>0).map(([k,v])=>esc(k)+' '+fmt(v)+' points').join(' · ')||'No exposure recorded'}</p>${d.activities.filter(a=>a.date===state.day&&a.source!=='lifts'&&(ss[a.sport]>0||(ss.lift>0&&d.lifts.some(l=>l.date===state.day&&l.source_activity_id===a.id)))).map(a=>`<p>${esc(a.sport)} · ${fmt(a.minutes)} min${a.calories_kcal!=null?' · '+fmt(a.calories_kcal)+' kcal':''}</p>`).join('')}${ss.lift>0?d.lifts.filter(l=>l.date===state.day).map(l=>`<p>${esc(l.session)} · ${fmt(l.volume_lb)} lb recorded dynamic volume</p>`).join(''):''}<p class="wr-note">Source participation is estimated; these records provide context.</p></div>`);
  }));if(state.day)target.querySelector(`[data-day="${state.day}"]`)?.click();
 }
 function drawMap(){
  const overallView=state.view===OVERALL,allowed=new Set(overallView?Object.values(GROUPS).flat():GROUPS[state.view]||[]),owner={};
  for(const [key,ms]of Object.entries(MUSCLES))for(const m of ms)if(!owner[m]||(allowed.has(key)&&!allowed.has(owner[m]))||(allowed.has(key)===allowed.has(owner[m])&&totals[key]>totals[owner[m]]))owner[m]=key;
  if(state.region&&MUSCLES[state.region])for(const m of MUSCLES[state.region])owner[m]=state.region;
  const peak=Math.max(1,...[...allowed].map(k=>totals[k]||0)),colors=['#355d7a','#487d9f','#66a3c6','#88bddb','#b7e2f5','#e9bb79'];
  const data=Object.entries(owner).filter(([,k])=>allowed.has(k)).map(([m,key])=>({name:regions[key]?.name||key,muscles:[m],frequency:key===state.region?6:Math.max(1,Math.ceil((totals[key]||0)/peak*5))}));
  container.querySelector('[data-body-map-caption]').textContent=(overallView?'All regions':state.view)+' · brighter blue means more recorded work in this period.'+(state.region&&state.region!=='muscle'?' '+label(state.region)+' is selected in gold.':'')+' Select a muscle to open its graph.';
  const token=Symbol();state.token=token;
  import('/web/vendor/body-highlighter.esm.js').then(({createBodyHighlighter})=>{if(state.token!==token)return;for(const [type,selector]of [['anterior','[data-body-front]'],['posterior','[data-body-back]']]){const host=container.querySelector(selector);host.replaceChildren();createBodyHighlighter({container:host,type,data,bodyColor:'#243c51',highlightedColors:colors,onClick:({muscle})=>{const key=owner[muscle];if(key)show(groupFor(key),key,{scroll:true});}});for(const x of [42,58]){const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');dot.setAttribute('cx',x);dot.setAttribute('cy','196');dot.setAttribute('r','2.7');dot.setAttribute('fill',state.region==='feet'?'#e9bb79':'#a2d4ee');dot.setAttribute('role','button');dot.setAttribute('tabindex','0');dot.setAttribute('aria-label','Feet and bones history');dot.style.cursor='pointer';dot.onclick=()=>show('Feet & lower body','feet',{scroll:true});dot.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();dot.onclick();}};host.querySelector('svg').append(dot);}}}).catch(()=>{container.querySelector('[data-body-front]').textContent='Map unavailable. Use the region graphs.';});
 }
 container.querySelectorAll('[data-body-range]').forEach(b=>b.onclick=()=>{state.range=b.dataset.bodyRange;saveView(state);body(container,bodyData);});
 container.querySelectorAll('[data-body-view]').forEach(b=>b.onclick=()=>{const v=b.dataset.bodyView;show(v,v===state.view?state.region:null);});
 show(state.view,state.region);
}
function openRegion(key){if(!bodyContainer||!bodyData)return;const state=states.get(bodyContainer);const k=key||'muscle';state.region=k;state.view=k==='muscle'?'Feet & lower body':Object.keys(GROUPS).find(g=>GROUPS[g].includes(k))||'Feet & lower body';state.day=null;saveView(state);body(bodyContainer,bodyData);bodyContainer.scrollIntoView({behavior:'smooth',block:'start'});bodyContainer.querySelector(`[data-region="${k}"]`)?.focus({preventScroll:true});}
async function refresh(){if(loading)return loading;const status=document.getElementById('fitness-status');loading=(async()=>{
 try{const [D,L,F,T]=await Promise.all([WorkRate.read(),...['/api/load','/api/coach/lifting','/api/coach/today'].map(async url=>{const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error('Hub readings unavailable');return r.json();})]);
 WorkRate.card(document.getElementById('work-rate-card'),D);lifting(document.getElementById('lifting-records-content'),D,F);body(document.getElementById('body-workload'),D);calibration(document.getElementById('calibration-extra'),L,T);
 window.dispatchEvent(new CustomEvent('fitness-readings',{detail:{load:L,today:T}}));
 if(status)status.textContent='Updated '+new Date().toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'})+' · today is in progress';
 return D;
 }catch(e){if(status)status.textContent='Latest readings could not load. Previous readings are retained; retry when the Hub is reachable.';return null;}
 })().finally(()=>loading=null);return loading;}
window.FitnessWorkspace={refresh,body,lifting,calibration,openRegion,rowsFor};
window.addEventListener('work-rate-region',e=>openRegion(e.detail));
window.addEventListener('energy-units-change',()=>{if(liftingData)lifting(document.getElementById('lifting-records-content'),liftingData,liftingSource);});
})();
