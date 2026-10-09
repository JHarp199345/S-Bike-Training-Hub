const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const handlers=[],ctx={document:{addEventListener:(name,fn)=>{if(name==='click')handlers.push(fn);}}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('web/workout-format.js','utf8'),ctx);vm.runInContext(fs.readFileSync('web/recorded-strength.js','utf8'),ctx);vm.runInContext(fs.readFileSync('web/swim-workout.js','utf8'),ctx);
const lift={name:'Row',sets:2,reps:10,weight:50,unit:'lb',section:'main',set_details:[{name:'Row',reps:10,weight:50,unit:'lb',rpe:5},{name:'Row',reps:10,weight:50,unit:'lb',rpe:6}]};
const row=(date,rpe,weight=50)=>({date,activity_id:date,external_volume_lb:weight*20,completion:{minutes:30,avg_hr:120,calories_kcal:250},feedback:{rpe,note:'<script>bad</script>'},strength_logs:[{points_total:20,lifts:[{...lift,weight}]}]});
const item={session:{name:'Routine'},responses:[row('2026-10-01',7),row('2026-10-08',6)]},html=ctx.RecordedStrength.historyHtml(item);
assert(html.indexOf('Workout trends')<html.indexOf('data-rs-deck'));
assert(html.indexOf('2026-10-08 · most recent')<html.indexOf('2026-10-01'));
assert.match(html,/data-rs-card="1" hidden/);assert.match(html,/1 of 2/);assert.match(html,/matching sets/);assert.match(html,/&lt;script&gt;/);assert.match(html,/data-rs-performance-body hidden/);
assert.match(ctx.RecordedStrength.historyHtml({...item,responses:[item.responses[0]]}),/One recorded performance/);
assert.match(ctx.RecordedStrength.historyHtml({...item,responses:[]}),/No completed performances/);
assert.equal(ctx.RecordedStrength.performanceMetrics(row('date',6)).energyRate,250/30);
assert.equal(ctx.RecordedStrength.performanceMetrics({}).hr,null);
const cards=[{hidden:false},{hidden:true}],newer={disabled:true},older={disabled:false},counter={};const deck={dataset:{rsIndex:'0'},querySelectorAll:()=>cards,querySelector:s=>s.includes('counter')?counter:s.includes('"-1"')?newer:older};
const step={dataset:{rsStep:'1'},closest:()=>deck};
handlers[0]({target:{closest:s=>s==='[data-rs-step]'?step:null}});
assert.deepEqual(cards.map(c=>c.hidden),[true,false]);assert.equal(deck.dataset.rsIndex,'1');assert.equal(older.disabled,true);assert.equal(newer.disabled,false);
step.dataset.rsStep='-1';handlers[0]({target:{closest:s=>s==='[data-rs-step]'?step:null}});assert.deepEqual(cards.map(c=>c.hidden),[false,true]);assert.equal(newer.disabled,true);
const host={hidden:false,dataset:{loaded:'yes'}},attrs={},button={parentElement:{querySelector:()=>host},setAttribute:(k,v)=>attrs[k]=v};
handlers[0]({target:{closest:s=>s==='[data-rs-performance]'?button:null}});assert(host.hidden);assert.equal(attrs['aria-expanded'],'false');
handlers[0]({target:{closest:s=>s==='[data-rs-performance]'?button:null}});assert(!host.hidden);assert.equal(attrs['aria-expanded'],'true');
const groups=[{section:'warmup',sets:[{stroke:'freestyle'}]},{section:'main',sets:[{stroke:'butterfly'}]},{section:'cooldown',sets:[{stroke:'freestyle'}]}];
for(const gs of [groups,groups.map(g=>({...g,sets:[{stroke:'freestyle'}]}))]){const picks=ctx.SwimWorkout.chooseArt(gs);for(let i=1;i<picks.length;i++){assert.notEqual(picks[i].file,picks[i-1].file);assert.notEqual(picks[i].similarity_group,picks[i-1].similarity_group);}}
assert.equal(ctx.WorkoutArt.chooseAdjacent([{id:'a',file:'a',similarity_group:'same'}],[{file:'b',similarity_group:'same'}]),null,'Do not silently fall back to an adjacent similar image');
console.log('PASS history chronology, fixed trends, record switching, repeated metrics toggle, missing data, and adjacent image-family exclusion');

