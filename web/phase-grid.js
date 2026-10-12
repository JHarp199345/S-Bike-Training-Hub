/* Phase day grid: which kind of session goes on which day of a phase (2026-10-11).
   The Plan page builds programs, not workouts: a cell holds up to three session types (bike, swim, lift, run).
   Weekly workouts are filled in later from the reports.

   Storage stays in the existing phase shape. A phase planned by hand keeps its sessions in date_placements and a
   weekly_pattern of rest days, so blank days stay rest instead of being filled by the automatic planner. A phase with
   no placements and no pattern is "automatic": the planner places its sessions when the draft is reviewed.

   The grid shows the calendar: days with saved workouts show those workouts (they always win over a placement, as in
   program_builder.macro_weeks) and can't be changed here; a day with nothing planned shows nothing. A repeating weekly
   template is not shown as sessions, because it isn't on the calendar. */
(function(root){
 const REST={sport:'rest',purpose:'Rest / open day'};
 const MAX=3;
 const add=(iso,n)=>{const d=new Date(iso+'T12:00');d.setDate(d.getDate()+n);return d.toLocaleDateString('en-CA');};
 const span=(a,b)=>Math.round((new Date(b+'T12:00')-new Date(a+'T12:00'))/86400000);
 const weekday=iso=>(new Date(iso+'T12:00').getDay()+6)%7;          // Monday 0 … Sunday 6
 const inside=(p,iso)=>iso>=p.start&&iso<p.end;
 const real=slots=>(slots||[]).filter(s=>s&&s.sport&&s.sport!=='rest');
 let saved={};                                                    // date -> saved calendar sessions
 const setSaved=map=>{saved=map||{};};
 const isSaved=iso=>real(saved[iso]).length>0;

 function dates(p){const out=[];for(let d=p.start;d<p.end;d=add(d,1))out.push(d);return out;}

 /* Calendar rows, Monday to Sunday; days before the start or after the end of the phase are marked outside. */
 function rows(p){
  const out=[];if(!p.start||!p.end||p.end<=p.start)return out;
  for(let monday=add(p.start,-weekday(p.start));monday<p.end;monday=add(monday,7))
   out.push(Array.from({length:7},(_,i)=>{const date=add(monday,i);return {date,inside:inside(p,date)};}));
  return out;
 }

 function manual(p){return !!p.weekly_pattern||Object.keys(p.date_placements||{}).length>0;}

 /* A day's placed sessions: its dated placement, [] when nothing is placed, or null for an automatic phase. */
 function slots(p,iso){
  const dated=(p.date_placements||{})[iso];if(dated)return real(dated);
  return manual(p)?[]:null;
 }
 /* What a cell shows: saved workouts first, then placements. */
 function shown(p,iso){return isSaved(iso)?real(saved[iso]):slots(p,iso);}

 /* Switch a phase to hand planning: its dated placements stay, and the weekly template becomes rest so days with
    nothing planned stay empty, as the grid shows them. */
 function makeManual(p){
  p.date_placements=p.date_placements||{};
  const allRest=Array.isArray(p.weekly_pattern)&&p.weekly_pattern.length===7&&p.weekly_pattern.every(x=>!real(Array.isArray(x)?x:[x]).length);
  if(!allRest)p.weekly_pattern=Array.from({length:7},()=>[{...REST}]);
  return p;
 }

 function set(p,iso,list){
  makeManual(p);const keep=real(list).slice(0,MAX);
  if(keep.length)p.date_placements[iso]=keep.map(x=>({...x}));else delete p.date_placements[iso];
 }

 /* Add one session type to each chosen day (never replacing). Days already holding three are skipped. */
 function addType(p,isoList,sport,purpose){
  makeManual(p);let added=0,full=0;
  for(const d of isoList){if(!inside(p,d)||isSaved(d))continue;const cur=slots(p,d)||[];if(cur.length>=MAX){full++;continue;}set(p,d,[...cur,{sport,purpose:purpose||p.label||'Planned session'}]);added++;}
  return {added,full};
 }

 function clear(p,isoList){makeManual(p);let n=0;for(const d of isoList)if(inside(p,d)&&!isSaved(d)&&(slots(p,d)||[]).length){set(p,d,[]);n++;}return n;}

 /* A copy remembers each chosen day's sessions by its distance from the first chosen day, including empty days, and
    repeats in whole weeks so a pattern keeps its weekdays when it is filled forward. */
 function copy(p,isoList){
  const list=[...new Set(isoList)].filter(d=>inside(p,d)).sort();if(!list.length)return null;
  const base=list[0],length=span(base,list.at(-1))+1;
  return {period:Math.ceil(length/7)*7,cells:list.map(d=>({offset:span(base,d),slots:(shown(p,d)||[]).map(x=>({sport:x.sport,purpose:x.purpose||p.label}))}))};
 }

 /* Where a paste (or a fill) would land: [{date, slots}] inside the phase. */
 function targets(p,clip,anchor,repeat=false){
  if(!clip)return [];const out=[];
  for(let start=anchor;start<p.end;start=add(start,clip.period)){
   for(const c of clip.cells){const date=add(start,c.offset);if(inside(p,date)&&!isSaved(date))out.push({date,slots:c.slots});}
   if(!repeat)break;
  }
  return out;
 }
 /* Fill forward from a selection: the copied block repeats after itself to the end of the phase. */
 function fillTargets(p,isoList){const clip=copy(p,isoList);if(!clip)return [];return targets(p,clip,add([...isoList].sort()[0],clip.period),true);}

 const same=(a,b)=>JSON.stringify(real(a).map(x=>x.sport))===JSON.stringify(real(b).map(x=>x.sport));
 /* Days that already hold sessions and would change. */
 function conflicts(p,list){return list.filter(t=>{const cur=slots(p,t.date)||[];return cur.length&&!same(cur,t.slots);});}

 /* mode "replace" writes every target; "empty" only fills days with nothing planned. */
 function apply(p,list,mode='replace'){
  makeManual(p);let n=0;
  for(const t of list){const cur=slots(p,t.date)||[];if(mode==='empty'&&cur.length)continue;if(same(cur,t.slots))continue;set(p,t.date,t.slots);n++;}
  return n;
 }

 /* A new phase starts with the previous phase's last week, repeated, when that phase was planned by hand. */
 function seedFrom(prev,p){
  if(!prev||!manual(prev)||!prev.end||!p.start)return false;
  const week=Array.from({length:7},(_,i)=>add(prev.end,i-7));
  const byDay=Object.fromEntries(week.filter(d=>d>=prev.start).map(d=>[weekday(d),shown(prev,d)||[]]));
  makeManual(p);for(const d of dates(p)){const s=byDay[weekday(d)];if(s&&s.length&&!isSaved(d))set(p,d,s.map(x=>({sport:x.sport,purpose:p.label||x.purpose})));}
  return true;
 }

 const api={REST,MAX,add,span,weekday,dates,rows,manual,slots,shown,setSaved,isSaved,makeManual,set,addType,clear,copy,targets,fillTargets,conflicts,apply,seedFrom};
 if(typeof module!=='undefined')module.exports=api;else root.PhaseGrid=api;
})(typeof window!=='undefined'?window:globalThis);
