// Verify dimensions and a persistent unit change without modifying the recorded energy.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(store=new Map()){
 const events={},ctx={Event:class{constructor(type){this.type=type;}},document:{readyState:'loading',addEventListener(){},querySelectorAll:()=>[],getElementById:()=>null},localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)}};
 ctx.window={addEventListener:(name,fn)=>events[name]=fn,dispatchEvent:e=>events[e.type]?.(e)};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('web/energy-units.js','utf8'),ctx);ctx.EnergyUnits=ctx.window.EnergyUnits;
 let code=fs.readFileSync('web/work-rate.js','utf8').replace('window.WorkRate={read,','window.WorkRate={energyCell,quantity,read,');
 vm.runInContext(code,ctx);return {ctx,store,events};
}
const {ctx,store,events}=setup(),units=ctx.EnergyUnits,work=ctx.window.WorkRate;
assert.equal(units.unit,'calories');assert.equal(units.text(4184),'1 kcal');assert.equal(units.watts(60),1);assert.equal(units.watts(null),null);
const activity={energy_j:200*4184,energy_power_w:200*4184/600,minutes:10,energy_source:'motion'};
const before=JSON.stringify(activity),render=work.energyCell(activity);
assert.match(render,/200 kcal/);assert.match(render,/<b>20 kcal\/min<\/b>/);assert.match(render,/wr-conversion.*1,394.67 W/);assert.match(render,/Estimated energy rate/);
assert.doesNotMatch(work.energyCell({energy_j:4184,minutes:0}),/Estimated metabolic power/);
assert.match(work.quantity(4184,'day'),/kcal/);assert.match(work.quantity(4184,'min'),/<strong>1<\/strong><span class="wr-unit">kcal\/min/);assert.match(work.rateText(4184),/^1 kcal\/min/);
units.set('joules');assert.equal(units.text(4184),'4.18 kJ');assert.match(work.energyCell(activity),/837 kJ/);assert.match(work.energyCell(activity),/<b>1,394.67 W<\/b>/);assert.match(work.energyCell(activity),/wr-conversion.*20 kcal\/min/);assert.match(work.quantity(4184,'min'),/<strong>69.73<\/strong><span class="wr-unit">W/);assert.match(work.rateText(4184),/^69.73 W/);
assert.equal(JSON.stringify(activity),before);assert.equal(store.get('hub-energy-unit'),'joules');assert.equal(setup(store).ctx.EnergyUnits.unit,'joules');
events.storage({key:'hub-energy-unit',newValue:'calories'});assert.equal(units.unit,'calories');
assert.equal(units.rate(0).value,'0');assert.equal(units.rate(0).equivalent,'0 W');assert.equal(units.rate(null).equivalent,null);assert.equal(units.rate(Infinity).equivalent,null);assert.equal(units.rate(-1).equivalent,null);assert.equal(units.compact(NaN).value,'—');assert.equal(units.compact(-1).value,'—');units.set('invalid');assert.equal(units.unit,'calories');
console.log('PASS energy units, watts conversion, readable equivalent, persistence, cross-tab updates and unchanged records');
