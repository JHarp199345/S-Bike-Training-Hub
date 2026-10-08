/* Shared read-only detail views; use the same recorded Hub readings everywhere. */
(()=>{
const esc=t=>String(t??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const SPORTC={bike:'#60a5fa',run:'#f97316',swim:'#22d3ee',gym:'#a78bfa',walk:'#facc15',lift:'#a78bfa',impact:'#f97316',other:'#94a3b8'};
function bars(rows,max){ max=max||Math.max(1,...rows.map(r=>r.v));
  return rows.map(r=>`<div class="brow"><span>${esc(r.label)}</span><div class="btrack"><i style="width:${Math.min(100,100*r.v/max)}%;background:${r.c||'#60a5fa'}"></i>${r.limit?`<em style="left:${Math.min(100,100*r.limit/max)}%"></em>`:''}</div><span>${esc(r.txt)}</span></div>`).join(''); }
function pie(el,parts,unit){ const tot=parts.reduce((a,p)=>a+p.v,0); if(!tot){ el.innerHTML='<div class="sub">Nothing this week yet.</div>'; return; }
  let a=-Math.PI/2, paths='';
  for(const p of parts){ const b=a+2*Math.PI*p.v/tot, large=b-a>Math.PI?1:0, x1=70+60*Math.cos(a), y1=70+60*Math.sin(a), x2=70+60*Math.cos(b), y2=70+60*Math.sin(b);
    paths+=parts.length===1?`<circle cx="70" cy="70" r="60" fill="${p.c}"/>`:`<path d="M70 70 L${x1} ${y1} A60 60 0 ${large} 1 ${x2} ${y2} Z" fill="${p.c}"/>`; a=b; }
  el.innerHTML=`<svg viewBox="0 0 140 140">${paths}<circle cx="70" cy="70" r="30" fill="var(--card)"/></svg><div class="legend" style="display:grid;gap:4px">${parts.map(p=>`<span><i style="background:${p.c}"></i>${esc(p.label)} · ${Math.round(p.v)}${unit} (${Math.round(100*p.v/tot)}%)</span>`).join('')}</div>`; }
function lines(el,days,series){ const W=600,H=220,P=28; const n=days.length; if(n<2){ el.outerHTML='<div class="sub">Not enough days yet.</div>'; return; }
  const vals=series.flatMap(s=>days.map(s.get)).filter(v=>v!=null), lo=Math.min(0,...vals), hi=Math.max(1,...vals);
  const x=i=>P+(W-2*P)*i/(n-1), y=v=>H-P-(H-2*P)*(v-lo)/(hi-lo);
  let g=`<line x1="${P}" x2="${W-P}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line)"/>`;
  for(const s of series) g+=`<polyline fill="none" stroke="${s.c}" stroke-width="2.5" points="${days.map((d,i)=>`${x(i)},${y(s.get(d)??0)}`).join(' ')}"/>`;
  g+=`<text x="${P}" y="${H-6}" font-size="13" fill="var(--muted)">${esc(days[0].date.slice(5))}</text><text x="${W-P}" y="${H-6}" font-size="13" fill="var(--muted)" text-anchor="end">${esc(days[n-1].date.slice(5))}</text>`;
  g+=`<text x="4" y="${y(hi)+4}" font-size="13" fill="var(--muted)">${Math.round(hi)}</text>`;
  el.setAttribute('viewBox',`0 0 ${W} ${H}`); el.innerHTML=g; }

function cardio(container,L){
 const d=WorkRate.data;if(!d){container.innerHTML='<p>Work-rate history is loading.</p>';return;}
 container.innerHTML='<div class="fitness-chart-grid"><article class="fitness-chart-card"><h3>Heart & lungs · daily recorded exposure</h3><div data-rate-history></div></article><article class="fitness-chart-card"><h3>Where cardio exposure came from · 3 days</h3><div class="pie" data-rate-mix></div><p class="means">Existing cardiovascular exposure points from recorded activities. These are modeled contributions, not watch-measured fatigue or oxygen use.</p></article></div>';
 WorkRate.regional(container.querySelector('[data-rate-history]'),d,'engine');
 const mix={};for(const row of d.daily.slice(-3))for(const [sport,values]of Object.entries(row.sports))mix[sport]=(mix[sport]||0)+values.engine;
 pie(container.querySelector('[data-rate-mix]'),Object.entries(mix).filter(([,v])=>v>0).map(([k,v])=>({label:k,v:v/3,c:SPORTC[k]||SPORTC.other})),' pts/day');
}
function mechanical(container,L){
 const d=WorkRate.data;if(!d){container.innerHTML='<p>Regional history is loading.</p>';return;}
 const rows=d.daily.slice(-3),regions=d.daily.at(-1)?.regions||{};
 const rates=Object.entries(regions).map(([k,r])=>({key:k,name:r.name,value:rows.reduce((a,day)=>a+Math.max(0,...Object.values(day.regions[k]?.sources||{})),0)/3})).sort((a,b)=>b.value-a.value);
 container.innerHTML=`<h3>Regional recorded work · 3-day rate</h3><p class="means">Open a region to see its dates, rates and contributing sports. Brightness shows relative recorded exposure, not pain, tissue damage, remaining fatigue or a training limit. Source indices overlap and must not be interpreted as physical energy.</p><details><summary>Choose a body region</summary><div class="wr-regions">${rates.map(r=>`<button type="button" data-region="${r.key}" aria-pressed="false"><b>${esc(r.name)}</b><small>${r.value.toFixed(1)} dominant source index/day</small></button>`).join('')}</div></details><div data-region-history></div><details><summary>Mechanical source mix · recorded indices</summary><div class="pie" data-rate-mix></div><p class="means">Share of the existing model's recorded impact and muscle indices over 3 days. This is an index visualization, not an energy or force breakdown.</p></details>`;
 const mix={};for(const row of rows)for(const [sport,v]of Object.entries(row.sports)){mix[sport+' · impact']=(mix[sport+' · impact']||0)+v.impact;mix[sport+' · muscle']=(mix[sport+' · muscle']||0)+v.muscle;}
 pie(container.querySelector('[data-rate-mix]'),Object.entries(mix).filter(([,v])=>v>0).map(([k,v])=>({label:k,v:v/3,c:SPORTC[k.split(' ')[0]]||SPORTC.other})),' index/day');
 container.querySelectorAll('[data-region]').forEach(b=>b.onclick=()=>{container.querySelectorAll('[data-region]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));const target=container.querySelector('[data-region-history]');target.dataset.metric=b.dataset.region;WorkRate.regional(target,d,b.dataset.region);});
}
function watch(container,L){
 container.innerHTML=`<div class="fitness-chart-grid"><article class="fitness-chart-card"><h3>Swimming · stroke consistency</h3><div data-chart="swim-hold"></div><p class="means">Recorded stroke consistency during each swim, using changes in SWOLF. Compare similar strokes and sets; drills, pacing and rest affect these readings.</p></article><article class="fitness-chart-card"><h3>Cycling · heart-rate response</h3><div data-chart="ride-recovery"></div><p class="means">Available heart-rate drops after efforts and heart rate at comparable power. Context matters when comparing rides.</p></article></div>`;
 const sl=L.insights?.swim?.session_length,swims=sl?.swims||[];
 container.querySelector('[data-chart="swim-hold"]').innerHTML=swims.length?`<div class="bars">${bars(swims.slice(-8).map(s=>({label:s.date.slice(5),v:s.held_m,c:s.broke?'#eab308':'#22c55e',txt:s.held_m+' of '+s.total_m+' m'})),Math.max(1,...swims.map(s=>s.total_m)))}</div>`:'<p class="sub">No pool swims available yet.</p>';
 const rec=L.insights?.ride?.recovery,aer=L.aerobic?.trend,rides=(rec?.rides||[]).filter(r=>r.drop_60!=null);
 container.querySelector('[data-chart="ride-recovery"]').innerHTML=(rides.length?`<div class="bars">${bars(rides.slice(-8).map(r=>({label:r.date.slice(5),v:r.drop_60,c:'#60a5fa',txt:r.drop_60+' bpm'})))}</div>`:'<p class="sub">No recorded heart-rate recovery after efforts yet.</p>')+(aer?.hr_at_band?`<p class="sub">Heart rate at 100–120 W: ${esc(aer.hr_at_band.latest)} bpm (${aer.hr_at_band.per_week>0?'+':''}${esc(aer.hr_at_band.per_week)} per week over ${esc(aer.hr_at_band.rides)} rides).</p>`:'');
}
window.FitnessCharts={SPORTC,bars,pie,lines,cardio,mechanical,watch};
})();
