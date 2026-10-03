/* Draft-only program editing. Active Plan is updated only after explicit acceptance. */
let workspacePhases=[],workspaceRevision=0,workspaceReview=null,workspaceBaseGoal={},workspaceSource='revise',workspaceEventExtra=0;
const workspaceDays=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const workspaceColors=['teal','blue','purple','orange','gold'];
const workspacePurpose={assessment:['Assessment','base','blue'],recovery:['Recovery','recovery','teal'],base:['Foundation','base','blue'],build:['Development','build','purple'],specific:['Event preparation','build','orange'],taper:['Final preparation','taper','gold']};
const draftCopy=x=>JSON.parse(JSON.stringify(x));
const draftDate=(iso,n)=>{const d=new Date(iso+'T12:00');d.setDate(d.getDate()+n);return d.toLocaleDateString('en-CA');};
const draftSpan=(a,b)=>Math.round((new Date(b+'T12:00')-new Date(a+'T12:00'))/86400000);
const draftStage=p=>p.stage||p.kind||'build';
function workspaceDirty(message='Draft changed — review before applying.'){
 workspaceRevision++;workspaceReview=null;programDraft=null;$('programaccept').disabled=true;$('programdraft').innerHTML='';$('programmessage').textContent=message;
}
function workspaceFields(){
 const event=$('programpath').value==='event';
 const fields={...workspaceBaseGoal,goal:$('programgoal').value,target:event?$('programtarget').value:null,start:$('programstart').value,
 horizon_days:Number($('programhorizon').value),sport:$('programsport').value,outcome:$('programoutcome').value,hours:Number($('programhours').value),focus:$('programfocus').value,
 entry:$('programentry').value,assessment:$('programassessment').value,starter_enabled:$('programstarter').checked,starter_level:$('programstarterlevel').value,starter_equipment:$('programstarterequipment').value,strength_anchors:workspaceAnchors(),neutral_forecast:$('programneutral').checked,
 priorities:Object.fromEntries(Object.keys(phaseSports).map(s=>[s,$('programmode-'+s).value])),
 schedule_options:{first_sport:$('programfirst').value,available_days:Array.from($('programavailable').querySelectorAll('input:checked')).map(x=>Number(x.value)),rest_days:Array.from($('programrest').querySelectorAll('input:checked')).map(x=>Number(x.value)),allow_doubles:$('programdoubles').checked}};
 delete fields.phases;delete fields.weeks;delete fields.changes;return fields;
}
function workspacePriorities(priorities){
 $('programpriorities').innerHTML=Object.entries(phaseSports).map(([s,name])=>`<label>${ICON[s]||''} ${esc(name)}<select id="programmode-${s}">${[['improve','Build'],['maintain','Maintain'],['pause','Pause']].map(([v,t])=>`<option value="${v}" ${priorities?.[s]===v?'selected':''}>${t}</option>`).join('')}</select></label>`).join('');
 $('programpriorities').querySelectorAll('select').forEach(el=>el.onchange=()=>{const s=el.id.replace('programmode-','');workspacePhases.forEach(p=>{p.modes[s]=el.value;});workspaceDirty();workspaceRender();});
}
function workspaceSetFields(goal){
 workspaceBaseGoal=draftCopy(goal||{});workspaceRenderAnchors(goal?.strength_anchors||[]);$('programneutral').checked=goal?.neutral_forecast!==false;$('programstarter').checked=false;$('programstarterlevel').value='easy';
 const today=day?.date||new Date().toLocaleDateString('en-CA');
 $('programstart').value=goal?.start&&goal.start>today?goal.start:today;$('programstart').min=today;
 $('programgoal').value=goal?.goal||'';$('programtarget').value=goal?.target||'';$('programpath').value=goal?.target?'event':'ongoing';
 $('programsport').value=goal?.sport||'general';$('programoutcome').value=goal?.outcome||'Build sustainable fitness';$('programhours').value=goal?.hours||4;$('programfocus').value=goal?.focus||'balanced';
 $('programentry').value=goal?.entry||'auto';$('programassessment').value=goal?.assessment||'week';
 const end=goal?.end||goal?.target||programState?.phases?.at(-1)?.end;
 workspaceEventExtra=goal?.target&&end===draftDate(goal.target,1)?1:0;
 $('programhorizon').value=end&&end>$('programstart').value?draftSpan($('programstart').value,end):84;
 $('programduration').value='fixed';
 const priorities=goal?.priorities||programState?.phases?.find(p=>p.kind==='build')?.modes||Object.fromEntries(Object.keys(phaseSports).map(s=>[s,'maintain']));
 workspacePriorities(priorities);
 const options=goal?.schedule_options||{};$('programfirst').value=options.first_sport||'auto';$('programdoubles').checked=!!options.allow_doubles;
 for(const [id,selected] of [['programavailable',options.available_days||[0,1,2,3,4,5,6]],['programrest',options.rest_days||[6]]]){
  $(id).innerHTML=workspaceDays.map((name,i)=>`<label><input type="checkbox" value="${i}" ${selected.includes(i)?'checked':''}>${name}</label>`).join('');
  $(id).querySelectorAll('input').forEach(e=>e.onchange=()=>workspaceDirty());
 }
 workspacePath();
}
function workspacePath(){const event=$('programpath').value==='event';$('programtargetlabel').hidden=!event;$('programhorizon').disabled=event;if(event)$('programduration').value='fixed';$('programduration').disabled=event;}
function workspaceReschedule(){
 let cursor=$('programstart').value;if(!cursor)return;
 workspacePhases.forEach(p=>{if(p.date_placements&&p.start&&p.start!==cursor){const delta=draftSpan(p.start,cursor);p.date_placements=Object.fromEntries(Object.entries(p.date_placements).map(([date,slots])=>[draftDate(date,delta),slots]));}p.id=p.start=cursor;p.days=Number(p.days);p.weeks=Math.round(p.days/7*100)/100;p.end=draftDate(cursor,p.days);cursor=p.end;});
 if(workspacePhases.length){$('programhorizon').value=workspacePhases.reduce((n,p)=>n+p.days,0);}
}
function workspaceWeeklyHtml(p){
 const pattern=p.weekly_pattern;
 return `<label class="program-check"><input type="checkbox" data-custom-week ${pattern?'checked':''}>Arrange this phase’s weekly sessions manually</label><div class="program-manual-week" ${pattern?'':'hidden'}>${workspaceDays.map((name,i)=>{
 const raw=pattern?.[i],slots=Array.isArray(raw)?raw:raw?[raw]:[{sport:'rest',purpose:'Rest / open day'}];
 return `<div><b>${name}</b>${[0,1,2].map(j=>`<select aria-label="${name} session ${j+1}" data-week-day="${i}" data-week-session="${j}"><option value="">${j?'No additional session':'Rest'}</option>${Object.entries(phaseSports).map(([s,n])=>`<option value="${s}" ${slots[j]?.sport===s?'selected':''}>${esc(n)}</option>`).join('')}</select>`).join('')}<input aria-label="${name} session purpose" data-week-note="${i}" value="${esc(slots[0]?.purpose||'')}" placeholder="Purpose / focus"></div>`;
 }).join('')}</div>`;
}
function workspaceRender(){
 const expanded=new Set(Array.from($('programphasecards').querySelectorAll('details[open]')).map(e=>e.dataset.phaseSettings));
 workspaceReschedule();
 $('programphasecards').innerHTML=workspacePhases.length?workspacePhases.map((p,i)=>`<article class="program-draft-phase phase-${esc(p.color||workspaceColors[i%5])}" data-draft-index="${i}">
 <div class="program-draft-art phasephoto"><img src="${esc(artFile(phasePhoto(p,'draft')))}" style="${artPosition(phasePhoto(p,'draft'))}" alt="${esc(p.label)} inspiration"><div class="program-duration-controls"><button type="button" data-duration-delta="-1" aria-label="Decrease phase ${i+1} by one day" ${p.locked?'disabled':''}>−</button><label><input type="number" data-phase-days min="1" max="366" aria-label="Phase ${i+1} days" value="${p.days}" ${p.locked?'disabled':''}> days</label><button type="button" data-duration-delta="1" aria-label="Increase phase ${i+1} by one day" ${p.locked?'disabled':''}>＋</button></div></div>
 <div class="program-draft-phase-body"><input data-phase-label aria-label="Phase ${i+1} name" value="${esc(p.label)}"><small>${esc(p.start)} → ${esc(p.end)}</small>
 <div class="program-phase-order"><button type="button" data-move="-1" aria-label="Move phase ${i+1} earlier" ${i===0?'disabled':''}>←</button><button type="button" data-move="1" aria-label="Move phase ${i+1} later" ${i===workspacePhases.length-1?'disabled':''}>→</button><button type="button" data-duplicate>Duplicate</button><button type="button" data-remove>Remove</button></div>
 <details data-phase-settings="${i}" ${expanded.has(String(i))?'open':''}><summary>Purpose, priorities & weekly placement</summary>
 <label>Training purpose<select data-phase-stage>${Object.entries(workspacePurpose).map(([s,[name]])=>`<option value="${s}" ${draftStage(p)===s?'selected':''}>${name}</option>`).join('')}</select></label>
 <label>Color<select data-phase-color>${workspaceColors.map(c=>`<option ${p.color===c?'selected':''}>${c}</option>`).join('')}</select></label>
 <label class="program-check"><input data-phase-lock type="checkbox" ${p.locked?'checked':''}>Lock duration during redistribution</label>
 <label>Purpose / coaching intent<textarea data-phase-purpose rows="2">${esc(p.purpose||'')}</textarea></label>
 <div class="program-phase-priorities">${Object.entries(phaseSports).map(([s,name])=>`<label>${esc(name)}<select data-phase-mode="${s}">${[['improve','Build'],['maintain','Maintain'],['pause','Pause']].map(([v,t])=>`<option value="${v}" ${p.modes[s]===v?'selected':''}>${t}</option>`).join('')}</select><input type="number" min="1" max="100" step="1" data-phase-weight="${s}" aria-label="${esc(name)} priority weight" value="${p.weights?.[s]|| (p.modes[s]==='improve'?2:1)}"></label>`).join('')}</div>
 ${workspaceWeeklyHtml(p)}<details class="program-dated-settings"><summary>Individual date exceptions</summary><p class="sub">Override the recurring placement for a specific date. Existing detailed workouts still take precedence.</p><label>Date<input type="date" data-placement-date min="${p.start}" max="${draftDate(p.end,-1)}" value="${p.start}"></label><div class="program-dated-sports">${[0,1,2].map(j=>`<select data-placement-sport aria-label="Dated session ${j+1}"><option value="">${j?'No additional session':'Rest'}</option>${Object.entries(phaseSports).map(([s,n])=>`<option value="${s}">${esc(n)}</option>`).join('')}</select>`).join('')}</div><input data-placement-purpose aria-label="Dated session purpose" placeholder="Purpose / focus"><button type="button" data-placement-save>Save date in draft</button><ul>${Object.entries(p.date_placements||{}).sort().map(([date,slots])=>`<li>${esc(date)} · ${slots.map(s=>esc(phaseSports[s.sport]||'Rest')).join(' + ')} <button type="button" data-placement-remove="${date}" aria-label="Remove placement on ${date}">Remove</button></li>`).join('')}</ul></details></details></div></article>`).join(''):'<p class="sub">No draft phases. Create evenly spaced phases, add a phase, or request a suggestion.</p>';
 $('programphasecards').querySelectorAll('[data-draft-index]').forEach(card=>{
  const i=Number(card.dataset.draftIndex),p=workspacePhases[i];
  const update=(selector,key,read=e=>e.value)=>{const e=card.querySelector(selector);e.onchange=()=>{p[key]=read(e);workspaceDirty();if(key==='color'||key==='locked')workspaceRender();};};
  update('[data-phase-label]','label');update('[data-phase-color]','color');update('[data-phase-lock]','locked',e=>e.checked);update('[data-phase-purpose]','purpose');
  card.querySelector('[data-phase-stage]').onchange=e=>{p.stage=e.target.value;p.kind=workspacePurpose[p.stage][1];p.profile=p.stage==='recovery'?'recovery':$('programfocus').value;workspaceDirty();workspaceRender();};
  card.querySelector('[data-phase-days]').onchange=e=>workspaceChangeDays(i,Number(e.target.value));
  card.querySelectorAll('[data-duration-delta]').forEach(b=>b.onclick=()=>workspaceChangeDays(i,p.days+Number(b.dataset.durationDelta)));
  card.querySelectorAll('[data-move]').forEach(b=>b.onclick=()=>{const j=i+Number(b.dataset.move);[workspacePhases[i],workspacePhases[j]]=[workspacePhases[j],workspacePhases[i]];workspaceDirty();workspaceRender();});
  card.querySelector('[data-duplicate]').onclick=()=>workspaceAdd(draftCopy(p));
  card.querySelector('[data-remove]').onclick=()=>{
   try{if(p.locked)throw Error('Unlock this phase before removing it.');const next=workspacePhases.filter((_,j)=>j!==i).map(x=>({...x}));
    if($('programduration').value==='fixed'&&next.length){const recipient=next.findIndex(x=>!x.locked);if(recipient<0)throw Error('Unlock a remaining phase before redistributing these days.');next[recipient].days+=p.days;if(next[recipient].days>366)throw Error('This would exceed the phase duration limit.');}
    workspacePhases=next;workspaceDirty();workspaceRender();
   }catch(e){$('programmessage').textContent=e.message;}
  };
  card.querySelectorAll('[data-phase-mode]').forEach(e=>e.onchange=()=>{p.modes[e.dataset.phaseMode]=e.value;workspaceDirty();});
  card.querySelectorAll('[data-phase-weight]').forEach(e=>e.onchange=()=>{p.weights={...p.weights,[e.dataset.phaseWeight]:Number(e.value)};workspaceDirty();});
  card.querySelector('[data-placement-save]').onclick=()=>{
   const date=card.querySelector('[data-placement-date]').value;if(date<p.start||date>=p.end){$('programmessage').textContent='Choose a date within this phase.';return;}
   const purpose=card.querySelector('[data-placement-purpose]').value||p.label,slots=Array.from(card.querySelectorAll('[data-placement-sport]')).filter(e=>e.value).map(e=>({sport:e.value,purpose}));
   p.date_placements={...p.date_placements,[date]:slots.length?slots:[{sport:'rest',purpose:'Rest / open day'}]};workspaceDirty();workspaceRender();
  };
  card.querySelectorAll('[data-placement-remove]').forEach(b=>b.onclick=()=>{delete p.date_placements[b.dataset.placementRemove];workspaceDirty();workspaceRender();});
  const saveWeek=()=>{p.weekly_pattern=workspaceDays.map((_,d)=>{
   const sportEls=Array.from(card.querySelectorAll(`[data-week-day="${d}"]`));const note=card.querySelector(`[data-week-note="${d}"]`).value||p.label;
   const slots=sportEls.filter(e=>e.value).map(e=>({sport:e.value,purpose:note}));return slots.length?slots:[{sport:'rest',purpose:'Rest / open day'}];
  });workspaceDirty();};
  card.querySelector('[data-custom-week]').onchange=e=>{card.querySelector('.program-manual-week').hidden=!e.target.checked;if(e.target.checked)saveWeek();else{delete p.weekly_pattern;workspaceDirty();}};
  card.querySelectorAll('[data-week-day],[data-week-note]').forEach(e=>e.onchange=saveWeek);
 });
}
function workspaceChangeDays(i,days){
 try{const next=ProgramDraftMath.redistribute(workspacePhases,i,days,$('programduration').value==='fixed');if(next.reduce((n,p)=>n+p.days,0)>366)throw Error('Keep the planning horizon within 366 days.');workspacePhases=next;workspaceDirty('Duration changed; other unlocked days were adjusted where required. Review the dates.');workspaceRender();}
 catch(e){$('programmessage').textContent=e.message;workspaceRender();}
}
function workspaceNewPhase(days=7){return {days,label:'Development',kind:'build',stage:'build',profile:$('programfocus').value,purpose:'Develop the selected priorities with reviewed progression.',color:workspaceColors[workspacePhases.length%5],modes:workspaceFields().priorities,weights:{},locked:false};}
function workspaceAdd(phase){
 try{if(workspacePhases.length>=24)throw Error('Use at most 24 phases.');phase=phase||workspaceNewPhase();phase.locked=false;
  const days=phase.days;const next=[...workspacePhases,draftCopy(phase)];
  if($('programduration').value==='fixed'&&workspacePhases.length){next.at(-1).days=0;workspacePhases=ProgramDraftMath.redistribute(next,next.length-1,days,true);}else workspacePhases=next;
  if(workspacePhases.reduce((n,p)=>n+p.days,0)>366){workspacePhases.pop();throw Error('Keep the planning horizon within 366 days.');}
  workspaceDirty();workspaceRender();
 }catch(e){$('programmessage').textContent=e.message;}
}
function workspaceEven(){
 const count=Number($('programcount').value),span=$('programpath').value==='event'?draftSpan($('programstart').value,$('programtarget').value)+workspaceEventExtra:Number($('programhorizon').value);
 if(!Number.isInteger(count)||count<1||count>24||!Number.isInteger(span)||span<count||span>366){$('programmessage').textContent='Choose 1–24 phases and enough days for at least one day per phase, up to 366 days.';return;}
 workspacePhases=Array.from({length:count},(_,i)=>({...workspaceNewPhase(Math.floor(span/count)+(i<span%count?1:0)),label:'Development '+(i+1),color:workspaceColors[i%5]}));workspaceDirty();workspaceRender();
}
function workspaceRevise(){
 workspaceSource='revise';workspaceSetFields(programState?.goal);const start=$('programstart').value;
 workspacePhases=(programState?.phases||[]).filter(p=>p.end>start).map(p=>({...draftCopy(p),start:p.start<start?start:p.start,days:draftSpan(p.start<start?start:p.start,p.end),locked:p.locked??['specific','taper'].includes(draftStage(p))}));
 workspaceDirty('Current program copied into a draft. Completed history stays in place.');workspaceRender();
}
async function workspaceSuggest(){
 workspaceDirty('Preparing a suggestion…');const fields=workspaceFields(),revision=workspaceRevision;
 const r=await post('/api/coach/program-builder',{...fields,action:'preview'});
 if(revision!==workspaceRevision||!$('programdialog').open)return;
 if(!r.ok){$('programmessage').textContent=r.j.error||'Could not build a suggestion.';return;}
 workspaceSource='suggest';workspacePhases=r.j.phases.map(p=>({...p,locked:['specific','taper'].includes(draftStage(p))}));workspaceRender();$('programmessage').textContent='Suggestion ready to edit. Review it before applying.';
}
async function openProgram(){
 if(!programState)await loadProgram();workspaceRevise();
 if(!workspacePhases.length){const ev=programState?.events?.find(e=>e.kind==='race'&&e.date>=(day?.date||''));if(ev)workspaceSetFields({goal:ev.name,target:ev.date,sport:ev.sport==='bike'?'ride':ev.sport,hours:4});}
 if(!$('programdialog').open)$('programdialog').showModal();
}
function workspaceReviewHtml(r){
 const changes=r.changes,old=programState?.goal;
 const counts={};for(const w of r.weeks)for(const slot of w.slots)if(slot.sport!=='rest')counts[slot.sport]=(counts[slot.sport]||0)+1;
 return `<section class="program-change-review"><h3>Review before applying</h3><div class="program-comparison"><div><small>ACTIVE PROGRAM</small><b>${esc(old?.goal||'No saved program')}</b><p>${esc(old?.start||'')} → ${esc(old?.end||old?.target||'')}</p><p>${programState?.phases?.length||0} saved phases</p></div><div><small>PROPOSED FROM ${esc(r.start)}</small><b>${esc(r.goal)}</b><p>${esc(r.start)} → ${esc(r.end)}</p><p>${r.phases.length} phases · ${r.hours} hours available / week</p></div></div>
 ${r.running_hold?'<p class="phasehold">Running remains on hold. The draft does not clear it.</p>':''}
 <p>${changes.retained_workout_days.length} days with existing detailed workouts remain saved. Earlier training and journal entries are preserved.</p>
 <details open><summary>Phase changes · ${changes.phase_changes.length}</summary><div class="program-change-table"><table><thead><tr><th>Current</th><th>Proposed</th><th>Dates</th></tr></thead><tbody>${changes.phase_changes.map(c=>`<tr><td>${esc(c.previous?.label||'New phase')}</td><td>${esc(c.proposed.label)}</td><td>${esc(c.proposed.start)} → ${esc(c.proposed.end)}</td></tr>`).join('')}${changes.removed_phases.map(p=>`<tr><td>${esc(p.label)}</td><td>Removed from future phase intent</td><td>${esc(p.start)} → ${esc(p.end)}</td></tr>`).join('')}</tbody></table></div></details>
 <p class="sub">${esc(changes.workout_policy)}</p>
 ${changes.conflicts.length?'<h4>Workout conflicts to review</h4><ul>'+changes.conflicts.map(c=>`<li>${esc(c.date)} · ${esc(phaseSports[c.sport])}: ${esc(c.reason)}</li>`).join('')+'</ul>':''}
 <details><summary>Proposed session placement by sport</summary><p>${Object.entries(counts).map(([s,n])=>`${esc(phaseSports[s]||s)}: ${n} slots`).join(' · ')}</p><p class="sub">Placement counts are not training doses. New load changes cannot be estimated until durations, intensity and workout details are prescribed. Existing projected loads remain available on the active calendar.</p></details>
 ${workspaceStarterHtml(r.starter)}${macroHtml(r.weeks)}</section>`;
}
$('programopen').onclick=openProgram;$('rulesprogramopen').onclick=openProgram;$('rulesphaseopen').onclick=()=>openPhaseEditor();
$('programrevise').onclick=workspaceRevise;$('programsuggest').onclick=workspaceSuggest;
$('programblank').onclick=()=>{workspaceSource='blank';workspacePhases=[];workspaceDirty('Blank draft ready. Create phases or add them individually.');workspaceRender();};
$('programclear').onclick=()=>{workspacePhases=[];workspaceDirty('Draft cleared. Your active program is unchanged.');workspaceRender();};
$('programcreate').onclick=workspaceEven;$('programadd').onclick=()=>workspaceAdd();
$('programclose').onclick=()=>$('programdialog').close();
$('programdialog').addEventListener('close',()=>{workspaceRevision++;workspaceReview=null;programDraft=null;programPreviewData=null;});
$('programdialog').querySelectorAll('.lgrid input,.lgrid select').forEach(e=>e.onchange=()=>{
 workspaceDirty();workspacePath();
 if(['programstart','programtarget','programhorizon'].includes(e.id)&&workspacePhases.length){
  if(e.id==='programstart'){workspaceRender();return;}
  const wanted=$('programpath').value==='event'?draftSpan($('programstart').value,$('programtarget').value)+workspaceEventExtra:Number($('programhorizon').value),total=workspacePhases.reduce((n,p)=>n+p.days,0),i=workspacePhases.findIndex(p=>!p.locked);
  if(i>=0&&wanted>0&&wanted<=366){try{workspacePhases=ProgramDraftMath.redistribute(workspacePhases,i,workspacePhases[i].days+wanted-total,false);}catch(err){$('programmessage').textContent=err.message;}}
  workspaceRender();
 }
});
$('programpath').onchange=()=>{workspacePath();workspaceDirty();};
$('programpreview').onclick=async()=>{
 workspaceDirty('Reviewing the draft…');const revision=workspaceRevision,fields=workspaceFields();
 if(!workspacePhases.length){$('programmessage').textContent='Create draft phases or ask for a suggestion first.';return;}
 if(fields.start<(day?.date||new Date().toLocaleDateString('en-CA'))){$('programmessage').textContent='Apply changes from today or a future date to preserve earlier history.';return;}
 if($('programpath').value==='event'&&!fields.target){$('programmessage').textContent='Choose an event date or use ongoing development.';return;}
 const r=await post('/api/coach/program-builder',{...fields,phases:draftCopy(workspacePhases),action:'preview'});
 if(revision!==workspaceRevision||!$('programdialog').open)return;
 if(!r.ok){$('programmessage').textContent=r.j.error||'Could not review the draft.';return;}
 workspaceReview=r.j;programDraft={...fields,phases:draftCopy(workspacePhases)};$('programdraft').innerHTML=workspaceReviewHtml(r.j);$('programaccept').disabled=false;$('programaccept').textContent='Apply changes from '+r.j.start;$('programmessage').textContent='Review ready. The active program has not changed.';
};
$('programaccept').onclick=async()=>{
 if(!programDraft||!workspaceReview)return;const revision=workspaceRevision;const payload=draftCopy(programDraft);
 $('programaccept').disabled=true;$('programmessage').textContent='Applying reviewed changes…';
 const r=await post('/api/coach/program-builder',{...payload,action:'accept'});
 if(!r.ok){$('programmessage').textContent=r.j.error||'Could not apply the program.';if(revision===workspaceRevision)$('programaccept').disabled=false;return;}
 $('programdialog').close();await loadProgram();await loadPhaseProfiles();await loadToday();
};
if(new URLSearchParams(location.search).get('program')==='setup'&&new URLSearchParams(location.search).get('starter')!=='1')openProgram();

