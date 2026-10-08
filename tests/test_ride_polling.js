// Slow/disconnected requests cannot overlap or leave a ride poll permanently stuck.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('web/ride-hub.html','utf8'),course=fs.readFileSync('web/course.html','utf8');
const delay=()=>new Promise(r=>setImmediate(r));
function timers(ctx){ctx.timers=[];ctx.setTimeout=f=>{ctx.timers.push(f);return ctx.timers.length};ctx.clearTimeout=()=>{};}
(async()=>{
 for(const [name,source] of [['shell',html],['scene',course]]){
  const ctx={AbortController,console,window:{dispatchEvent(){}},CustomEvent:function(){},rideStatus:null};timers(ctx);
  const nodes={};ctx.$=id=>nodes[id]??={};let pending=[],calls=0;
  ctx.fetch=(url,{signal})=>{calls++;return new Promise((resolve,reject)=>{pending.push(resolve);signal.addEventListener('abort',()=>reject(Error('timeout')));});};
  vm.createContext(ctx);
  const start=source.indexOf('let pollBusy=false;'),end=source.indexOf(name==='shell'?"fetch('/api/map/status')":'async function pollStatus',start);
  vm.runInContext(source.slice(start,end),ctx);
  if(name==='scene')ctx.pollStatus=async(signal)=>{const r=await ctx.fetch('/status',{signal});await r.json();};
  const first=ctx.poll();await ctx.poll();assert.equal(calls,1,name+' overlapped requests');
  ctx.timers.at(-1)();await first;await delay();
  const next=ctx.poll();assert.equal(calls,2,name+' failed to recover after timeout');
  pending.at(-1)({ok:true,json:async()=>({bike:true,workout:null,route:null,test:null})});await next;
  console.log('PASS '+name+' single in-flight request, timeout and reconnect');
 }
 const code=fs.readFileSync('web/livegraph.js','utf8').replace(/export /g,'')+'\nthis.LiveGraph=LiveGraph;';
 const ctx={AbortController,console,addEventListener(){},setInterval(){return 1},clearInterval(){},Date};timers(ctx);vm.createContext(ctx);vm.runInContext(code,ctx);
 let calls=0,pending=[];ctx.fetch=(u,{signal})=>{calls++;return new Promise((resolve,reject)=>{pending.push(resolve);signal.addEventListener('abort',()=>reject(Error('abort')));});};
 const graph=new ctx.LiveGraph({addEventListener(){}});graph.draw=()=>{};
 const first=graph.poll();await graph.poll();assert.equal(calls,1);ctx.timers.at(-1)();await first;
 const second=graph.poll();assert.equal(calls,2);graph.stop();await second;
 const third=graph.poll();pending.at(-1)({ok:true,json:async()=>({points:[[1,100,70]],now:2,ftp:180,band:[65,80]})});await third;
 assert.equal(graph.last,1);assert.equal(graph.pts.length,1);
 console.log('PASS live graph prevents overlap and recovers after timeout/stop');
})().catch(e=>{console.error(e);process.exitCode=1;});
