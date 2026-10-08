/* Today · re-check card: after a bad report, a short evening and next-morning re-check decides what happens next. */
(()=>{
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SITES={feet:'Feet & lower legs',legs:'Knees & legs',hips:'Hips & lower back',shoulders:'Shoulders',other:'Somewhere else'};
const when=iso=>new Date(iso).toLocaleString(undefined,{weekday:'short',hour:'numeric',minute:'2-digit'});
async function render(){
 const box=document.getElementById('recheck-box');if(!box)return;
 let data;try{const r=await fetch('/api/coach/rechecks',{cache:'no-store'});if(!r.ok)throw Error();data=await r.json();}catch(e){box.hidden=true;return;}
 const open=data.open[0],last=data.recent.find(r=>r.status==='closed'&&(Date.now()-Date.parse(r.outcome?.at||r.created))<2*86400e3);
 if(!open&&!last){box.hidden=true;return;}box.hidden=false;
 if(!open){box.innerHTML=`<section class="recheck-card closed"><h3>Re-check · ${esc({settled:'settled',step_back:'step back',stop:'see a professional'}[last.outcome.result]||last.outcome.result)}</h3><p>${esc(last.outcome.advice)}</p></section>`;return;}
 const now=Date.now(),due=open.due.filter(x=>!open.answers.some(a=>a.slot===x.slot&&Date.parse(a.at)>=Date.parse(x.at)-6*3600e3)),next=due[0];
 const ready=next&&Date.parse(next.at)-now<3*3600e3;
 box.innerHTML=`<section class="recheck-card"><h3>Re-check after a report</h3><p><b>Why:</b> ${open.reasons.map(esc).join(' · ')}</p><p>${esc(open.outcome?.advice||open.advice)}</p>
 <p class="sub">${next?`Next re-check: ${esc(next.slot)} · ${esc(when(next.at))}${ready?' · ready now':''}`:'All scheduled re-checks answered.'}</p>
 <details ${ready?'open':''}><summary>Answer the ${esc(next?.slot||'')} re-check</summary><div class="recheck-form">
 ${Object.entries(SITES).map(([k,v])=>`<div class="sl"><label>${v} pain <span><b data-rcv="${k}">${open.trigger.pain[k]??0}</b>/10</span></label><input type="range" min="0" max="10" value="${open.trigger.pain[k]??0}" data-rc-pain="${k}"></div>`).join('')}
 <div class="sl"><label>Stiffness <span><b data-rcv="stiff">0</b>/10</span></label><input type="range" min="0" max="10" value="0" data-rc-stiff></div>
 <label>Walking <select data-rc="walking"><option value="easy">Easy</option><option value="some">Some discomfort</option><option value="hard">Hard</option></select></label>
 <label>Stairs <select data-rc="stairs"><option value="easy">Easy</option><option value="some">Some discomfort</option><option value="hard">Hard</option></select></label>
 <fieldset><legend>Any of these?</legend>${Object.entries(data.red_flags).map(([k,v])=>`<label class="rc-flag"><input type="checkbox" data-rc-flag="${k}"> ${esc(v)}</label>`).join('')}</fieldset>
 <button class="blue" data-rc-save>Save re-check</button><p data-rc-msg class="sub" role="status"></p></div></details></section>`;
 box.querySelectorAll('input[type=range]').forEach(i=>i.oninput=()=>{box.querySelector(`[data-rcv="${i.dataset.rcPain||'stiff'}"]`).textContent=i.value;});
 box.querySelector('[data-rc-save]').onclick=async()=>{const body={id:open.id,slot:next?.slot,pain:Object.fromEntries([...box.querySelectorAll('[data-rc-pain]')].filter(i=>+i.value>0||open.trigger.pain[i.dataset.rcPain]!=null).map(i=>[i.dataset.rcPain,+i.value])),stiffness:+box.querySelector('[data-rc-stiff]').value,
   walking:box.querySelector('[data-rc="walking"]').value,stairs:box.querySelector('[data-rc="stairs"]').value,red_flags:[...box.querySelectorAll('[data-rc-flag]:checked')].map(i=>i.dataset.rcFlag)};
  const r=await fetch('/api/coach/recheck',{method:'POST',body:JSON.stringify(body)});const j=await r.json();
  box.querySelector('[data-rc-msg]').textContent=r.ok?j.outcome.advice:(j.error||'Not saved. Please try again.');if(r.ok){setTimeout(render,1800);window.LoadOutlook?.render();}};
}
window.Recheck={render};document.addEventListener('DOMContentLoaded',render);window.addEventListener('fitness-readings',render);
})();