function workspaceStarterHtml(starter){
 if(!starter)return '';
 return `${starter.assumptions?.length?'<details><summary>Forecast defaults and assumptions</summary><ul>'+starter.assumptions.map(n=>'<li>'+esc(n)+'</li>').join('')+'</ul></details>':''}<h3>Starter journey · ${esc(starter.selected)} scenario</h3><p class="sub">${esc(starter.notice)}</p>${Object.keys(starter.strength_anchors||{}).length?'<details><summary>Reported lifting sets and estimated maximums</summary><ul>'+Object.entries(starter.strength_anchors).map(([name,a])=>'<li>'+esc(name)+': '+a.weight+' '+esc(a.unit)+' × '+a.reps+' reps, '+a.rir+' left · estimated max '+(a.e1rm_kg/(a.unit==='lb'?.45359237:1)).toFixed(1)+' '+esc(a.unit)+'</li>').join('')+'</ul></details>':''}<div class="starter-comparison">${starter.candidates.map(c=>`<article class="card"><h4>${esc(c.level)} ${c.level===starter.selected?'· selected':''}</h4><b>${c.total_minutes} total minutes · ${c.added_minutes} new</b><p>${c.limit_flags.length} daily load-limit flags · ${c.unknown_metrics.length} unestimated readings</p><table><thead><tr><th>Reading</th><th>Start</th><th>End</th></tr></thead><tbody>${c.summary.map(m=>`<tr><td>${esc(m.name)}<small> ${esc(m.unit)}</small></td><td>${m.start??'Unknown'}</td><td>${m.end??'Unknown'}</td></tr>`).join('')}</tbody></table>${c.limit_flags.length?`<details><summary>Review load-limit flags</summary><ul>${c.limit_flags.slice(0,20).map(f=>`<li>${esc(f.date)} · ${esc(f.metric)} ${f.after} / ${f.limit}</li>`).join('')}</ul></details>`:''}</article>`).join('')}</div><details open><summary>Selected workouts · through ${esc(starter.detail_end)} (end exclusive)</summary>${starter.candidates.find(c=>c.level===starter.selected).journey.map(w=>`<details class="macro-week"><summary>Week ${w.week} · ${esc(w.start)} · ${w.minutes} min · ${esc(w.purpose)}</summary>${Object.entries(starter.display_plans||starter.plans).filter(([date])=>date>=w.start&&date<draftDate(w.start,7)).map(([date,p])=>`<div><h4>${esc(date)} ${p.retained?'· existing workout retained':''}</h4>${p.sessions.map(s=>`<b>${esc(s.name)} · ${s.minutes} min</b><ul>${(s.steps||[]).map(step=>`<li>${esc(step)}</li>`).join('')}</ul>`).join('')}</div>`).join('')}</details>`).join('')}</details>`;
}
async function workspaceWelcomeStarter(){
 const q=new URLSearchParams(location.search);if(q.get('starter')!=='1')return;
 await openProgram();
 const sports=(q.get('sports')||'').split(',').filter(s=>s in phaseSports);workspaceSetFields({sport:sports.length===1?sports[0]:'general',outcome:'Build sustainable fitness',focus:'balanced',hours:Number(q.get('hours')||3.5)});workspaceEventExtra=0;let setup={};try{setup=JSON.parse(sessionStorage.getItem('starterSetup')||'{}')}catch(e){}workspaceRenderAnchors(setup.anchors||[]);$('programanchorunit').value=setup.unit||'lb';$('programstarterequipment').value=setup.equipment||'basic';workspacePriorities(Object.fromEntries(Object.keys(phaseSports).map(s=>[s,sports.includes(s)?'improve':'pause'])));
 $('programhorizon').value=Math.min(366,Math.max(7,Number(q.get('weeks')||12)*7));$('programhours').value=Number(q.get('hours')||3.5);$('programtarget').value=q.get('target')||'';$('programpath').value=q.get('target')?'event':'ongoing';$('programassessment').value=setup.assessment||'week';$('programentry').value='auto';$('programgoal').value=q.get('goal')||'My starter program';$('programstarter').checked=true;$('programstarterlevel').value=['easy','moderate','higher'].includes(q.get('level'))?q.get('level'):'easy';workspacePath();await workspaceSuggest();
}
workspaceWelcomeStarter();

