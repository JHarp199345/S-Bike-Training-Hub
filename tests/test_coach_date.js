const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {localDate,phaseState,createController}=require('../web/coach-date.js');
process.env.TZ='America/Los_Angeles';
assert.equal(localDate(new Date('2026-10-10T06:59:59Z')),'2026-10-09');
assert.equal(localDate(new Date('2026-10-10T07:00:00Z')),'2026-10-10');
assert.equal(localDate(new Date('2027-01-01T08:00:00Z')),'2027-01-01');
assert.equal(localDate(new Date('2026-11-01T08:30:00Z')),'2026-11-01');
assert.equal(localDate(new Date('2026-11-01T09:30:00Z')),'2026-11-01');
const old={start:'2026-10-02',end:'2026-10-05'},current={start:'2026-10-05',end:'2026-10-12'};
assert.equal(phaseState(old,'2026-10-10'),'past');
assert.equal(phaseState(current,'2026-10-10'),'current');
assert.equal(phaseState(current,'2026-10-05'),'current');
assert.equal(phaseState(current,'2026-10-12'),'past');
assert.equal(phaseState(current,'2026-10-04'),'upcoming');

async function run(){
 let loaded='2026-10-09',date=new Date(2026,9,10),busy=true,loads=0,pending=0,failures=0;
 let release;
 const controller=createController({loadedDate:()=>loaded,now:()=>date,busy:()=>busy,pending:()=>pending++,failed:()=>failures++,refresh:async target=>{loads++;await new Promise(r=>release=r);loaded=target;return true;}});
 assert.equal(await controller.check(),false);assert.equal(pending,1);assert.equal(loads,0);
 busy=false;const first=controller.check(),second=controller.check();assert.equal(first,second);
 await Promise.resolve();release();assert.equal(await first,true);assert.equal(loaded,'2026-10-10');
 await controller.check();assert.equal(loads,1);
 date=new Date(2026,9,12);const monday=controller.check();await Promise.resolve();release();await monday;
 assert.equal(loaded,'2026-10-12');assert.equal(loads,2);
 let attempts=0;
 const retry=createController({loadedDate:()=>loaded,now:()=>new Date(2026,9,13),failed:()=>failures++,refresh:async target=>{if(++attempts===1)throw Error('offline');loaded=target;return true;}});
 assert.equal(await retry.check(),false);assert.equal(loaded,'2026-10-12');assert.equal(failures,1);
 assert.equal(await retry.check(),true);assert.equal(loaded,'2026-10-13');

 // Exercise the actual loader's fetch/apply boundary, including edits made while fetching.
 const html=fs.readFileSync('web/coach.html','utf8');
 const loader=html.slice(html.indexOf('async function loadToday('),html.indexOf('  const c=r.checkin||{}'))+'return true;}';
 let dirty=false,reset=0,notice=0,requests=[],respond,clock='2026-10-10';
 const context={CoachDate:{localDate:()=>clock},todayRequest:0,day:{date:'2026-10-09'},ftp:0,workouts:[],fullWorkouts:[],
  dateRolloverBusy:()=>dirty,dateRolloverPending:()=>notice++,resetDailyInputs:()=>reset++,refreshFitnessDashboard:()=>{},
  activityReportCache:{clear(){}},$:()=>({hidden:false}),fetch:(url,options)=>{requests.push({url,options});if(url==='/api/workouts')return Promise.resolve({json:async()=>({workouts:[]})});return new Promise(r=>respond=()=>r({ok:true,json:async()=>({date:clock,ftp:180,workouts:[]})}));}};
 vm.createContext(context);vm.runInContext(loader,context);
 dirty=true;assert.equal(await context.loadToday(),false);assert.equal(requests.length,0);assert.equal(context.day.date,'2026-10-09');
 dirty=false;const loading=context.loadToday();dirty=true;respond();await loading;
 assert.equal(context.day.date,'2026-10-09');assert.equal(reset,0);assert.equal(notice,2);
 dirty=false;const safe=context.loadToday();respond();assert.equal(await safe,true);
 assert.equal(context.day.date,'2026-10-10');assert.equal(reset,1);
 assert.equal(requests[0].url,'/api/coach/today?date=2026-10-10');assert.equal(requests[0].options.cache,'no-store');
 // A response that straddles midnight must not set Today back to the prior date.
 const stale=context.loadToday();clock='2026-10-11';respond();assert.equal(await stale,false);assert.equal(context.day.date,'2026-10-10');

 // Daily form readings from yesterday must not become answers for the new day.
 const resetCode=html.slice(html.indexOf('function resetDailyInputs('),html.indexOf('\nconst colour='));
 const rating={tagName:'INPUT',id:'legs',value:'9',defaultValue:'3'},hr={tagName:'INPUT',id:'hr90',value:'140',defaultValue:''};
 const nodes={feel:{querySelectorAll:()=>[rating,hr]},legsv:{textContent:'9'},trun:{hidden:false},ask90:{hidden:false},ask120:{hidden:false},askrec:{hidden:false},cimsg:{textContent:'old'},cisavestatus:{textContent:'old'}};
 const ctx={$:id=>nodes[id],editing:false,gut:'no',shoulderTouched:true,checkinRequest:'old',checkinInitialized:true,plan:{},document:{querySelectorAll:()=>[]},setPain:()=>{}};
 vm.createContext(ctx);vm.runInContext(resetCode,ctx);ctx.resetDailyInputs();
 assert.equal(rating.value,'3');assert.equal(nodes.legsv.textContent,'3');assert.equal(hr.value,'');assert.equal(ctx.gut,null);assert.equal(ctx.shoulderTouched,false);assert.equal(ctx.checkinRequest,null);assert.equal(nodes.trun.hidden,true);
 console.log('PASS local midnight/DST/year dates, phase boundaries, Monday rollover, draft preservation, concurrent refresh, retry, in-flight edit protection and fresh daily answers');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
