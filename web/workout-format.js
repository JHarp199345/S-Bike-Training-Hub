/* Presentation only: forecasts use the Hub's existing lifting calculator. */
(function(root){
 'use strict';
 const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const stages=[['warmup','Warm-up','Prepare for the work'],['main','Main work','The focus of this session'],['cooldown','Cool-down','Ease out of the session']];
 let serial=0;const cache=new Map();
 const num=v=>Number.isFinite(Number(v))&&v!==null&&v!==''?Number(v):null;
 function section(x){if(x.section==='warmup'||x.section==='cooldown')return x.section;const cue=String(x.how||'').match(/^(warm[ -]?up|cool[ -]?down)\b/i);return cue?(/^warm/i.test(cue[1])?'warmup':'cooldown'):'main';}
 function stepSection(t){return /^(?:warm[ -]?up|easy movement|dynamic stretch)/i.test(t)?'warmup':/^(?:cool[ -]?down)/i.test(t)?'cooldown':'main';}
 function organize(session){
  const original=session.lifts||[],first=original.findIndex(x=>x.style==='build'),last=original.map(x=>x.style).lastIndexOf('build');
  const infer=original.length&&!original.some(x=>x.section)&&first>=0;
  const lifts=original.map((x,i)=>({...x,...(infer&&x.style==='restorative'&&(i<first||i>last)?{section:i<first?'warmup':'cooldown'}:{})}));
  return {lifts,inferred:!!infer&&lifts.some(x=>x.section)};
 }
 function totals(lifts){
  let kg=0,seconds=0,unknownWeight=0,unknownTime=0,assumed=0;
  for(const x of lifts.filter(x=>x.name&&x.done!==false)){
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
  return {kg,seconds,unknownWeight,unknownTime,assumed};
 }
 function metrics(lifts,actual=false){
  const t=totals(lifts),unit=lifts.find(x=>x.unit)?.unit==='kg'?'kg':'lb',weight=t.kg/(unit==='kg'?1:.45359237);
  return `<div class="wf-metrics"><div><span>External weight moved${t.unknownWeight?' · partial':''}</span><strong>${weight.toLocaleString(undefined,{maximumFractionDigits:0})} ${unit}</strong></div><div><span>Active time${t.assumed||t.unknownTime?' · estimated':''}</span><strong>${Math.floor(t.seconds/60)}m ${Math.round(t.seconds%60)}s</strong></div></div><p class="wf-footnote">Sets × reps × entered external weight; static holds and body weight are excluded from weight moved. Active time includes holds, excludes rest${t.assumed?'; unspecified tempo uses the Hub’s 4 seconds per rep estimate':''}.${t.unknownWeight?' Some working weights are missing; the weight total is incomplete.':''}${t.unknownTime?' Some exercise durations are missing.':''}${actual?' Based on logged details.':''}</p>`;
 }
 function exercise(x){return `<li><div><b>${E(x.name)}</b><span>${E(x.sets??'—')} × ${x.seconds?E(x.seconds)+' s':E(x.rep_range||x.reps||'—')}${x.per_side?' per side':''}${x.weight!=null?' · '+E(x.weight)+' '+E(x.unit||'lb'):''}${x.tempo?' · tempo '+E(x.tempo):''}${x.hold?' · '+E(x.hold)+' s hold per rep':''}${x.rest_seconds?' · rest '+E(x.rest_seconds)+' s':''}</span>${x.how?`<small>${E(x.how)}</small>`:''}</div></li>`;}
 function render(session,options={}){
  if(session.sport==='run'&&session.run_recipe&&root.RunWorkout)return root.RunWorkout.render(session.run_recipe);
  if(session.sport==='swim'&&session.swim_recipe&&root.SwimWorkout)return root.SwimWorkout.render(session.swim_recipe);
  if(session.sport==='rest'&&root.RestCard)return root.RestCard.render(session,options.context||{});
  const organized=organize(session),lifts=organized.lifts.filter(x=>x.name&&x.done!==false),steps=(session.steps||[]).map(String),id='wf-'+(++serial),actual=!!options.actual;
  const mainPhoto=({gym:'/web/sports/phase-lifting.jpg',swim:'/web/sports/phase-foundation.jpg',run:'/web/sports/community-road-run.jpg',ride:'/web/sports/phase-development.jpg'})[session.sport]||'/web/sports/phase-lifting.jpg';
  const html=`<div class="workout-format" id="${id}">${organized.inferred?'<p class="wf-footnote">Sections grouped from the saved exercise order and restorative/build labels. Edit the workout to confirm or change them.</p>':''}${stages.map(([key,title,subtitle])=>{
   const xs=lifts.filter(x=>section(x)===key),lines=steps.filter(t=>stepSection(t)===key&&(key!=='main'||!lifts.length));
   return `<section class="wf-section wf-${key}${!xs.length&&!lines.length?' wf-unspecified':''}"${key==='main'?` style="--wf-photo:url('${mainPhoto}')"`:''}><header><div><span class="wf-kicker">${E(subtitle)}</span><h4>${title}</h4></div><span class="wf-load" data-wf-load="${key}">${xs.length?actual?(xs.every(x=>num(x.points)!==null)?xs.reduce((a,x)=>a+Number(x.points),0).toFixed(1)+' strength points · estimate':'Logged load unavailable'):options.preview?'Load not yet evaluated':'Estimating load…':lines.length?'Load not separately estimated':'Not specified'}</span></header><div class="wf-body">${lines.length?`<ul class="wf-guidance">${lines.map(t=>`<li>${E(t)}</li>`).join('')}</ul>`:''}${xs.length?`<ul class="wf-exercises">${xs.map((x,n)=>(x.block&&(!n||xs[n-1].block!==x.block)?`<li class="wf-block-title"><b>${E(x.block)}${x.block_repeats>1?` · ${x.block_repeats} rounds (included in sets)`:''}</b></li>`:'')+(options.exerciseHTML?options.exerciseHTML(x,lifts.indexOf(x)):exercise(x))).join('')}</ul>${metrics(xs,actual)}`:!lines.length?'<p class="wf-empty">No details saved for this section.</p>':''}</div></section>`;
  }).join('')}${lifts.length?`<footer class="wf-total"><h4>Session totals ${actual?'· logged':'· planned'}</h4>${metrics(lifts,actual)}<p class="wf-footnote" data-wf-total>${actual&&lifts.every(x=>num(x.points)!==null)?lifts.reduce((a,x)=>a+Number(x.points),0).toFixed(1)+' strength points · logged estimate. ':''}Load estimates describe the entered exercises; any unrecorded warm-up or cool-down is not included.</p></footer>`:''}</div>`;
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
 root.WorkoutFormat={render,totals,section,stepSection,organize};
 if(typeof module!=='undefined')module.exports=root.WorkoutFormat;
})(typeof window!=='undefined'?window:globalThis);