function workspaceRenderAnchors(anchors=[]){
 $('programanchors').innerHTML=['BB squat','BB bench press','BB row'].map((name,i)=>{const a=anchors.find(x=>x.name===name)||{};return `<div class="calibration-row"><b>${name}</b><label>Weight<input type="number" data-anchor-weight="${i}" min="0" step="0.5" value="${a.weight||''}"></label><label>Reps<input type="number" data-anchor-reps="${i}" min="3" max="15" value="${a.reps||8}"></label><label>Reps left<input type="number" data-anchor-rir="${i}" min="0" max="5" value="${a.rir??2}"></label></div>`;}).join('');
 $('programanchors').querySelectorAll('input').forEach(e=>e.onchange=()=>workspaceDirty());
}
function workspaceAnchors(){return ['BB squat','BB bench press','BB row'].flatMap((name,i)=>{const weight=Number(document.querySelector(`[data-anchor-weight="${i}"]`)?.value);return weight?[{name,weight,reps:Number(document.querySelector(`[data-anchor-reps="${i}"]`).value),rir:Number(document.querySelector(`[data-anchor-rir="${i}"]`).value),unit:$('programanchorunit').value}]:[];});}

$('programneutral').onchange=()=>workspaceDirty();
$('programanchorunit').onchange=()=>workspaceDirty();
