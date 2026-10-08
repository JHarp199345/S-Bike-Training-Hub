// The shared dashboard must refresh fresh sources and retain readings if a fetch fails.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const js=fs.readFileSync(__dirname+'/../web/fitness-workspace.js','utf8');
const source=js.slice(js.indexOf('async function refresh()'),js.indexOf('window.FitnessWorkspace='));
const elements=new Map(),events=[];let requests=[],revision=1,fail=false,readCalls=0;
const element=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:''});return elements.get(id);};
const context={console,Date,Promise,loading:null,document:{getElementById:element},window:{dispatchEvent:e=>events.push(e)},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},
 WorkRate:{read:async()=>{readCalls++;return {revision};},card:(el,d)=>el.innerHTML='work '+d.revision},
 lifting:(el,d)=>el.innerHTML='lifting '+d.revision,body:(el,d)=>el.innerHTML='body '+d.revision,calibration:(el,L,T)=>el.innerHTML='test '+T.revision,
 fetch:async(url,options)=>{requests.push({url,options});if(fail)throw Error('offline');return {ok:true,json:async()=>({revision})};}};
vm.createContext(context);vm.runInContext(source,context);
(async()=>{
 const a=context.refresh(),b=context.refresh();await Promise.all([a,b]);assert.equal(readCalls,1);assert.equal(requests.length,3);assert(requests.every(r=>r.options.cache==='no-store'));assert.equal(element('work-rate-card').innerHTML,'work 1');assert.equal(events[0].type,'fitness-readings');
 revision=2;await context.refresh();for(const id of ['work-rate-card','lifting-records-content','body-workload'])assert.match(element(id).innerHTML,/2/);assert.equal(element('calibration-extra').innerHTML,'test 2');
 fail=true;await context.refresh();assert.equal(element('work-rate-card').innerHTML,'work 2');assert.match(element('fitness-status').textContent,/Previous readings are retained/);
 fail=false;revision=3;await context.refresh();assert.equal(element('body-workload').innerHTML,'body 3');assert.match(element('fitness-status').textContent,/Updated/);
 console.log('PASS: shared dashboard refresh coalesces reads, uses fresh APIs, updates all homes, retains readings on failure and retries');
})().catch(e=>{console.error(e);process.exitCode=1;});
