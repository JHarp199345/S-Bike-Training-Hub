/* Trusted Hub UI; never loaded inside the untrusted game. */
(async()=>{'use strict';
 if(window!==top||document.documentElement.dataset.embedded==='true'||document.getElementById('hub-support'))return;
 const policy=window.HubSupportPolicy,KEY='sbike-support-v1';
 let state=policy.fresh();try{const saved=JSON.parse(localStorage.getItem(KEY));if(saved&&saved.modules&&saved.shown)state=saved;}catch{}
 const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(state));}catch{}};
 const host=document.createElement('section');host.id='hub-support';
 host.innerHTML=`<button class="hs-badge" aria-label="Help and feedback" title="Help and feedback"><svg viewBox="0 0 36 29" fill="none"><path d="M5 6h22v12c0 4-4 7-11 7S5 22 5 18V6Z" stroke="currentColor" stroke-width="1.8"/><path d="M27 8h2a5 5 0 0 1 0 10h-2M3 27h27" stroke="currentColor" stroke-width="1.8"/><path d="M16 12c-3-4-8 1 0 7 8-6 3-11 0-7Z" fill="#ff6433"/></svg></button>
 <aside class="hs-prompt" hidden aria-label="Optional support invitation"><button class="hs-close" aria-label="Dismiss invitation">×</button><h2>Enjoying the games?</h2><p>If you’d like to support more games and improvements, you can buy me a coffee. Supporting development is always optional.</p><div class="hs-actions"><button class="hs-donate" aria-label="Donate on Ko-fi"><img src="/web/kofi-donate-button.png" alt="Donate on Ko-fi"></button><button class="hs-supported">Already supported</button></div><div class="hs-actions"><button class="hs-quiet hs-later">Not now</button><button class="hs-quiet hs-never">Don’t ask again</button></div><p class="hs-small">Opens Ko-fi in a new tab.</p></aside>
 <dialog class="hs-help"><button class="hs-close" aria-label="Close help">×</button><h2>Help & feedback</h2><details><summary>Do I need to donate to use the Hub or Monster Chase?</summary><p>No. The Hub and this Monster Chase donation release work without payment or activation.</p></details><details><summary>What information does a game receive?</summary><p>Only the readings and controls shown when you review its manifest. Your workout history and reports are not supplied to it.</p></details><details><summary>How do I update a module?</summary><p>Download its new ZIP from the same itch.io project. Drop it into Add a module in the Ride menu, then review and approve replacing it.</p></details><details><summary>Why can’t the game find my bike?</summary><p>Check the Hub’s bike connection in Settings first. The game uses that connection.</p></details><h3>How’s it feeling?</h3><p class="hs-small">Optional ratings: 1 = low, 5 = high. Click again to clear.</p><div class="hs-ratings"></div><h3>Three small ideas</h3><div class="hs-ideas"></div><button class="hs-review-button">Review feedback</button><p class="hs-small">Nothing is sent automatically. No training records or logs are attached.</p></dialog>
 <dialog class="hs-review"><button class="hs-close" aria-label="Close feedback preview">×</button><h2>Review your feedback</h2><p>GitHub issues are public. Leave out health details, personal information and keys.</p><div class="hs-preview"></div><a class="hs-github" target="_blank" rel="noopener noreferrer">Open draft on GitHub ↗</a><p class="hs-small">You review and submit it on GitHub.</p></dialog>`;
 document.body.append(host);const $=s=>host.querySelector(s),prompt=$('.hs-prompt'),badge=$('.hs-badge');
 const dismiss=()=>{prompt.hidden=true;badge.classList.remove('hs-glow');};
 const consider=()=>{const id=policy.pending(state);if(!id||document.querySelector('dialog[open]'))return;state.shown[id]=true;save();prompt.hidden=false;badge.classList.add('hs-glow');};
 $('.hs-prompt .hs-close').onclick=$('.hs-later').onclick=dismiss;
 $('.hs-never').onclick=()=>{state.never=true;save();dismiss();};
 $('.hs-supported').onclick=()=>{state.supported=true;save();dismiss();};
 $('.hs-donate').onclick=()=>{dismiss();window.open('https://ko-fi.com/jharp199345','_blank','noopener,noreferrer');};
 badge.onclick=()=>{dismiss();$('.hs-help').showModal();};
 for(const d of host.querySelectorAll('dialog'))d.querySelector('.hs-close').onclick=()=>d.close();
 const scores={};for(const name of ['Enjoyment','Ease of use','Reliability']){
 const row=document.createElement('div');row.className='hs-rating';const label=document.createElement('span');label.textContent=name;row.append(label);
 for(let n=1;n<=5;n++){const b=document.createElement('button');b.textContent=n;b.setAttribute('aria-label',name+': '+n+' of 5');b.setAttribute('aria-pressed','false');b.onclick=()=>{scores[name]=scores[name]===n?null:n;for(const c of row.querySelectorAll('button'))c.setAttribute('aria-pressed',String(c===b&&scores[name]===n));};row.append(b);}$('.hs-ratings').append(row);}
 for(let n=1;n<=3;n++){const l=document.createElement('label');l.textContent='Idea '+n+' (up to 160 characters)';const input=document.createElement('input');input.maxLength=160;l.append(input);$('.hs-ideas').append(l);}
 $('.hs-review-button').onclick=()=>{const ideas=[...host.querySelectorAll('input')].map(i=>i.value.trim()).filter(Boolean);if(!Object.values(scores).some(Boolean)&&!ideas.length)return;
 const text='S-Bike Training Hub feedback\n'+Object.entries(scores).filter(([,v])=>v).map(([k,v])=>k+': '+v+'/5').join('\n')+(ideas.length?'\n\nSuggestions:\n'+ideas.map(i=>'• '+i).join('\n'):'');
 $('.hs-preview').textContent=text;$('.hs-github').href='https://github.com/JHarp199345/S-Bike-Training-Hub/issues/new?title='+encodeURIComponent('Hub feedback')+'&body='+encodeURIComponent(text);$('.hs-review').showModal();};
 let busy=false;async function poll(){if(busy)return;busy=true;const ac=new AbortController(),timer=setTimeout(()=>ac.abort(),4000);
 try{const r=await fetch('/status',{signal:ac.signal});if(!r.ok)return;const s=await r.json();policy.observe(state,s,Date.now()/1000);save();if(state.current||s.workout||s.route||s.test)dismiss();else consider();}catch{}finally{clearTimeout(timer);busy=false;}}
 addEventListener('storage',e=>{if(e.key===KEY){try{const s=JSON.parse(e.newValue);if(s?.modules&&s?.shown)state=s;}catch{}if(state.never||state.supported)dismiss();}});
 poll();setInterval(poll,5000);
})();
