const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('web/coach.html','utf8'),start=html.indexOf('function toggleReportedWorkout('),end=html.indexOf('function recordedSwimEditor(',start);
const nodes=Object.fromEntries(['othercard','othertitle','timedcard','timedtitle'].map(k=>[k,{hidden:true,innerHTML:'',querySelector:()=>({})}]));
let loads=0;
const ctx={$:k=>nodes[k],WorkoutFormat:{render:s=>'breakdown:'+s.sport},SwimWorkout:{render:()=>'<swim-recipe>',planView:()=>'<swim-analysis>'},completedHtml:()=>'<watch-metrics>',loadActivityReports:()=>loads++,loadPlanned:()=>loads++};
vm.createContext(ctx);vm.runInContext(html.slice(start,end),ctx);
const button=()=>({attributes:{},textContent:'',getAttribute(k){return this.attributes[k]||null},setAttribute(k,v){this.attributes[k]=v},focus(){}});
for(const sport of ['swim','run','gym','walk','other','ride']){
 const b=button();ctx.togglePlanWorkout(b,{date:'today'},{sport});
 assert.equal(b.attributes['aria-expanded'],'true');assert.equal(nodes[sport==='ride'?'timedcard':'othercard'].hidden,false);
 ctx.togglePlanWorkout(b,{date:'today'},{sport});assert.equal(b.attributes['aria-expanded'],'false');
 assert.equal(nodes.othercard.hidden,true);assert.equal(nodes.timedcard.hidden,true);
}
const b=button();ctx.togglePlanWorkout(b,{date:'today'},{sport:'swim',completion:{activity_id:'swim'},swim_recipe:{}});
assert.match(nodes.othercard.innerHTML,/<watch-metrics>/);
ctx.togglePlanWorkout(b,{date:'today'},{sport:'swim',completion:{activity_id:'swim'},swim_recipe:{}});assert.equal(nodes.othercard.hidden,true);
assert.doesNotMatch(html.slice(html.indexOf("if(cur){$('planworkoutdetails').onclick="),html.indexOf("if($('planworkoutedit'))")),/showTab\('today'\)/);
console.log('PASS Plan details stay local and toggle open/closed for every sport, including completed swim breakdown');
