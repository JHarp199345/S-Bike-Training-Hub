/* Presentation only: forecasts use the Hub's existing lifting calculator. */
(function(root){
 'use strict';
 const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 // Similarity groups are curated visual families, not automatic semantic guesses.
 function artFamily(a){return a?.similarity_group||a?.family||a?.file||a?.id;}
 function adjacentArt(candidates,neighbors=[],preferred){const blocked=new Set(neighbors.filter(Boolean).map(artFamily));const files=new Set(neighbors.filter(Boolean).map(a=>a.file));const valid=candidates.filter(a=>!blocked.has(artFamily(a))&&!files.has(a.file));return valid.find(a=>a.id===preferred)||valid[0]||null;}
 root.WorkoutArt={family:artFamily,chooseAdjacent:adjacentArt};
 const stages=[['warmup','Warm-up','Prepare for the work'],['main','Main work','The focus of this session'],['cooldown','Cool-down','Ease out of the session']];
 let serial=0;const cache=new Map();
 const num=v=>Number.isFinite(Number(v))&&v!==null&&v!==''?Number(v):null;
 function section(x){if(['warmup','main','cooldown'].includes(x.section))return x.section;const cue=String(x.how||'').match(/^(warm[ -]?up|cool[ -]?down)\b/i);return cue?(/^warm/i.test(cue[1])?'warmup':'cooldown'):'main';}
 function stepSection(t){return /^(?:warm[ -]?up|easy movement|dynamic stretch)/i.test(t)?'warmup':/^(?:cool[ -]?down)/i.test(t)?'cooldown':'main';}
 function organize(session){
  const original=session.lifts||[],first=original.findIndex(x=>x.style==='build'),last=original.map(x=>x.style).lastIndexOf('build');
  const infer=original.length&&!original.some(x=>x.section)&&first>=0;
  const lifts=original.map((x,i)=>({...x,...(infer&&x.style==='restorative'&&(i<first||i>last)?{section:i<first?'warmup':'cooldown'}:{})}));
  return {lifts,inferred:!!infer&&lifts.some(x=>x.section)};
 }
 function totals(lifts){
  let kg=0,seconds=0,unknownWeight=0,unknownTime=0,assumed=0;
  for(const original of lifts.filter(x=>x.name&&x.done!==false)){
  for(const detail of original.set_details||[original]){
   if(detail.done===false)continue;const x={...original,...detail,sets:original.set_details?1:original.sets};
   const sets=num(x.sets),reps=num(x.reps),secs=num(x.seconds),w=num(x.weight),sides=x.per_side?2:1;
   if(sets===null||sets<=0){unknownTime++;unknownWeight++;continue;}
   const count=sets*sides;
   if(reps!==null&&reps>0){
    if(w!==null&&['lb','kg'].includes(x.unit||'lb'))kg+=count*reps*w*((x.unit||'lb')==='kg'?1:.45359237);else if(x.kind!=='bodyweight')unknownWeight++;
    const parts=String(x.tempo||'').match(/\d+/g),tempo=parts?parts.slice(0,4).reduce((a,b)=>a+Number(b),0):0;
    if(!tempo)assumed++;
    seconds+=count*reps*((tempo||4)+(num(x.hold)||0));
   }else if(secs!==null&&secs>0){seconds+=count*secs;}
   else{unknownTime++;unknownWeight++;}
  }
  }
  return {kg,seconds,unknownWeight,unknownTime,assumed};
 }
 function metrics(lifts,actual=false){
  const t=totals(lifts),unit=lifts.find(x=>x.unit)?.unit==='kg'?'kg':'lb',weight=t.kg/(unit==='kg'?1:.45359237);
  return `<div class="wf-metrics"><div><span>External weight moved${t.unknownWeight?' · partial':''}</span><strong>${weight.toLocaleString(undefined,{maximumFractionDigits:0})} ${unit}</strong></div><div><span>Active time${t.assumed||t.unknownTime?' · estimated':''}</span><strong>${Math.floor(t.seconds/60)}m ${Math.round(t.seconds%60)}s</strong></div></div><p class="wf-footnote">Sets × reps × entered external weight; static holds and body weight are excluded from weight moved. Active time includes holds, excludes rest${t.assumed?'; unspecified tempo uses the Hub’s 4 seconds per rep estimate':''}.${t.unknownWeight?' Some working weights are missing; the weight total is incomplete.':''}${t.unknownTime?' Some exercise durations are missing.':''}${actual?' Based on logged details.':''}</p>`;
 }
 function setTable(x,actual=true){
  const rows=x.set_details||Array.from({length:x.sets||1},()=>({...x,sets:1}));
  const hasReps=rows.some(a=>a.reps??x.reps);
  return `<div style="overflow-x:auto"><table class="wf-set-table"><thead><tr><th>Set</th><th>${hasReps?'Reps':'Time'}</th><th>Weight</th><th>Weight moved</th><th>Time under tension</th><th>Planned effort</th><th>Reported effort</th></tr></thead><tbody>${rows.map((a,i)=>{const r={...x,...a,sets:1},t=totals([{...r,set_details:undefined}]),v=r.reps&&r.weight!=null?r.reps*r.weight*(r.per_side?2:1):null;return `<tr><td>${i+1}${r.done===false?' · skipped':''}</td><td>${E(r.reps??(r.seconds!=null?r.seconds+' s':'—'))}</td><td>${r.weight!=null?E(r.weight)+' '+E(r.unit||'lb'):'—'}</td><td>${v!=null?E(v)+' '+E(r.unit||'lb'):'—'}</td><td>${Math.round(t.seconds)} s${t.assumed?' · estimate':''}</td><td>${x.planned_effort?.[i]!=null?E(x.planned_effort[i])+'/10':'—'}</td><td>${actual&&r.rpe!=null?E(r.rpe)+'/10':'—'}</td></tr>`;}).join('')}</tbody></table></div>`;
 }
 function sledInfo(x){
  const s=x.sled;if(!s)return '';const r=s.resistance_estimate;
  return `<div class="wf-sled-dose"><p><b>${E(s.model||'Sled')}</b> · magnets ${E(s.front_level??'—')}/${E(s.rear_level??'—')}${s.distance_m?' · '+(s.distance_m/.9144).toLocaleString(undefined,{maximumFractionDigits:0})+' yd total':''}</p>${s.seconds_low&&s.seconds_high?`<p>${E(s.seconds_low)}–${E(s.seconds_high)} seconds per trip · ${E(s.duration_basis||'duration estimated')}</p>`:''}${x.comfort?`<p>Reported response: ${E(x.comfort.replaceAll('_',' '))}.</p>`:''}${r?`<p>Estimated pace ${E(r.speed_mph_low)}–${E(r.speed_mph_high)} mph. Friction-sled weight equivalent: ${r.equivalent_weight_lb_low!=null&&r.equivalent_weight_lb_high!=null?E(r.equivalent_weight_lb_low)+'–'+E(r.equivalent_weight_lb_high)+' lb':r.equivalent_weight_lb_high!=null?'up to approximately '+E(r.equivalent_weight_lb_high)+' lb at the faster end; slower end outside the chart':'outside the published chart range'}.</p><p class="wf-footnote">${E(r.basis)} <a href="https://www.torquefitness.com/pages/tank-faq" target="_blank" rel="noopener">Torque chart</a></p>`:''}${x.load_range?`<p>Estimated strength load ${E(x.load_range.points_low)}–${E(x.load_range.points_high)} points; ${E(x.points)} points logged. ${E(x.load_range.basis)}.</p>`:''}</div>`;
 }
 function exercise(x,actual=false){return `<li><div><b>${E(x.name)}</b><span>${E(x.sets??'—')} sets${x.reps?' × '+E(x.reps)+' reps':''}${x.per_side?' per side':''}${x.weight!=null?' · '+E(x.weight)+' '+E(x.unit||'lb'):''}${x.tempo?' · tempo '+E(x.tempo):''}${x.hold?' · '+E(x.hold)+' s hold per rep':''}</span>${x.how?`<small>${E(x.how)}</small>`:''}${!actual?`<span class="wf-effort-slot">Planned effort: ${x.planned_effort?.some(v=>v!=null)?E(x.planned_effort.map(v=>v??'—').join(', ')):'—'} /10 · optional · edit RPE in workout text</span>`:''}${setTable(x,actual)}${sledInfo(x)}</div></li>`;}

 function render(session,options={}){
  if(session.sport==='run'&&session.run_recipe&&root.RunWorkout)return root.RunWorkout.render(session.run_recipe);
  if(session.sport==='swim'&&session.swim_recipe&&root.SwimWorkout)return root.SwimWorkout.render(session.swim_recipe);
  if(session.sport==='rest'&&root.RestCard)return root.RestCard.render(session,options.context||{});
  const organized=organize(session),lifts=organized.lifts.filter(x=>x.name&&x.done!==false),steps=(session.steps||[]).map(String),id='wf-'+(++serial),actual=!!options.actual;
  const mainPhoto=({gym:'/web/sports/phase-lifting.jpg',swim:'/web/sports/phase-foundation.jpg',run:'/web/sports/community-road-run.jpg',ride:'/web/sports/phase-development.jpg'})[session.sport]||'/web/sports/phase-lifting.jpg';
  const stageArt=[{id:'warmup',file:'/web/sports/phase-mobility-morning.jpg',similarity_group:'floor-mobility'},{id:'main',file:mainPhoto,similarity_group:session.sport==='gym'?'barbell-standing':session.sport},{id:'cooldown',file:'/web/sports/phase-recovery-stretch.jpg',similarity_group:'floor-mobility'}];
  let previousArt=null;const photos={};for(const [key] of stages){const pick=adjacentArt(stageArt,[previousArt],key);photos[key]=pick;previousArt=pick;}
  const html=`<div class="workout-format" id="${id}">${organized.inferred?'<p class="wf-footnote">Sections grouped from the saved exercise order and restorative/build labels. Edit the workout to confirm or change them.</p>':''}${stages.map(([key,title,subtitle])=>{
   const xs=lifts.filter(x=>section(x)===key),lines=steps.filter(t=>stepSection(t)===key&&(key!=='main'||!lifts.length));
   return `<section class="wf-section wf-${key}${!xs.length&&!lines.length?' wf-unspecified':''}" data-art-family="${E(photos[key]?.similarity_group||'plain')}" style="--wf-photo:${photos[key]?`url('${photos[key].file}')`:'none'}"><header><div><span class="wf-kicker">${E(subtitle)}</span><h4>${title}</h4></div><span class="wf-load" data-wf-load="${key}">${xs.length?actual?(xs.every(x=>num(x.points)!==null)?xs.reduce((a,x)=>a+Number(x.points),0).toFixed(1)+' strength points · estimate':'Logged load unavailable'):options.preview?'Load not yet evaluated':'Estimating load…':lines.length?'Load not separately estimated':'Not specified'}</span></header><div class="wf-body">${lines.length?`<ul class="wf-guidance">${lines.map(t=>`<li>${E(t)}</li>`).join('')}</ul>`:''}${xs.length?`<ul class="wf-exercises">${xs.map((x,n)=>(x.block&&(!n||xs[n-1].block!==x.block)?`<li class="wf-block-title"><b>${E(x.block)}${x.block_repeats>1?` · ${x.block_repeats} rounds (included in sets)`:''}</b></li>`:'')+(options.exerciseHTML?options.exerciseHTML(x,lifts.indexOf(x)):exercise(x,actual))).join('')}</ul>${metrics(xs,actual)}`:!lines.length?'<p class="wf-empty">No details saved for this section.</p>':''}</div></section>`;
  }).join('')}${lifts.length?`<footer class="wf-total"><h4>Session totals ${actual?'· logged':'· planned'}</h4>${metrics(lifts,actual)}<p class="wf-footnote" data-wf-total>${actual&&lifts.every(x=>num(x.points)!==null)?(num(session.points_total)??lifts.reduce((a,x)=>a+Number(x.points),0)).toFixed(1)+' strength points · logged estimate. Section sums may differ due to rounding. ':''}Load estimates describe the entered exercises; any unrecorded warm-up or cool-down is not included.</p></footer>`:''}</div>`;
  if(lifts.length&&!actual&&!options.preview&&typeof document!=='undefined')setTimeout(()=>hydrate(id,lifts),0);
  return html;
 }
 async function hydrate(id,lifts){
  const payload=lifts.map(x=>({...x,unit:x.unit||'lb'})),key=JSON.stringify(payload);
  if(!cache.has(key))cache.set(key,fetch('/api/coach/lifting/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lifts:payload})}).then(async r=>{if(!r.ok)throw Error('Unavailable');const j=await r.json();if(j.error)throw Error(j.error);return j;}).catch(()=>{cache.delete(key);return null;}));
  const value=await cache.get(key),box=document.getElementById(id);if(!box)return;
  stages.forEach(([stage])=>{
   const indices=lifts.map((x,i)=>section(x)===stage?i:-1).filter(i=>i>=0),label=box.querySelector(`[data-wf-load="${stage}"]`);if(!indices.length)return;
   const rows=indices.map(i=>value?.exercises?.[i]),scored=rows.filter(r=>r?.scored),sum=scored.reduce((a,r)=>a+r.points,0);
   label.textContent=!value?'Load unavailable':scored.length===rows.length?sum.toFixed(1)+' strength points · estimate':scored.length?sum.toFixed(1)+' points · partial':'Load awaits exercise scoring';
  });
  const label=box.querySelector('[data-wf-total]');label.textContent=value?`${value.points_total} strength points${value.unscored?.length?' · incomplete estimate':' · estimate'}. Section points may differ slightly from the total due to rounding; they are not extra load. Unrecorded preparation or recovery work is excluded.`:'Load could not be retrieved. Weight and active-time totals remain available.';
 }
 root.WorkoutFormat={render,totals,section,stepSection,organize,setTable,sledInfo};
 if(typeof module!=='undefined')module.exports=root.WorkoutFormat;
})(typeof window!=='undefined'?window:globalThis);
