/* Rest is recovery information, never a three-stage workout or a scored exercise. */
(function(root){
 'use strict';
 const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const valid=n=>n!==null&&n!==undefined&&n!==''&&Number.isFinite(Number(n));
 function period(now=new Date()){return now.getHours()>=6&&now.getHours()<18?'day':'night';}
 function render(s={},r={},now=new Date()){
  const m=r.morning||{},c=r.checkin||{},rows=[];
  if(valid(m.sleep_min))rows.push(['Watch sleep',`${Math.floor(m.sleep_min/60)}h ${Math.round(m.sleep_min%60)}m`]);
  if(valid(m.hrv?.ms))rows.push(['Watch HRV',`${m.hrv.ms} ms`]);
  if(valid(m.resting_hr?.bpm))rows.push(['Resting heart rate',`${m.resting_hr.bpm} bpm`]);
  if(valid(c.sleep))rows.push(['Your sleep rating',`${c.sleep}/10`]);
  const why=Object.entries(r.systems?.systems||{}).filter(([,v])=>['easy','rest'].includes(v.level)).map(([k,v])=>[({engine:'Heart & lungs',impact:'Feet & bones',muscle:'Leg muscles'})[k]||k,(v.why||[]).join(' · ')]);
  const advice=s.explanation?.text||s.note||'';
  return `<article class="rest-card" data-rest-period="${period(now)}"><div class="rest-content"><span class="wf-kicker">Make room to recover</span><h3>${E(s.name||'Rest & recovery')}</h3><p>${advice?E(advice):'Today is set aside for recovery. Keep the day comfortable and give yourself time to unwind.'}</p>${rows.length?`<div class="rest-readings">${rows.map(([label,value])=>`<div><small>${E(label)}</small><strong>${E(value)}</strong></div>`).join('')}</div>`:'<p class="sub">No recovery readings available yet. Import your watch data or add a check-in.</p>'}${rows.some(x=>x[0].startsWith('Watch')||x[0]==='Resting heart rate')?`<p class="sub">Imported overnight readings · ${E(m.date||'date unavailable')}${m.date&&r.date&&m.date!==r.date?' · earlier reading':''}. These are separate from your reported sleep rating.</p>`:''}${why.length?`<details><summary>What the Hub is asking you to rest</summary><ul>${why.map(([label,text])=>`<li><b>${E(label)}</b>${text?' — '+E(text):''}</li>`).join('')}</ul><p class="sub">Model guidance from the current readings; this is not a new injury assessment.</p></details>`:''}<p class="rest-sleep">For adults, aim for 7–9 hours of sleep and allow quiet time before bed. <a href="https://www.nhlbi.nih.gov/health/heart-healthy-living/sleep" target="_blank" rel="noopener">Sleep guidance</a></p><small class="rest-clock">Artwork follows your device’s local time (day 6 am–6 pm); sunrise and sunset are not configured.</small></div></article>`;
 }
 function update(rootNode,now=new Date()){rootNode.querySelectorAll('.rest-card').forEach(x=>x.dataset.restPeriod=period(now));}
 root.RestCard={render,period,update};if(typeof module!=='undefined')module.exports=root.RestCard;
 if(typeof document!=='undefined'){setInterval(()=>update(document),60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)update(document);});}
})(typeof window!=='undefined'?window:globalThis);
