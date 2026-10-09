(function(root){
'use strict';
const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock=s=>s==null?'—':Math.floor(Math.round(s)/60)+':'+String(Math.round(s)%60).padStart(2,'0');
const artwork=[
 {id:'pool',file:'/web/sports/swim-pool-freestyle-v1.jpg',similarity_group:'swim-side-freestyle'},
 {id:'dawn',file:'/web/sports/swim-open-water-dawn-v1.jpg',similarity_group:'swim-side-freestyle'},
 {id:'overhead',file:'/web/sports/swim-open-water-breaststroke-v2.jpg',similarity_group:'swim-overhead-breaststroke'},
 {id:'butterfly',file:'/web/sports/swim-butterfly-fantasy-v1.jpg',similarity_group:'swim-front-butterfly'}
];
function chooseArt(groups){let previous=artwork[0];return [previous,...groups.map(g=>{const butterfly=g.sets.some(s=>s.stroke==='butterfly'||/\bbutterfly\b/i.test(s.description||'')),preferred=butterfly?'butterfly':g.section==='warmup'?'dawn':g.section==='cooldown'?'overhead':'pool';const pick=root.WorkoutArt?.chooseAdjacent(artwork,[previous],preferred)||artwork.find(a=>a.similarity_group!==previous?.similarity_group);previous=pick;return pick;})];}
function render(p,preview=false){
 const groups=[];for(const s of p.sets||[]){let g=groups.at(-1);if(!g||g.name!==s.group||g.section!==s.section){g={name:s.group,section:s.section,sets:[]};groups.push(g);}g.sets.push(s);}
 const art=chooseArt(groups);
 return `<div class="swim-recipe"><header data-art-family="${art[0].similarity_group}" style="--swim-photo:url('${art[0].file}')"><h3>${preview?'Swim preview':'Swim workout'} · ${Number(p.total_distance).toLocaleString()} ${E(p.unit)}</h3><p class="sub">${p.pool_length?E(p.pool_length)+' '+E(p.unit)+' pool · ':''}${p.completion_expected_minutes?`Set completion targets: goal ${clock(p.completion_goal_minutes*60)} · expected ${clock(p.completion_expected_minutes*60)}${p.all_completion_timed?'':' · partial targets'}`:`Timed send-off slots: ${p.sendoff_minutes} min${p.all_sendoffs?'':' · other sets untimed'}`} · rest may add session time</p></header><div class="swim-distance-chart" role="img" aria-label="Swim distance by set">${groups.map((g,i)=>`<i style="flex:${g.sets.reduce((n,s)=>n+s.distance_m,0)};background:${g.section==='warmup'?'#fb923c':g.section==='cooldown'?'#22d3ee':['#a78bfa','#facc15','#fb923c'][i%3]}" title="${E(g.name)}"></i>`).join('')}</div>${groups.map((g,i)=>`<section data-art-family="${art[i+1].similarity_group}" style="--swim-photo:url('${art[i+1].file}')" class="swim-set swim-${g.section}${g.sets.some(s=>s.stroke==='butterfly'||/\bbutterfly\b/i.test(s.description||''))?' swim-butterfly':''}"><header><h4>${E(g.name)}</h4><b>${(Math.round(g.sets.reduce((n,s)=>n+s.distance_m,0)/(p.unit==='yd'?.9144:1)*100)/100).toLocaleString()} ${E(p.unit)}</b></header>${g.sets.map(s=>`<div class="swim-set-line"><b>${s.repetitions>1?s.repetitions+' × ':''}${s.distance} ${E(s.unit)}</b> · ${E(s.description)}${s.notes?.length?'<p class="sub">'+s.notes.map(E).join(' · ')+'</p>':''}${s.goal_seconds!=null?`<small>Completion goal ${clock(s.goal_seconds)} · expected ${clock(s.expected_seconds)} · whole written set</small>`:''}${s.work==='drill'?'<small>Individual drill timing is optional. Want to track this drill separately? Remember or record its time, then add it after the swim.</small>':''}${s.sendoff_seconds!=null?`<small>Send off every ${clock(s.sendoff_seconds)} · start-to-start, not fixed rest</small>`:s.rest_seconds!=null?`<small>Rest ${s.rest_seconds} seconds after each repetition</small>`:s.goal_seconds==null?'<small>Timing not specified</small>':''}</div>`).join('')}</section>`).join('')}${(p.notes||[]).map(n=>'<p class="sub">'+E(n)+'</p>').join('')}${drillBlocks(p)}${preview?suggestedTimes(p):''}${preview?(p.issues||[]).map(n=>'<p class="note">'+E(n)+'</p>').join('')+(p.warnings||[]).map(n=>'<p class="sub">'+E(n)+'</p>').join(''):''}</div>`;
}
function drillBlocks(p){
 const blocks=[];for(const s of p.sets||[]){if(s.work!=='drill'){blocks.push(null);continue;}let b=blocks.at(-1);if(!b||b.section!==s.section){b={section:s.section,sets:[]};blocks.push(b);}b.sets.push(s);}
 return blocks.filter(b=>b&&b.sets.length>1).map(b=>`<p class="sub">Combined drill block · ${E(b.sets.map(s=>`${s.repetitions*s.distance} ${s.unit} ${s.description}`).join(' + '))}${b.sets.every(s=>s.goal_seconds!=null)?` · goal ${clock(b.sets.reduce((n,s)=>n+s.goal_seconds,0))} · expected ${clock(b.sets.reduce((n,s)=>n+s.expected_seconds,0))}`:''}. The watch may record these together. Individual times remain optional athlete reports.</p>`).join('');
}
function suggestedTimes(p){return (p.timing_suggestions||[]).length?`<aside class="swim-timing"><h4>Timing drafts from your history</h4>${p.timing_suggestions.map(x=>`<p>Set ${x.set_index+1} · recent best ${clock(x.recent_best_seconds)} · usual ${clock(x.expected_seconds)} · ${x.performances} comparable performances</p>`).join('')}<p class="sub">Review these as goal and expected times. Pool length, stroke, distance, work and equipment must match; differences in rests and conditions still matter.</p><button type="button" data-use-swim-timing>Use these times in my draft</button></aside>`:'';}
function difference(g){if(!g)return '—';return `${Math.abs(g.seconds_vs_expected).toFixed(0)} s ${g.seconds_vs_expected>=0?'faster than':'slower than'} expected (${Math.abs(g.percent_vs_expected)}%) · ${g.seconds_to_goal?g.seconds_to_goal+' s from goal':'goal reached'}`;}
function timingReport(t){
 if(!t)return '';
 return `<section class="swim-timing"><h3>Swim timing · goal and expectation</h3><p class="sub">${E(t.plan_basis)}. ${E(t.basis)}</p>${t.grade?`<p><b>${E(t.grade.status)}</b> · goal ${clock(t.goal_seconds)} · expected ${clock(t.expected_seconds)} · recorded ${clock(t.actual_seconds)}<br>${E(difference(t.grade))}</p>`:''}<div class="table-scroll"><table><thead><tr><th>Set or recorded block</th><th>Goal</th><th>Expected</th><th>Watch time</th><th>Comparison</th></tr></thead><tbody>${(t.rows||[]).map(x=>`<tr><td>${E(x.label)}${x.combined?'<small>Combined block · individual watch splits unavailable</small>':''}<small>${E(x.basis)}</small></td><td>${clock(x.goal_seconds)}</td><td>${clock(x.expected_seconds)}</td><td>${clock(x.actual_seconds)}</td><td>${x.needs_review?'Needs review':x.grade?`<b>${E(x.grade.status)}</b><small>${E(difference(x.grade))}</small>`:'No timing target'}</td></tr>`).join('')}</tbody></table></div>${(t.issues||[]).map(x=>`<p class="note">${E(x)}</p>`).join('')}<p class="sub">Times compare against your written targets. They do not by themselves prove better conditioning. Watch lap timers may include rests; active-length timers do not.</p>${t.reported_splits?.length?`<details><summary>Optional individual drill times · athlete reported</summary><form data-swim-splits="${E(t.activity_id)}"><p>Did you record or remember each drill’s time? Add it here if you want separate comparisons. Leave unknown times blank; combined watch times stay unchanged.</p>${t.reported_splits.map(x=>`<label class="swim-split-field"><span>${E(x.label)}</span><span>Minutes <input type="number" min="0.01" max="600" step="any" data-split-index="${x.set_index}" value="${x.actual_seconds==null?'':Number((x.actual_seconds/60).toFixed(4))}"></span>${x.grade?`<small>${E(x.grade.status)} · ${E(difference(x.grade))}</small>`:'<small>— No individual time reported</small>'}</label>`).join('')}<button type="submit">Save drill times</button><p class="sub" role="status" data-split-status></p></form></details>`:''}</section>`;
}
const strokeNames={free:'Freestyle',back:'Backstroke',breast:'Breaststroke',fly:'Butterfly',drill:'Drill · unresolved',mixed:'Mixed',medley:'Medley · split unknown',choice:'Choice · split unknown',unknown:'Unclassified'};
const strokeColors={free:'#38bdf8',back:'#a78bfa',breast:'#34d399',fly:'#fbbf24',drill:'#fb923c',mixed:'#e879f9',medley:'#e879f9',choice:'#94a3b8',unknown:'#64748b'};
const strokeOrder=['free','breast','back','fly','drill','mixed','medley','choice','unknown'],workOrder=['swim','drill','kick','pull'];
function orderedParts(parts){return (parts||[]).slice().sort((a,b)=>(strokeOrder.indexOf(a.stroke)<0?99:strokeOrder.indexOf(a.stroke))-(strokeOrder.indexOf(b.stroke)<0?99:strokeOrder.indexOf(b.stroke))||(workOrder.indexOf(a.work||'swim')<0?99:workOrder.indexOf(a.work||'swim'))-(workOrder.indexOf(b.work||'swim')<0?99:workOrder.indexOf(b.work||'swim')));}
function partLabel(x){return (strokeNames[x.stroke]||'Unclassified')+(x.work&&x.work!=='swim'?' · '+x.work:'');}
function sourceMix(r,source){return source==='plan'?r.written_mix||r.described_mix||r.planned_mix:source==='written'?r.described_mix:r.watch_mix;}
function writtenBasis(r){return r.written_basis||(r.described_mix?'Recorded workout breakdown':r.planned_mix?'Saved planned workout':'No written workout breakdown');}

function strokeMix(p,basis='Written workout · distance proportions'){
 const totals={};for(const s of p?.sets||[]){const key=strokeNames[s.stroke]?s.stroke:'unknown';totals[key]=(totals[key]||0)+(Number(s.distance_m)||0);}
 const workTotals={};for(const s of p?.sets||[]){const stroke=strokeNames[s.stroke]?s.stroke:'unknown',work=workOrder.includes(s.work)?s.work:'swim',id=stroke+'|'+work;workTotals[id]=workTotals[id]||{stroke,work,distance_m:0};workTotals[id].distance_m+=Number(s.distance_m)||0;}
 const total=Object.values(totals).reduce((a,b)=>a+b,0);return {total_m:total,basis,work_parts:orderedParts(Object.values(workTotals)),parts:Object.entries(totals).filter(([,v])=>v>0).map(([stroke,distance_m])=>({stroke,label:strokeNames[stroke],distance_m,percent:distance_m/total*100}))};
}
function participation(p){
 const sums=[0,0,0,0,0];let total=0;
 for(const s of p?.sets||[]){const n=Number(s.distance_m)||0;total+=n;const weights=s.work==='kick'?[0,.15,.5,.7,.45]:s.work==='pull'?[1,.85,.5,.1,.05]:[1,.85,.5,.28,.2];weights.forEach((v,i)=>sums[i]+=n*v);}
 return sums.map(v=>total?v/total:0);
}
const intensityColors=['#364353','#355d75','#64ceec','#a78bfa','#f19abd'];
function intensityLegend(){
 return `<div class="swim-map-key"><h4>Estimated Intensity Heat Map</h4>${['No estimate','Low','Moderate','High','Very high'].map((label,i)=>`<span><i style="background:${intensityColors[i]}"></i>${label}</span>`).join('')}</div>`;
}
let bodyModule;
function hydrateBodyMaps(){
 bodyModule=bodyModule||import('/web/vendor/body-highlighter.esm.js');
 bodyModule.then(({createBodyHighlighter})=>{
  for(const host of document.querySelectorAll('[data-swim-body]:not([data-ready])')){
   const values=JSON.parse(host.getAttribute('data-swim-body')),groups=[['front-deltoids','back-deltoids','biceps','triceps','forearm'],['chest','upper-back','trapezius'],['abs','obliques','lower-back'],['quadriceps','hamstring','adductor','abductors','gluteal'],['calves','left-soleus','right-soleus']];
   const data=groups.flatMap((muscles,i)=>values[i]>0?[{name:'Estimated swim intensity',muscles,frequency:values[i]>=.85?4:values[i]>=.65?3:values[i]>=.35?2:1}]:[]);
   const large=host.getAttribute('data-swim-body-layout')==='large';
   for(const [type,x] of [['anterior',large?48:60],['posterior',120]]){
    const model=createBodyHighlighter({type,data,bodyColor:intensityColors[0],highlightedColors:intensityColors.slice(1)}),svg=model.element.querySelector('svg');
    svg.setAttribute('x',x);svg.setAttribute('y',large?'44':'54');svg.setAttribute('width',large?'72':'60');svg.setAttribute('height',large?'142':'132');svg.setAttribute('aria-label',type==='anterior'?'Front muscle map':'Back muscle map');
    host.append(svg);
   }
   host.setAttribute('data-ready','true');
  }
 }).catch(()=>{});
}
function miniBody(p,large=false){
 if(typeof document!=='undefined')setTimeout(hydrateBodyMaps,0);
 return `<g class="swim-body" data-swim-body-layout="${large?'large':'compact'}" data-swim-body="${E(JSON.stringify(participation(p)))}"></g>`;
}
function strokeLegend(m){
 const parts=orderedParts(m?.parts);
 return `<ul>${parts.map(x=>`<li><i style="background:${strokeColors[x.stroke]||strokeColors.unknown}"></i>${E(x.label)} <b>${Number(x.percent.toFixed(1))}%</b></li>`).join('')||'<li>— No distances supplied</li>'}</ul>`;
}
function donut(m,p,profile=false){
 const parts=orderedParts(m?.parts);let cursor=-Math.PI/2;const width=profile?28:20,outer=99+width/2,inner=99-width/2;
 const point=(r,t)=>[120+r*Math.cos(t),120+r*Math.sin(t)].map(v=>Number(v.toFixed(4))).join(' ');
 const arcs=parts.map(x=>{const angle=Math.max(0,Math.min(1,x.percent/100))*Math.PI*2,start=cursor;cursor+=angle;
  const path=angle>=Math.PI*2-.000001?`M ${point(outer,start)} A ${outer} ${outer} 0 1 1 ${point(outer,start+Math.PI)} A ${outer} ${outer} 0 1 1 ${point(outer,start)} L ${point(inner,start)} A ${inner} ${inner} 0 1 0 ${point(inner,start+Math.PI)} A ${inner} ${inner} 0 1 0 ${point(inner,start)} Z`:`M ${point(outer,start)} A ${outer} ${outer} 0 ${angle>Math.PI?1:0} 1 ${point(outer,cursor)} L ${point(inner,cursor)} A ${inner} ${inner} 0 ${angle>Math.PI?1:0} 0 ${point(inner,start)} Z`;
  return `<path d="${path}" fill="${strokeColors[x.stroke]||strokeColors.unknown}"><title>${E(x.label)} · ${x.percent.toFixed(1)}% · ${Math.round(x.distance_m)} m</title></path>`;}).join('');
 return `<figure class="swim-composition"><svg viewBox="0 0 240 240" role="img" aria-label="${E((m?.basis||'Stroke proportions')+': '+parts.map(x=>`${x.label} ${x.percent.toFixed(1)}%`).join(', '))}"><circle cx="120" cy="120" r="99" fill="none" stroke="#253544" stroke-width="${width}"/>${arcs}${miniBody(p,profile)}</svg>${profile?'<figcaption>Distance proportions · front and back muscle maps</figcaption>':`<figcaption>${E(m?.basis||'No stroke data')}${strokeLegend(m)}</figcaption>`}</figure>`;
}
function planView(p,basis='Planned workout · not a performed record',m=null){
 p=p||{};m=m||strokeMix(p);const sets=p.sets||[];
 return `<section class="swim-plan-profile"><header><h3>Swim breakdown · ${Number(p.total_distance||0).toLocaleString()} ${E(p.unit||'m')}</h3><p class="sub">${E(basis)}</p></header><div class="swim-plan-grid"><div class="swim-writeup" aria-label="Workout sections"><h4 class="swim-panel-title">Workout</h4>${['warmup','main','cooldown'].map(key=>`<section class="swim-writeup-${key}"><h4>${({warmup:'Warm-up',main:'Main work',cooldown:'Cool-down'})[key]}</h4>${sets.filter(s=>s.section===key).map(s=>`<p><b>${s.repetitions>1?s.repetitions+' × ':''}${s.distance} ${E(s.unit)}</b> · ${E(s.description)}${s.goal_seconds!=null?`<small>Goal ${clock(s.goal_seconds)} · expected ${clock(s.expected_seconds)}</small>`:s.sendoff_seconds!=null?`<small>Send off every ${clock(s.sendoff_seconds)}</small>`:s.rest_seconds!=null?`<small>Rest ${s.rest_seconds} s</small>`:'<small>Time —</small>'}</p>`).join('')||'<p class="sub">— Not specified</p>'}</section>`).join('')}</div><div class="swim-plan-visuals"><section class="swim-plan-diagram" aria-label="Stroke distribution and body map"><h4 class="swim-panel-title">Stroke distribution & body map</h4>${donut(m,p,true)}</section><section class="swim-plan-keys" aria-label="Stroke and intensity keys">${intensityLegend()}<div class="swim-stroke-legend"><h4>Stroke distance</h4>${strokeLegend(m)}</div></section></div></div></section>`;
}
function historyBuckets(rows,days=20,mode='session',source='watch'){
 const end=rows.at(-1)?.date;if(!end)return [];
 const start=new Date(end+'T12:00:00Z');start.setUTCDate(start.getUTCDate()-days+1);const cutoff=start.toISOString().slice(0,10);
 const filtered=rows.filter(r=>r.date>=cutoff&&r.date<=end),buckets=[];
 function row(r){const m=sourceMix(r,source),missing=source!=='watch'&&!m?.parts?.length;
  return {date:r.date,current:r.current,count:1,missing:missing?1:0,basis:source==='plan'?writtenBasis(r):'Watch detection',parts:orderedParts(m?.work_parts?.length?m.work_parts:m?.parts?.length?m.parts:source==='watch'?[{stroke:'unknown',distance_m:r.response?.distance_m||0}]:[]),distance_m:m?.total_m||(source==='watch'?r.response?.distance_m||0:0)};}
 if(mode==='session')return filtered.map(row);
 for(let i=0;i<days;i++){const day=new Date(start);day.setUTCDate(day.getUTCDate()+i);const key=day.toISOString().slice(0,10),entries=filtered.filter(r=>r.date===key).map(row),parts={};for(const r of entries)for(const x of r.parts){const id=x.stroke+'|'+(x.work||'');parts[id]=parts[id]||{stroke:x.stroke,work:x.work,distance_m:0};parts[id].distance_m+=x.distance_m;}buckets.push({date:key,current:entries.some(r=>r.current),count:entries.length,basis:source==='plan'?'Written workout breakdowns':'Watch detection',missing:entries.reduce((n,r)=>n+r.missing,0),distance_m:entries.reduce((n,r)=>n+r.distance_m,0),parts:orderedParts(Object.values(parts))});}
 return buckets;
}
function displayParts(parts,details){
 if(details)return orderedParts(parts);
 const totals={};for(const x of parts||[]){totals[x.stroke]=(totals[x.stroke]||0)+x.distance_m;}
 return orderedParts(Object.entries(totals).map(([stroke,distance_m])=>({stroke,distance_m})));
}
// Zero guides are overlays: they never contribute distance or change segment heights.
function historyZeroGuides(parts,total){
 let below=0;const positions={};for(const stroke of strokeOrder){positions[stroke]=total?below/total*100:0;below+=(parts||[]).filter(x=>x.stroke===stroke).reduce((n,x)=>n+x.distance_m,0);}
 const guides=strokeOrder.slice(0,4).filter(stroke=>!(parts||[]).some(x=>x.stroke===stroke&&x.distance_m>0)).map(stroke=>({stroke,position:positions[stroke],distance_m:0}));
 const collisions={};return guides.map(g=>{const key=g.position.toFixed(6),offset=collisions[key]||0;collisions[key]=offset+1;return {...g,offset:g.position>=99?-offset*3:offset*3};});
}
function proportionHistory(rows,days=90,mode='session',source='watch',scale='distance',details=true){
 if(!rows?.length)return '<p class="sub">Stroke history appears as recordings are imported.</p>';
 if(source==='written')source='plan';
 const sources=source==='compare'?['plan','watch']:[source],groups=sources.map(k=>({source:k,buckets:historyBuckets(rows,days,mode,k).map(r=>({...r,parts:displayParts(r.parts,details)}))})),max=Math.max(1,...groups.flatMap(g=>g.buckets.map(r=>r.distance_m))),selected=groups[0].buckets.reduce((n,r)=>n+r.count,0);
 const parts=orderedParts([...new Map([...strokeOrder.slice(0,4).map(stroke=>({stroke})),...groups.flatMap(g=>g.buckets.flatMap(r=>r.parts))].map(x=>[x.stroke+'|'+(x.work||'swim'),x])).values()]);
 const names={watch:'Watch detection',plan:'Planned',compare:'Planned vs watch'},workClass=x=>x.stroke==='drill'?' swim-work-drill':x.work&&x.work!=='swim'?' swim-work-'+x.work:'';
 const buckets=groups[0].buckets,indices=Array.from({length:buckets.length},(_,i)=>i),tickEvery=Math.max(1,Math.ceil(buckets.length/10)),axisMax=scale==='ratio'?100:max,axisValue=n=>scale==='ratio'?Math.round(n)+'%':Math.round(n).toLocaleString();
 const column=(r,k,i)=>{
  const height=r.distance_m?(scale==='ratio'?100:r.distance_m/max*100):0,missing=!r.count?'No swim recorded':k==='plan'?'No written workout':'No distance available',label=r.date+': '+names[k]+'; '+(r.basis||'')+'; '+Math.round(r.distance_m)+' metres; '+r.parts.map(x=>partLabel(x)+' '+(r.distance_m?Number((x.distance_m/r.distance_m*100).toFixed(1)):0)+'%').join(', '),dateTick=i%tickEvery===0||i===indices.length-1;
  return `<div class="swim-history-column${r.current?' swim-history-current':''}" title="${E(label+(r.distance_m?'':'; '+missing))}"><small class="swim-column-total">${r.distance_m?Math.round(r.distance_m).toLocaleString()+' m':'—'}</small><div class="swim-column-track"><div class="swim-share-bar" style="height:${height}%" role="img" aria-label="${E(label)}">${r.parts.filter(x=>x.distance_m>0).map(x=>`<i class="${workClass(x).trim()}" style="height:${r.distance_m?x.distance_m/r.distance_m*100:0}%;background-color:${strokeColors[x.stroke]||strokeColors.unknown}" title="${E(partLabel(x))} · ${Math.round(x.distance_m)} m · ${r.distance_m?Number((x.distance_m/r.distance_m*100).toFixed(1)):0}%"></i>`).join('')}${r.distance_m?historyZeroGuides(r.parts,r.distance_m).map(g=>`<i class="swim-zero-guide" style="bottom:clamp(0px,calc(${g.position}% + ${g.offset}px),calc(100% - 2px));background-color:${strokeColors[g.stroke]}" title="${strokeNames[g.stroke]} · 0 m · 0% · zero marker"></i>`).join(''):''}</div>${!r.distance_m?`<span class="swim-column-missing" aria-label="${E(missing)}" title="${E(missing)}">—</span>`:''}</div><span class="swim-column-date${dateTick?'':' swim-column-date-hidden'}" aria-hidden="${!dateTick}">${E(r.date.slice(5).replace('-','/'))}</span>${r.missing&&r.distance_m?`<small class="swim-column-coverage" title="${r.count-r.missing}/${r.count} swims with written breakdowns">${r.count-r.missing}/${r.count}</small>`:''}</div>`;
 };
 const buttons=(items,key,active)=>items.map(([k,label])=>`<button type="button" data-history-${key}="${k}" aria-pressed="${active===k}">${label}</button>`).join('');
 return `<section class="swim-history" data-swim-history="${E(JSON.stringify(rows))}" data-days="${days}" data-mode="${mode}" data-source="${source}" data-scale="${scale}" data-work-details="${details}"><h3>Stroke ${scale==='ratio'?'proportions':'distance'} across swims</h3><div class="swim-history-layout"><aside class="swim-history-filters" aria-label="Swim history filters"><h4>Display</h4><div class="swim-history-controls" role="group" aria-label="Swim history scale">${buttons([['distance','Distance'],['ratio','Percentages']],'scale',scale)}</div><div class="swim-history-controls" role="group" aria-label="Swim history grouping">${buttons([['session','Session'],['day','Day']],'mode',mode)}</div><label class="swim-history-source">Source<select data-history-source aria-label="Swim history source">${[['plan','Planned'],['watch','Watch detection'],['compare','Compare']].map(([k,label])=>`<option value="${k}" ${source===k?'selected':''}>${label}</option>`).join('')}</select></label>${source!=='watch'?`<label class="swim-history-detail"><input type="checkbox" data-history-work-details ${details?'checked':''}><span>Drill, kick & pull detail</span></label>`:''}<p class="swim-history-hint">${scale==='ratio'?'Each column = 100%.':'Column height = metres.'}${source==='watch'?' Watch drills may not name a stroke.':' Written workouts supply the planned breakdown.'}</p></aside><div class="swim-history-main"><div class="swim-history-controls swim-history-period" role="group" aria-label="Swim history period">${buttons([5,10,20,30,40,60,90].map(n=>[n,n+' days']),'days',days)}</div><p class="sub swim-history-range">${days} days ending ${E(rows.at(-1).date)} · ${selected} recorded swim${selected===1?'':'s'}<small>Available from ${E(rows[0].date)}</small></p><div class="swim-history-bars swim-history-vertical ${source==='compare'?'swim-history-compare':''}"><div class="swim-history-plots" style="--history-count:${indices.length};--history-min-width:${Math.max(1,indices.length)*(mode==='day'?18:64)+46}px">${groups.map(g=>`<section class="swim-history-source-panel" aria-label="${names[g.source]} swim history"><h4>${names[g.source]}</h4><div class="swim-column-chart"><div class="swim-column-axis" aria-hidden="true"><small>${axisValue(axisMax)}</small><small>${axisValue(axisMax/2)}</small><small>0${scale==='ratio'?'':' m'}</small></div><div class="swim-history-columns">${indices.map(i=>column(g.buckets[i],g.source,i)).join('')||'<p class="sub">No swims recorded in this window.</p>'}</div></div></section>`).join('')}</div></div><div class="swim-stroke-key">${parts.map(x=>`<span><i class="${workClass(x).trim()}" style="background-color:${strokeColors[x.stroke]||strokeColors.unknown}"></i>${E(partLabel(x))}</span>`).join('')}</div><p class="swim-history-guide-note">Thin color marks = 0; totals and percentages are unchanged. — = no data.</p></div></div></section>`;
}
if(typeof document!=='undefined'){
 const updateHistory=event=>{
  const control=event.target.closest(event.type==='change'?'[data-history-source],[data-history-work-details]':'button[data-history-days],button[data-history-mode],button[data-history-scale]');if(!control)return;
  const panel=control.closest('[data-swim-history]');if(!panel)return;
  const rows=JSON.parse(panel.dataset.swimHistory),days=Number(control.dataset.historyDays||panel.dataset.days),mode=control.dataset.historyMode||panel.dataset.mode,source=control.matches('[data-history-source]')?control.value:panel.dataset.source,scale=control.dataset.historyScale||panel.dataset.scale||'distance',details=control.matches('[data-history-work-details]')?control.checked:panel.dataset.workDetails==='true';
  const key=['days','mode','scale'].find(k=>control.hasAttribute('data-history-'+k)),focus=key?`[data-history-${key}="${control.getAttribute('data-history-'+key)}"]`:control.matches('[data-history-source]')?'[data-history-source]':'[data-history-work-details]';
  const holder=document.createElement('div');holder.innerHTML=proportionHistory(rows,days,mode,source,scale,details);const replacement=holder.firstElementChild;panel.replaceWith(replacement);replacement.querySelector(focus)?.focus({preventScroll:true});
 };
 document.addEventListener('click',updateHistory);document.addEventListener('change',updateHistory);
}
function responseTrend(rows,current){
 if(!rows?.length)rows=[{date:'Selected workout',response:current}];
 const metrics=[['distance_m','Distance','m'],['duration_minutes','Duration','min'],['avg_hr','Average HR','bpm'],['hr_time_bpm_min','HR × time','bpm·min']];
 const first=rows.at(-1)?.response||current||{},prior=rows.at(-2)?.response;
 return `<section class="swim-response"><h3>Time, volume and heart-rate response</h3><div class="swim-response-grid">${metrics.map(([key,label,unit])=>{const valid=rows.map(r=>r.response?.[key]).filter(v=>Number.isFinite(v)&&v>=0),max=Math.max(...valid,1),n=rows.length,w=240;const delta=prior&&Number.isFinite(prior[key])&&Number.isFinite(first[key])?first[key]-prior[key]:null;return `<figure><figcaption>${label}<strong>${first[key]==null?'—':Number(first[key].toFixed(1)).toLocaleString()} <small>${unit}</small></strong>${delta==null?'':`<small>${delta>0?'+':''}${Number(delta.toFixed(1))} ${unit} vs previous swim</small>`}</figcaption><svg viewBox="0 0 240 70" role="img" aria-label="${E(label+': '+rows.map(r=>r.date+' '+(r.response?.[key]??'unknown')+' '+unit).join('; '))}">${rows.map((r,i)=>{const v=r.response?.[key],x=i*w/n+3,bw=Math.max(2,w/n-6);return Number.isFinite(v)?`<rect x="${x}" y="${65-v/max*58}" width="${bw}" height="${Math.max(1,v/max*58)}" rx="2" fill="${r.current?'#c4a2ff':'#469dbc'}"><title>${E(r.date)} · ${v} ${unit}</title></rect>`:`<text x="${x}" y="60" fill="#8196a7">—</text>`;}).join('')}</svg></figure>`;}).join('')}</div><p class="sub">${E(current?.hr_basis||'Heart rate unavailable')}. HR × time is a descriptive quantity, not perceived effort, a heart-rate zone, or a validated training score. Average HR is shown separately from duration. ${current?.hr_coverage_percent!=null?'HR sample coverage '+current.hr_coverage_percent+'%. ':''}Timer pace ${current?.pace_per_100m_seconds!=null?clock(current.pace_per_100m_seconds)+' / 100 m':'—'}; may include rests.</p><p class="sub">Reported effort ${rows.at(-1)?.response?.reported_effort==null?'—':E(rows.at(-1).response.reported_effort)+'/10'}. Stroke mix, volume, pace, rests and conditions can change these readings. Differences alone do not establish adaptation or deconditioning.</p></section>`;
}
function analysisView(a){
 if(!a)return '';const written=a.described_mix||a.planned_mix,chosen=written||a.watch_mix;
 const history=(a.history||[]).map(r=>r.current&&!r.planned_mix&&a.planned_mix?{...r,planned_mix:{...a.planned_mix,...(!a.described_mix&&a.recipe&&/^Saved plan captured/.test(a.recipe_basis||'')?{work_parts:strokeMix(a.recipe).work_parts}:{})}}:r);
 return `${a.recipe?planView(a.recipe,a.recipe_basis,chosen):`<section class="swim-plan-profile"><h3>Recorded stroke proportions</h3>${donut(a.watch_mix,null)}</section>`}${written?`<details class="swim-watch-share"><summary>Watch-classified stroke split</summary>${donut(a.watch_mix,null)}${a.watch_mix?.distance_mismatch?'<p class="note">Length/lap distance exceeds the watch session total; review the source distances.</p>':''}</details>`:''}${proportionHistory(history)}${responseTrend(history.slice(-12),a.response)}`;
}

root.SwimWorkout={render,chooseArt,artwork,timingReport,clock,strokeMix,planView,analysisView,historyBuckets,displayParts,orderedParts,historyZeroGuides,historyView:proportionHistory,intensityLegend,compositionView:(m,p,legend=true)=>donut(m,p)+(legend?intensityLegend():'')};if(typeof module!=='undefined')module.exports=root.SwimWorkout;
})(typeof window!=='undefined'?window:globalThis);
