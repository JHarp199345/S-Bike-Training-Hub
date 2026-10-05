// Verify refreshes render new reports without writing athlete data.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/../web/dashboard.html','utf8');
const source=html.slice(html.indexOf('let dashboardLoading=false;'),html.indexOf('</script><script>(()=>'));
const elements=new Map(),events={},parent={};let requests=[],weekly='2026-10-04',verdict='easy',fail=false;
const element=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',hidden:false,before(e){elements.set(e.id,e);},setAttribute(){}});return elements.get(id);};
const context={console,Date,Math,Object,Promise,parent,location:{origin:'http://localhost'},document:{hidden:false,createElement:()=>({setAttribute(){}})},$:element,esc:String,ring:()=>'',pie(){},lines(){},bars:()=>'',zone:()=>'',SPORTC:{},setInterval(){},addEventListener:(type,handler)=>events[type]=handler,
 fetch:async(url,options)=>{requests.push({url,options});if(fail)throw Error('offline');return {ok:true,json:async()=>url==='/api/load'?{readiness:{verdict,limited_by:['shoulders 6/10']}}:url==='/api/coach/today'?{date:'2026-10-05'}:url==='/api/coach/weekly'?{answered:{[weekly]:{weekeffort:4}}}:{}};}};
vm.createContext(context);vm.runInContext(source,context);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 await settle();assert.match(element('dashboard-updated').textContent,/2026-10-04/);assert.match(element('verdicts').innerHTML,/shoulders 6\/10/);assert(requests.every(r=>r.options.cache==='no-store'));
 const n=requests.length;events.message({origin:'https://unrelated',source:parent,data:{type:'hub-data-updated'}});await settle();assert.equal(requests.length,n);
 weekly='2026-10-11';verdict='go';events.message({origin:context.location.origin,source:parent,data:{type:'hub-data-updated'}});await settle();assert.match(element('dashboard-updated').textContent,/2026-10-11/);assert.match(element('verdicts').innerHTML,/class="lv go"/);
 const previous=element('verdicts').innerHTML;fail=true;events.visibilitychange();await settle();assert.equal(element('verdicts').innerHTML,previous);assert.match(element('loading').textContent,/previous view is retained/);
 fail=false;events.visibilitychange();await settle();assert.equal(element('loading').hidden,true);
 console.log('PASS: dashboard refresh uses fresh data, shows weekly source, rejects unrelated messages, preserves readings on failure and retries');
})().catch(e=>{console.error(e);process.exitCode=1;});
