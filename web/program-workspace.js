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
function workspaceCapacityFields(){
 return Object.keys(phaseSports).flatMap(s=>{const row={...(workspaceBaseGoal.capacity_demands||[]).find(g=>g.sport===s),sport:s,label:phaseSports[s]};for(const key of ['distance_m','duration_min','weekly_minutes']){const el=$('capacity-'+s+'-'+key);if(el?.value)row[key]=Number(el.value);else if(el)delete row[key];}return ['distance_m','duration_min','weekly_minutes','weight_kg','power_w'].some(k=>row[k]!=null)?[row]:[];});
}
function workspaceCapacityInputs(goals=[]){
 $('programcapacity').innerHTML=Object.entries(phaseSports).map(([s,name])=>{const g=goals.find(x=>x.sport===s)||{};return `<fieldset><legend>${esc(name)}</legend>${(s==='gym'?[['duration_min','Session duration (minutes)'],['weekly_minutes','Weekly training goal (minutes)']]:[['distance_m','Goal distance (meters)'],['duration_min','Goal duration (minutes)'],['weekly_minutes','Weekly training goal (minutes)']]).map(([k,t])=>`<label>${t}<input class="lfield" id="capacity-${s}-${k}" type="number" min="0.01" step="any" value="${esc(g[k]??'')}"></label>`).join('')}</fieldset>`;}).join('');
 $('programcapacity').querySelectorAll('input').forEach(el=>el.oninput=()=>workspaceDirty());
}
function capacityHistoryHtml(trends=[]){
 return `<details><summary>Calibration history · background evidence</summary><p class="sub">Estimated energy rate is one signal. Recovery reports and comparable sport-specific work are reviewed together.</p>${trends.map(t=>{const rows=t.series.filter(x=>x.kcal_per_hour!=null);const max=Math.max(1,...rows.map(x=>x.kcal_per_hour));const points=rows.map((x,i)=>({x:20+i*260/Math.max(1,rows.length-1),y:90-x.kcal_per_hour/max*70,row:x}));return `<article><h4>${esc(phaseSports[t.sport]||t.sport)} · ${esc(t.signal)}</h4>${rows.length?`<svg class="capacity-history-graph" viewBox="0 0 300 112" role="img" aria-label="${esc(t.sport)} estimated energy rate history"><path d="M20 20V92H285" fill="none" stroke="#667584"/><polyline points="${points.map(p=>p.x+','+p.y).join(' ')}" fill="none" stroke="#64b4ff" stroke-width="2"/>${points.map(p=>`<circle cx="${p.x}" cy="${p.y}" r="3" fill="${p.row.negative_report||p.row.delayed_recovery==='difficult'?'#ffac62':p.row.clean_followup?'#70dca1':'#64b4ff'}"><title>${esc(p.row.date)} · ${esc(p.row.kcal_per_hour)} kcal/hour · recovery ${esc(p.row.delayed_recovery||'unknown')}</title></circle>`).join('')}<text x="20" y="108" fill="#a9b8c5" font-size="9">${esc(rows[0].date)} → ${esc(rows.at(-1).date)} · up to ${Math.round(max)} kcal/hour</text></svg>`:'<p>No energy readings available.</p>'}<p class="sub">${esc(t.why)}</p><p class="sub">${esc(t.notice)}</p><details><summary>Comparison assumptions</summary><p class="sub">${esc(t.assumptions)}</p></details></article>`;}).join('')}</details>`;
}
function workspaceCapacityHtml(c){if(!c)return '';return `<section class="capacity-review"><h3>Capacity toward your goal</h3><p>${esc(c.notice)}</p>${c.demands.map(x=>`<article><h4>${esc(x.target.label)}</h4><p>Goal: ${x.target.distance_m?esc(x.target.distance_m)+' m · ':''}${x.target.duration_min?esc(x.target.duration_min)+' minutes':''}${x.target.weekly_minutes?' · '+esc(x.target.weekly_minutes)+' min/week':''}</p><p>Recent evidence: ${x.observed.sessions} sessions · longest ${esc(x.observed.longest_minutes??'unknown')} min · farthest ${esc(x.observed.farthest_m??'unknown')} m.</p><p>${esc(x.explanation)}</p><p>${esc(x.next_step)}. ${esc(x.tolerance)}</p><details><summary>Estimated demand and assumptions</summary>${x.energy?`<p>${x.energy.gross_kcal?'Estimated gross energy: '+esc(x.energy.gross_kcal)+' kcal. ':''}${esc(x.energy.formula||'')}</p>`:''}${x.mechanical?`<p>${esc(x.mechanical.meaning)} ${x.mechanical.impact_points?'Estimated impact: '+esc(x.mechanical.impact_points)+' points.':''}</p>`:''}<ul>${[...x.assumptions,...x.unknown].map(a=>`<li>${esc(a)}</li>`).join('')}</ul></details></article>`).join('')}${capacityHistoryHtml(c.tolerance_trends)}</section>`;}
function workspaceFields(){
 const event=$('programpath').value==='event';
 const fields={...workspaceBaseGoal,capacity_demands:workspaceCapacityFields(),goal:$('programgoal').value,target:event?$('programtarget').value:null,start:$('programstart').value,
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
 workspaceCapacityInputs(goal?.capacity_demands||[]);workspaceBaseGoal=draftCopy(goal||{});workspaceRenderAnchors(goal?.strength_anchors||[]);$('programneutral').checked=goal?.neutral_forecast!==false;$('programstarter').checked=false;$('programstarterlevel').value='easy';
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
/* The phase day grid (phase-grid.js): click a day, or shift/Cmd-click several, then pick a session type; drag to select
   a block to copy, paste or fill forward. Every change can be undone. */
const gridSel={phase:-1,dates:new Set(),drag:null,pending:null,clip:null,all:new Set(),last:null};
const gridTypes=[['ride','Bike'],['swim','Swim'],['gym','Lift'],['run','Run']];
let workspaceUndo=[],workspaceRedo=[];
function workspaceHistoryButtons(){$('programundo').disabled=!workspaceUndo.length;$('programredo').disabled=!workspaceRedo.length;}
function workspaceSnapshot(){workspaceUndo.push(JSON.stringify(workspacePhases));if(workspaceUndo.length>100)workspaceUndo.shift();workspaceRedo=[];workspaceHistoryButtons();}
function workspaceHistoryReset(){workspaceUndo=[];workspaceRedo=[];workspaceHistoryButtons();}
function workspaceHistory(back){
 const from=back?workspaceUndo:workspaceRedo,to=back?workspaceRedo:workspaceUndo;if(!from.length)return;
 to.push(JSON.stringify(workspacePhases));workspacePhases=JSON.parse(from.pop());gridClose(true);workspaceDirty(back?'Undone.':'Redone.');workspaceRender();workspaceHistoryButtons();
}
function gridDayLabel(p,iso){const d=new Date(iso+'T12:00');return d.getDate()===1||iso===p.start?d.toLocaleDateString('en-US',{month:'short',day:'numeric'}):String(d.getDate());}
/* Saved calendar workouts by date, from the active program's weeks (the same sessions the calendar shows). */
function gridSavedFromProgram(){const map={};for(const w of programState?.weeks||[])for(const s of w.slots||[])if(s.source==='scheduled'&&s.sport!=='rest')(map[s.date]=map[s.date]||[]).push({sport:s.sport,purpose:s.purpose});PhaseGrid.setSaved(map);}
function gridHtml(p,i){
 const rows=PhaseGrid.rows(p),auto=!PhaseGrid.manual(p),folded=rows.length>6&&!gridSel.all.has(i),shown=folded?rows.slice(0,6):rows;
 const pending=gridSel.pending?.phase===i?Object.fromEntries(gridSel.pending.targets.map(t=>[t.date,t.slots])):{};
 const cell=c=>{
  if(!c.inside)return '<span class="pg-cell pg-out" aria-hidden="true"></span>';
  const saved=PhaseGrid.isSaved(c.date),now=PhaseGrid.shown(p,c.date),incoming=pending[c.date],show=incoming||now||[];
  const said=saved?'saved workout, '+now.map(x=>phaseSports[x.sport]||x.sport).join(' and '):now===null?'placed automatically':now.length?now.map(x=>phaseSports[x.sport]||x.sport).join(' and '):'nothing planned';
  return `<button type="button" class="pg-cell${gridSel.phase===i&&gridSel.dates.has(c.date)?' pg-sel':''}${incoming?' pg-pending':''}${now===null?' pg-auto':''}${saved?' pg-saved':''}" data-cell="${c.date}" aria-label="${esc(c.date)}: ${esc(said)}" ${saved?`title="Saved workout: ${esc(now.map(x=>x.purpose||phaseSports[x.sport]).join(' + '))}. Change it on the calendar."`:''}><small>${esc(gridDayLabel(p,c.date))}</small><span class="pg-icons">${now===null&&!incoming?'<em>auto</em>':show.map(x=>`<i class="pg-dot pg-${esc(x.sport)}" title="${esc(phaseSports[x.sport]||x.sport)}">${ICON[x.sport]||''}</i>`).join('')}</span></button>`;
 };
 const n=gridSel.pending?.phase===i?gridSel.pending.conflicts:0;
 return `<p class="sub pg-hint">${auto?'Sessions here are placed automatically when you review. Click a day to plan this phase by hand.':'Click a day, or shift-click several, to add a session. Drag across days to copy, paste or fill them forward. Days with a saved workout (outlined) show it and change on the calendar.'}</p>
 <div class="pg-grid"><div class="pg-days" aria-hidden="true">${workspaceDays.map(d=>`<span>${d}</span>`).join('')}</div>${shown.map(r=>`<div class="pg-row">${r.map(cell).join('')}</div>`).join('')}</div>
 ${rows.length>6?`<button type="button" class="pg-more" data-grid-all>${folded?`Show all ${rows.length} weeks`:'Show fewer weeks'}</button>`:''}
 ${n?`<div class="pg-confirm" role="alertdialog" aria-label="Replace planned days"><b>Replace ${n} planned day${n===1?'':'s'}?</b><span class="sub">The highlighted days show what would go in.</span><button type="button" class="blue" data-pending="replace">Replace</button><button type="button" data-pending="empty">Fill empty days only</button><button type="button" data-pending="cancel">Cancel</button></div>`:''}`;
}
function gridRender(i){const host=document.querySelector(`[data-grid="${i}"]`);if(host&&workspacePhases[i])host.innerHTML=gridHtml(workspacePhases[i],i);}
function gridChange(i,fn,message){workspaceSnapshot();const r=fn(workspacePhases[i]);workspaceDirty(message);gridRender(i);return r;}
function gridMenu(){let m=$('pgmenu');if(!m){m=document.createElement('div');m.id='pgmenu';m.className='pg-menu';m.hidden=true;m.setAttribute('role','menu');$('programdialog').append(m);}return m;}
function gridClose(clearSelection){const m=$('pgmenu');if(m)m.hidden=true;if(clearSelection){const i=gridSel.phase;gridSel.dates=new Set();gridSel.pending=null;if(i>=0)gridRender(i);}}
function gridOpen(){
 const i=gridSel.phase,n=gridSel.dates.size;if(i<0||!n)return;
 const m=gridMenu(),anchor=document.querySelector(`[data-grid="${i}"] [data-cell="${gridSel.last}"]`)||document.querySelector(`[data-grid="${i}"] .pg-sel`);
 m.innerHTML=`<b>Add to ${n} day${n===1?'':'s'}</b><div class="pg-menu-types">${gridTypes.map(([s,t])=>`<button type="button" role="menuitem" data-menu-add="${s}">${ICON[s]||''}${t}</button>`).join('')}</div><div class="pg-menu-actions"><button type="button" role="menuitem" data-menu="copy">Copy</button><button type="button" role="menuitem" data-menu="paste" ${gridSel.clip?'':'disabled'}>Paste</button><button type="button" role="menuitem" data-menu="fill">Fill to end of phase</button><button type="button" role="menuitem" data-menu="clear">Clear</button><button type="button" role="menuitem" data-menu="close">Cancel</button></div>`;
 m.hidden=false;const r=(anchor||$('programphasecards')).getBoundingClientRect(),w=m.offsetWidth,h=m.offsetHeight;
 m.style.left=Math.max(8,Math.min(innerWidth-w-8,r.left))+'px';m.style.top=(r.bottom+h+8<innerHeight?r.bottom+6:Math.max(8,r.top-h-6))+'px';
 m.querySelector('button')?.focus();
}
function gridPlace(i,targets){
 if(!targets.length){$('programmessage').textContent='There are no days after the selection to fill.';return;}
 const conflicts=PhaseGrid.conflicts(workspacePhases[i],targets);
 if(!conflicts.length){gridChange(i,p=>PhaseGrid.apply(p,targets),`Placed ${targets.length} day${targets.length===1?'':'s'}. Review before applying.`);return;}
 gridSel.pending={phase:i,targets,conflicts:conflicts.length};gridRender(i);
}
function gridAction(action,sport){
 const i=gridSel.phase,p=workspacePhases[i],all=[...gridSel.dates].sort();if(i<0||!p)return;
 gridClose(false);
 const chosen=['add','clear'].includes(action)?all.filter(d=>!PhaseGrid.isSaved(d)):all,skipped=all.length-chosen.length;
 if(['add','clear'].includes(action)&&!chosen.length){$('programmessage').textContent='Those days have saved workouts. Change them on the calendar.';gridSel.dates=new Set();gridRender(i);return;}
 if(action==='add'){const r=gridChange(i,q=>PhaseGrid.addType(q,chosen,sport),`Added ${phaseSports[sport]} to ${chosen.length} day${chosen.length===1?'':'s'}. Review before applying.`);if(skipped)$('programmessage').textContent+=` ${skipped} day${skipped===1?' has a saved workout':'s have saved workouts'} and stayed as planned.`;if(r.full)$('programmessage').textContent=`${r.full} day${r.full===1?' already has':'s already have'} three sessions and stayed as ${r.full===1?'it was':'they were'}.`;}
 else if(action==='copy'){gridSel.clip=PhaseGrid.copy(p,chosen);$('programmessage').textContent=`Copied ${chosen.length} day${chosen.length===1?'':'s'}. Select a day and choose Paste, here or in another phase.`;}
 else if(action==='paste'&&gridSel.clip){gridSel.dates=new Set();gridPlace(i,PhaseGrid.targets(p,gridSel.clip,chosen[0]));return;}
 else if(action==='fill'){gridSel.dates=new Set();gridPlace(i,PhaseGrid.fillTargets(p,chosen));return;}
 else if(action==='clear')gridChange(i,q=>PhaseGrid.clear(q,chosen),'Cleared. Review before applying.');
 gridSel.dates=new Set();gridRender(i);
}
function gridRange(p,a,b){const [lo,hi]=a<b?[a,b]:[b,a];return PhaseGrid.dates(p).filter(d=>d>=lo&&d<=hi);}
function gridDrag(cellDate){
 const d=gridSel.drag;if(!d)return;const p=workspacePhases[d.phase];
 const next=new Set(d.base);if(d.toggle&&cellDate===d.from)next.delete(cellDate);else gridRange(p,d.from,cellDate).forEach(x=>next.add(x));
 gridSel.dates=next;gridSel.last=cellDate;
 document.querySelectorAll(`[data-grid="${d.phase}"] [data-cell]`).forEach(c=>c.classList.toggle('pg-sel',next.has(c.dataset.cell)));
}
(function gridEvents(){
 const cards=$('programphasecards');
 cards.addEventListener('pointerdown',e=>{
  const cell=e.target.closest('[data-cell]');if(!cell||e.button!==0)return;e.preventDefault();
  const i=Number(cell.closest('[data-draft-index]').dataset.draftIndex);if(gridSel.pending)return;
  const more=e.shiftKey||e.metaKey||e.ctrlKey;gridMenu().hidden=true;
  if(gridSel.phase!==i){const old=gridSel.phase;gridSel.phase=i;gridSel.dates=new Set();if(old>=0)gridRender(old);}
  gridSel.drag={phase:i,from:cell.dataset.cell,base:more?new Set(gridSel.dates):new Set(),toggle:more&&gridSel.dates.has(cell.dataset.cell),more};
  gridDrag(cell.dataset.cell);
 });
 cards.addEventListener('pointerover',e=>{const cell=e.target.closest('[data-cell]');if(cell&&gridSel.drag&&cell.closest(`[data-grid="${gridSel.drag.phase}"]`))gridDrag(cell.dataset.cell);});
 addEventListener('pointerup',()=>{const d=gridSel.drag;if(!d)return;gridSel.drag=null;if(!d.more&&gridSel.dates.size)gridOpen();});
 addEventListener('keyup',e=>{if(['Shift','Meta','Control'].includes(e.key)&&!gridSel.drag&&gridSel.dates.size&&gridMenu().hidden&&$('programdialog').open)gridOpen();});
 cards.addEventListener('click',e=>{
  const all=e.target.closest('[data-grid-all]');if(all){const i=Number(all.closest('[data-draft-index]').dataset.draftIndex);gridSel.all.has(i)?gridSel.all.delete(i):gridSel.all.add(i);gridRender(i);return;}
  const b=e.target.closest('[data-pending]');if(!b||!gridSel.pending)return;
  const {phase,targets}=gridSel.pending;gridSel.pending=null;
  if(b.dataset.pending==='cancel'){gridRender(phase);$('programmessage').textContent='Nothing changed.';return;}
  const n=gridChange(phase,p=>PhaseGrid.apply(p,targets,b.dataset.pending),'');$('programmessage').textContent=`${b.dataset.pending==='empty'?'Filled':'Placed'} ${n} day${n===1?'':'s'}. Review before applying.`;
 });
 gridMenu().addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.menuAdd)gridAction('add',b.dataset.menuAdd);else if(b.dataset.menu==='close')gridClose(true);else gridAction(b.dataset.menu);});
 $('programdialog').addEventListener('pointerdown',e=>{if(!e.target.closest('#pgmenu,[data-cell],.pg-confirm')&&(gridSel.dates.size||!gridMenu().hidden))gridClose(true);},true);
 $('programdialog').addEventListener('keydown',e=>{
  if(e.target.closest('input,textarea,select'))return;
  const mod=e.metaKey||e.ctrlKey,k=e.key.toLowerCase(),chosen=gridSel.dates.size;
  if(mod&&k==='z'){e.preventDefault();workspaceHistory(!e.shiftKey);}
  else if(mod&&k==='y'){e.preventDefault();workspaceHistory(false);}
  else if(mod&&k==='c'&&chosen){e.preventDefault();gridAction('copy');}
  else if(mod&&k==='v'&&chosen&&gridSel.clip){e.preventDefault();gridAction('paste');}
  else if((e.key==='Delete'||e.key==='Backspace')&&chosen){e.preventDefault();gridAction('clear');}
  else if(e.key==='Escape'&&(chosen||gridSel.pending||!gridMenu().hidden)){e.preventDefault();gridClose(true);}
 });
})();
function workspaceRender(){
 gridSel.pending=null;gridSel.dates=new Set();gridMenu().hidden=true;gridSavedFromProgram();
 workspaceReschedule();
 $('programphasecards').innerHTML=workspacePhases.length?workspacePhases.map((p,i)=>`<article class="program-draft-phase phase-${esc(p.color||workspaceColors[i%5])}" data-draft-index="${i}">
 <div class="program-draft-art phasephoto"><img src="${esc(artFile(phasePhoto(p,'draft')))}" style="${artPosition(phasePhoto(p,'draft'))}" alt="${esc(p.label)} inspiration"><div class="program-duration-controls"><button type="button" data-duration-delta="-1" aria-label="Decrease phase ${i+1} by one day" ${p.locked?'disabled':''}>−</button><label><input type="number" data-phase-days min="1" max="366" aria-label="Phase ${i+1} days" value="${p.days}" ${p.locked?'disabled':''}> days</label><button type="button" data-duration-delta="1" aria-label="Increase phase ${i+1} by one day" ${p.locked?'disabled':''}>＋</button></div></div>
 <div class="program-draft-phase-body"><input data-phase-label aria-label="Phase ${i+1} name" value="${esc(p.label)}"><small>${esc(p.start)} → ${esc(p.end)}</small>
 <div class="program-phase-order"><button type="button" data-move="-1" aria-label="Move phase ${i+1} earlier" ${i===0?'disabled':''}>←</button><button type="button" data-move="1" aria-label="Move phase ${i+1} later" ${i===workspacePhases.length-1?'disabled':''}>→</button><button type="button" data-duplicate>Duplicate</button><button type="button" data-remove>Remove</button></div>
 <div class="program-phase-settings"><label>Training purpose<select data-phase-stage>${Object.entries(workspacePurpose).map(([s,[name]])=>`<option value="${s}" ${draftStage(p)===s?'selected':''}>${name}</option>`).join('')}</select></label>
 <label>Color<select data-phase-color>${workspaceColors.map(c=>`<option ${p.color===c?'selected':''}>${c}</option>`).join('')}</select></label>
 <label class="program-check"><input data-phase-lock type="checkbox" ${p.locked?'checked':''}>Lock duration</label></div>
 <div class="phase-grid-host" data-grid="${i}">${gridHtml(p,i)}</div></div></article>`).join(''):'<p class="sub">No draft phases. Create evenly spaced phases, add a phase, or request a suggestion.</p>';
 $('programphasecards').querySelectorAll('[data-draft-index]').forEach(card=>{
  const i=Number(card.dataset.draftIndex),p=workspacePhases[i];
  const update=(selector,key,read=e=>e.value)=>{const e=card.querySelector(selector);e.onchange=()=>{workspaceSnapshot();p[key]=read(e);workspaceDirty();if(key==='color'||key==='locked')workspaceRender();};};
  update('[data-phase-label]','label');update('[data-phase-color]','color');update('[data-phase-lock]','locked',e=>e.checked);
  card.querySelector('[data-phase-stage]').onchange=e=>{workspaceSnapshot();p.stage=e.target.value;p.kind=workspacePurpose[p.stage][1];p.profile=p.stage==='recovery'?'recovery':$('programfocus').value;workspaceDirty();workspaceRender();};
  card.querySelector('[data-phase-days]').onchange=e=>workspaceChangeDays(i,Number(e.target.value));
  card.querySelectorAll('[data-duration-delta]').forEach(b=>b.onclick=()=>workspaceChangeDays(i,p.days+Number(b.dataset.durationDelta)));
  card.querySelectorAll('[data-move]').forEach(b=>b.onclick=()=>{workspaceSnapshot();const j=i+Number(b.dataset.move);[workspacePhases[i],workspacePhases[j]]=[workspacePhases[j],workspacePhases[i]];workspaceDirty();workspaceRender();});
  card.querySelector('[data-duplicate]').onclick=()=>workspaceAdd(draftCopy(p));
  card.querySelector('[data-remove]').onclick=()=>{
   try{if(p.locked)throw Error('Unlock this phase before removing it.');const next=workspacePhases.filter((_,j)=>j!==i).map(x=>({...x}));
    if($('programduration').value==='fixed'&&next.length){const recipient=next.findIndex(x=>!x.locked);if(recipient<0)throw Error('Unlock a remaining phase before redistributing these days.');next[recipient].days+=p.days;if(next[recipient].days>366)throw Error('This would exceed the phase duration limit.');}
    workspaceSnapshot();workspacePhases=next;workspaceDirty();workspaceRender();
   }catch(e){$('programmessage').textContent=e.message;}
  };
 });
}
function workspaceChangeDays(i,days){
 try{const before=JSON.stringify(workspacePhases);const next=ProgramDraftMath.redistribute(workspacePhases,i,days,$('programduration').value==='fixed');if(next.reduce((n,p)=>n+p.days,0)>366)throw Error('Keep the planning horizon within 366 days.');workspaceUndo.push(before);workspaceRedo=[];workspaceHistoryButtons();workspacePhases=next;workspaceDirty('Duration changed; other unlocked days were adjusted where required. Review the dates.');workspaceRender();}
 catch(e){$('programmessage').textContent=e.message;workspaceRender();}
}
function workspaceNewPhase(days=7){return {days,label:'Development',kind:'build',stage:'build',profile:$('programfocus').value,purpose:'Development',color:workspaceColors[workspacePhases.length%5],modes:workspaceFields().priorities,weights:{},locked:false,weekly_pattern:Array.from({length:7},()=>[{...PhaseGrid.REST}]),date_placements:{}};}
function workspaceAdd(phase){
 try{if(workspacePhases.length>=24)throw Error('Use at most 24 phases.');const fresh=!phase,before=JSON.stringify(workspacePhases);phase=phase||workspaceNewPhase();phase.locked=false;
  const days=phase.days;const next=[...workspacePhases,draftCopy(phase)];
  if($('programduration').value==='fixed'&&workspacePhases.length){next.at(-1).days=0;workspacePhases=ProgramDraftMath.redistribute(next,next.length-1,days,true);}else workspacePhases=next;
  if(workspacePhases.reduce((n,p)=>n+p.days,0)>366){workspacePhases=JSON.parse(before);throw Error('Keep the planning horizon within 366 days.');}
  if(fresh&&workspacePhases.length>1){workspaceReschedule();PhaseGrid.seedFrom(workspacePhases.at(-2),workspacePhases.at(-1));}
  workspaceUndo.push(before);workspaceRedo=[];workspaceHistoryButtons();workspaceDirty();workspaceRender();
 }catch(e){$('programmessage').textContent=e.message;}
}
function workspaceEven(){
 const count=Number($('programcount').value),span=$('programpath').value==='event'?draftSpan($('programstart').value,$('programtarget').value)+workspaceEventExtra:Number($('programhorizon').value);
 if(!Number.isInteger(count)||count<1||count>24||!Number.isInteger(span)||span<count||span>366){$('programmessage').textContent='Choose 1–24 phases and enough days for at least one day per phase, up to 366 days.';return;}
 workspaceSnapshot();workspacePhases=Array.from({length:count},(_,i)=>({...workspaceNewPhase(Math.floor(span/count)+(i<span%count?1:0)),label:'Development '+(i+1),color:workspaceColors[i%5]}));workspaceDirty();workspaceRender();
}
function workspaceRevise(){
 workspaceSource='revise';workspaceSetFields(programState?.goal);const start=$('programstart').value;
 workspacePhases=(programState?.phases||[]).filter(p=>p.end>start).map(p=>({...draftCopy(p),start:p.start<start?start:p.start,days:draftSpan(p.start<start?start:p.start,p.end),locked:p.locked??['specific','taper'].includes(draftStage(p))}));
 workspaceHistoryReset();workspaceDirty('Current program copied into a draft. Completed history stays in place.');workspaceRender();
}
async function workspaceSuggest(){
 workspaceDirty('Preparing a suggestion…');const fields=workspaceFields(),revision=workspaceRevision;
 const r=await post('/api/coach/program-builder',{...fields,action:'preview'});
 if(revision!==workspaceRevision||!$('programdialog').open)return;
 if(!r.ok){$('programmessage').textContent=r.j.error||'Could not build a suggestion.';return;}
 workspaceSnapshot();workspaceSource='suggest';workspacePhases=r.j.phases.map(p=>({...p,locked:['specific','taper'].includes(draftStage(p))}));workspaceRender();$('programmessage').textContent='Suggestion ready to edit. Review it before applying.';
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
 ${workspaceCapacityHtml(r.capacity_review)}${workspaceStarterHtml(r.starter)}${macroHtml(r.weeks)}</section>`;
}
$('programopen').onclick=openProgram;$('rulesprogramopen').onclick=openProgram;$('rulesphaseopen').onclick=()=>openPhaseEditor();
$('programsuggest').onclick=workspaceSuggest;
$('programblank').onclick=()=>{workspaceSnapshot();workspaceSource='blank';workspacePhases=[];workspaceDirty('Blank draft ready. Create phases or add them individually.');workspaceRender();};
$('programclear').onclick=()=>{workspaceSnapshot();workspacePhases=[];workspaceDirty('Draft cleared. Your active program is unchanged.');workspaceRender();};
$('programcreate').onclick=workspaceEven;$('programadd').onclick=()=>workspaceAdd();
$('programclose').onclick=()=>$('programdialog').close();
$('programundo').onclick=()=>workspaceHistory(true);$('programredo').onclick=()=>workspaceHistory(false);
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
 const r=await post('/api/coach/program-builder',{draft_id:workspaceReview.draft.id,action:'accept'});
 if(!r.ok){$('programmessage').textContent=r.j.error||'Could not apply the program.';if(revision===workspaceRevision){workspaceReview=null;programDraft=null;$('programaccept').disabled=true;}return;}
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

/* One goal field: a typed goal ("225 lb bench press") stays as written; an event's web address is read
   (/api/coach/event-url-preview, the same reader as Events & goals) and fills in the event name, its date (the peak),
   the planning horizon and the goal sport. Nothing is saved until the draft is reviewed and applied. */
const goalSports={run:'run',bike:'ride',swim:'swim',tri:'tri',gym:'gym'};
const goalLooksLikeUrl=v=>{const t=(v||'').trim();return !!t&&!/\s/.test(t)&&/^(https?:\/\/)?([a-z0-9-]+\.)+[a-z]{2,}(:\d+)?([\/?#]\S*)?$/i.test(t);};
let goalImportUndo=null,goalImportRun=0,goalLast='',goalBefore='';
function goalFields(){return {goal:$('programgoal').value,path:$('programpath').value,target:$('programtarget').value,sport:$('programsport').value,horizon:$('programhorizon').value,url:workspaceBaseGoal.event_url};}
function goalRestore(f){$('programgoal').value=f.goal;$('programpath').value=f.path;$('programtarget').value=f.target;$('programsport').value=f.sport;$('programhorizon').value=f.horizon;if(f.url)workspaceBaseGoal.event_url=f.url;else delete workspaceBaseGoal.event_url;workspacePath();$('programtarget').dispatchEvent(new Event('change'));}
function goalPrettyDate(iso){return iso?new Date(iso+'T12:00').toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric',year:'numeric'}):'';}
function goalCard(html,state){const box=$('programgoalimport');box.hidden=false;box.className='goal-import goal-import-'+state;box.innerHTML=html;}
function goalApply(c,url){
 goalImportUndo=goalImportUndo||{...goalFields(),goal:goalBefore};
 if(c.name)$('programgoal').value=c.name;
 $('programpath').value='event';if(c.date)$('programtarget').value=c.date;
 if(goalSports[c.sport])$('programsport').value=goalSports[c.sport];
 workspaceBaseGoal.event_url=c.source_url||url;workspacePath();$('programtarget').dispatchEvent(new Event('change'));
 const filled=['the goal name',c.date&&'the event date and planning horizon',goalSports[c.sport]&&'the goal sport'].filter(Boolean);
 const img=(c.image_candidates||[])[0];
 goalCard(`${img?`<img src="${esc(img)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">`:''}<div class="goal-import-body"><small>EVENT FROM THE WEB</small><h4>${esc(c.name||'Event')}</h4><p class="goal-import-facts">${[c.date&&`<span>${ICON.test||''}${esc(goalPrettyDate(c.date))}${c.time?' · '+esc(c.time):''}</span>`,c.location&&`<span>${esc(c.location)}</span>`,goalSports[c.sport]&&`<span>${ICON[goalSports[c.sport]]||''}${esc(phaseSports[goalSports[c.sport]]||(c.sport==='tri'?'Triathlon':c.sport))}</span>`,c.distance&&`<span>${esc(c.distance)}</span>`].filter(Boolean).join('')}</p>
 <p class="sub">Filled in ${esc(filled.join(', '))}.${c.date?'':' <b>The page didn’t give a date. Choose the event date below.</b>'} Check them before reviewing.</p>
 <div class="goal-import-actions"><a href="${esc(c.source_url||url)}" target="_blank" rel="noopener">Open event page ↗</a><button type="button" data-goal-undo>Undo</button></div></div>`,'done');
 if(!c.date)$('programtarget').focus();
 workspaceDirty('Event details filled in from the page. Check them, then review the draft.');
}
async function goalImport(raw){
 goalLast=raw;const url=/^https?:\/\//i.test(raw.trim())?raw.trim():'https://'+raw.trim(),run=++goalImportRun;
 goalCard(`<div class="goal-import-body"><small>READING THE EVENT PAGE</small><p class="goal-import-loading"><span class="goal-spinner" aria-hidden="true"></span>${esc(new URL(url).hostname)}…</p></div>`,'loading');
 let r;try{r=await post('/api/coach/event-url-preview',{url});}catch(e){r={ok:false,j:{}};}
 if(run!==goalImportRun)return;
 const found=(r.ok&&r.j.candidates||[]).filter(c=>c.name||c.date);
 if(!found.length){goalCard(`<div class="goal-import-body"><small>COULDN’T READ THAT PAGE</small><p>${esc(r.j?.error||'No event details were found on that page.')}</p><p class="sub">Type the event name in Goal and pick its date instead.</p></div>`,'error');return;}
 if(found.length===1)return goalApply(found[0],url);
 goalCard(`<div class="goal-import-body"><small>THIS PAGE LISTS ${found.length} EVENTS · CHOOSE YOURS</small><div class="goal-import-choices">${found.slice(0,8).map((c,i)=>`<button type="button" data-goal-pick="${i}"><b>${esc(c.name||'Event')}</b><span>${esc(goalPrettyDate(c.date)||'date not listed')}${c.location?' · '+esc(c.location):''}</span></button>`).join('')}</div></div>`,'choose');
 $('programgoalimport').querySelectorAll('[data-goal-pick]').forEach(b=>b.onclick=()=>goalApply(found[Number(b.dataset.goalPick)],url));
}
$('programgoal').addEventListener('focus',()=>{const v=$('programgoal').value;if(!goalLooksLikeUrl(v))goalBefore=v;});
$('programgoal').addEventListener('change',()=>{const v=$('programgoal').value;if(goalLooksLikeUrl(v)&&v!==goalLast)goalImport(v);});
$('programgoal').addEventListener('paste',()=>setTimeout(()=>{const v=$('programgoal').value;if(goalLooksLikeUrl(v)&&v!==goalLast)goalImport(v);},0));
$('programgoalimport').addEventListener('click',e=>{if(!e.target.closest('[data-goal-undo]')||!goalImportUndo)return;goalRestore(goalImportUndo);goalImportUndo=null;goalLast='';$('programgoalimport').hidden=true;workspaceDirty('Event details undone.');});
$('programdialog').addEventListener('close',()=>{goalImportUndo=null;$('programgoalimport').hidden=true;});
