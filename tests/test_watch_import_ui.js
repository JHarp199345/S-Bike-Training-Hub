// A clock mismatch must be recoverable without leaving the manual linking UI.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const handlers={},elements={};
const el=id=>elements[id]||(elements[id]={innerHTML:'',open:false,addEventListener:(kind,fn)=>handlers[kind]=fn,showModal(){this.open=true;},close(){this.open=false;}});
const calls=[],ctx={window:{},document:{getElementById:el},fetch:async(url,options)=>{
 if(!options)return {ok:true,json:async()=>({activity:{id:'watch',sport:'bike',date:'2026-10-08',start:'2026-10-08T09:20:00',minutes:10},scheduled:[],recorded:[{id:'bike',source:'bridge',start:'2026-10-08T09:00:00',minutes:10}]})};
 const req=JSON.parse(options.body);calls.push(req);
 if(req.offset_seconds!==-1200)return {ok:false,json:async()=>({error:'The recordings do not overlap. Review their times and clock offset.'})};
 return {ok:true,json:async()=>({workout:{sport:'bike',date:'2026-10-08',minutes:10},note:'Sample linked record',alignment:{matched_hr_samples:600,timeline_samples:600},metric_sources:{power:'bridge',heart_rate:'watch'},measurements:{avg_power:180,avg_heart_rate:140}})};
}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('web/watch-import.js','utf8'),ctx);
(async()=>{
 await ctx.window.WatchImport.open(['watch']);
 const button={dataset:{recorded:'0'},hasAttribute:k=>k==='data-recorded'};
 await handlers.click({target:{closest:()=>button}});
 assert.match(el('watch-link-review').innerHTML,/do not overlap/);
 assert.match(el('watch-link-review').innerHTML,/id="watch-link-offset"/,'An error must retain the correction control');
 assert.doesNotMatch(el('watch-link-review').innerHTML,/data-save-link/,'Do not offer save after an invalid preview');
 handlers.change({target:{id:'watch-link-offset',value:'-1200'}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.match(el('watch-link-review').innerHTML,/Average power: 180.0 W/);
 assert.match(el('watch-link-review').innerHTML,/data-save-link/);
 assert.equal(calls.at(-1).offset_seconds,-1200);assert(calls.every(x=>x.save===false),'Preview and corrections must not save');
 console.log('PASS manual clock-mismatch correction, retry preview, source labels, and no save before valid review');
})().catch(e=>{console.error(e);process.exitCode=1;});
