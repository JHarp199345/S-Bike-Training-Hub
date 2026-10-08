/* Display preference only. Stored energy and model calculations stay in joules. */
(()=>{
if(window.EnergyUnits)return;
const KEY='hub-energy-unit',J_PER_KCAL=4184;
let unit='calories';
try{if(localStorage.getItem(KEY)==='joules')unit='joules';}catch(e){}
const valid=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0;
function compact(j){
 if(!valid(j))return {value:'—',unit:unit==='calories'?'kcal':'J'};
 if(unit==='calories')return {value:(j/J_PER_KCAL).toLocaleString(undefined,{maximumSignificantDigits:3}),unit:'kcal'};
 const scale=j>=1e6?1e6:j>=1000?1000:1;
 return {value:(j/scale).toLocaleString(undefined,{maximumSignificantDigits:3}),unit:scale===1e6?'MJ':scale===1000?'kJ':'J'};
}
function text(j){const q=compact(j);return q.value+' '+q.unit;}
function exact(j){return valid(j)?(unit==='calories'?j/J_PER_KCAL:j).toLocaleString(undefined,{maximumFractionDigits:2})+' '+(unit==='calories'?'kcal':'J'):'Not available';}
function watts(jPerMinute){return valid(jPerMinute)?jPerMinute/60:null;}
function rate(jPerMinute){
 const calories=unit==='calories',format=n=>n.toLocaleString(undefined,{maximumFractionDigits:2});
 const primaryUnit=calories?'kcal/min':'W',equivalentUnit=calories?'W':'kcal/min';
 if(!valid(jPerMinute))return {value:'—',unit:primaryUnit,equivalent:null};
 return {value:format(jPerMinute/(calories?J_PER_KCAL:60)),unit:primaryUnit,
  equivalent:format(jPerMinute/(calories?60:J_PER_KCAL))+' '+equivalentUnit};
}
function set(next){if(!['calories','joules'].includes(next))return;unit=next;try{localStorage.setItem(KEY,unit);}catch(e){};sync();window.dispatchEvent(new Event('energy-units-change'));}
function sync(){document.querySelectorAll('[data-energy-unit]').forEach(el=>el.value=unit);}
window.EnergyUnits={compact,text,exact,watts,rate,set,get unit(){return unit;}};
function mount(){
 // Older running Hub processes still serve their in-memory panel template.
 if(location.pathname==='/panel'&&!document.querySelector('[data-energy-unit]')){
  const box=document.createElement('section');box.className='phone';box.innerHTML='<h2 id="energy-setting-title">Training display</h2><label>Energy units<select data-energy-unit style="display:block;width:100%;box-sizing:border-box;padding:12px;margin:10px 0;font:inherit;background:#0b0f14;color:#eef1f5;border:1px solid #2a3441;border-radius:10px"><option value="calories">Calories (kcal)</option><option value="joules">Joules &amp; watts (J / W)</option></select></label><p class="sub">Saved in this browser. Totals and history use your choice. Calories shows kcal/min; Joules &amp; watts shows W. The equivalent appears in smaller text. Nominal lifting work is mechanical work, not calories burned.</p><a href="/coach#fitness">View recorded training</a>';
  const before=document.getElementById('log');if(before)before.before(box);else document.body.append(box);
 }
 sync();document.querySelectorAll('[data-energy-unit]').forEach(el=>el.addEventListener('change',()=>set(el.value)));
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
window.addEventListener('storage',e=>{if(e.key===KEY){unit=e.newValue==='joules'?'joules':'calories';sync();window.dispatchEvent(new Event('energy-units-change'));}});
})();