const coachHtml=fs.readFileSync('web/coach.html','utf8');assert.match(coachHtml,/data-library-saved="true"[^>]+>♥/);assert.doesNotMatch(coachHtml,/data-library-heart="\$\{w.id\}"/);

// Imported activities must offer the same heart as manually scheduled workouts.
const heartSource=coachHtml.slice(coachHtml.indexOf('function workoutHeart('),coachHtml.indexOf('function workoutHeart(')+2100);
const heartFn=heartSource.slice(0,heartSource.indexOf('\n}')+2);
const heartCtx={day:{library_favorites:['kept']},esc:x=>String(x??'')};vm.createContext(heartCtx);vm.runInContext(heartFn,heartCtx);
for(const sport of ['swim','ride','run','other']){
 const heart=heartCtx.workoutHeart('2026-10-08',null,{sport,name:'Recorded workout',completion:{activity_id:'source',workout_details:{library_id:'kept'}}});
 assert.match(heart,/data-activity-id="source"/);assert.match(heart,/aria-pressed="true"/);assert.match(heart,/>♥/);
 assert.match(heartCtx.workoutHeart('2026-10-08',0,{sport,name:'Plan'}),/data-index="0"/);
}
assert.equal(heartCtx.workoutHeart('2026-10-08',null,{sport:'gym',completion:{activity_id:'source'}}),'','Strength keeps its existing single heading heart');
assert.match(coachHtml,/workoutHeart\(d.date,null,session\)/,'Unscheduled imported workouts need a heart too');
console.log('PASS library hearts for planned and imported swim, cycling, running, and other workouts');

(async()=>{
 const start=coachHtml.indexOf('async function saveWorkoutHeart('),end=coachHtml.indexOf("document.addEventListener('click',async e=>{const b=e.target.closest('[data-workout-heart]');",start);
 const calls=[],attrs={},button={dataset:{activityId:'recorded-swim',libraryId:'',favorite:'false'},setAttribute:(k,v)=>attrs[k]=v};
 const saved={id:'saved-swim',favorite:true};
 const saveCtx={day:{library_favorites:[],week:[{done:[{activity_id:'recorded-swim',workout_details:{fields:{main:'400 free'}}}]}]},document:{querySelectorAll:()=>[button]},activityReportCache:new Map(),post:async(path,body)=>{calls.push({path,body});return {ok:true,j:{workout:saved}};},actionNotice:message=>{throw Error(message);}};
 vm.createContext(saveCtx);vm.runInContext(coachHtml.slice(start,end),saveCtx);
 await saveCtx.saveWorkoutHeart(button);
 assert.equal(calls[0].path,'/api/coach/workout-library/completed');assert.equal(calls[0].body.activity_id,'recorded-swim');assert.equal(calls[0].body.save,true);
 assert.equal(button.textContent,'♥');assert.equal(button.dataset.favorite,'true');assert.equal(attrs['aria-pressed'],'true');assert.equal(button.disabled,false);
 assert.equal(saveCtx.day.week[0].done[0].workout_details.fields.main,'400 free');assert.equal(saveCtx.day.week[0].done[0].workout_details.library_id,'saved-swim');
 vm.runInContext(heartFn,saveCtx);saveCtx.esc=x=>String(x??'');
 assert.match(saveCtx.workoutHeart('2026-10-08',null,{sport:'swim',name:'Swim',completion:saveCtx.day.week[0].done[0]}),/>♥/,'Re-render keeps the saved heart red');
 console.log('PASS recorded swim heart saves the source activity and retains red state on re-render');
})().catch(e=>{console.error(e);process.exitCode=1;});

const swimHistory=ctx.RecordedStrength.historyHtml({session:{sport:'swim',name:'Swim'},responses:[{date:'2026-10-09',completion:{sport:'swim',minutes:40,swim_analysis:{response:{distance_m:1500,avg_hr:130,hr_time_bpm_min:5200,pace_per_100m_seconds:160}}}}]});
assert.match(swimHistory,/Recorded distance/);assert.match(swimHistory,/HR × time/);assert.doesNotMatch(swimHistory,/External weight moved|Strength load estimate|Mean reported set effort/);
