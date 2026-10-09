const assert=require('node:assert/strict'),S=require('../web/swim-workout.js');
const recipe={total_distance:2000,unit:'yd',sets:[{stroke:'free',distance_m:1500,section:'main',distance:1500,unit:'yd',description:'FS <script>',work:'swim'},{stroke:'fly',distance_m:300,section:'warmup',distance:300,unit:'yd',description:'Butterfly drill',work:'drill'},{stroke:'back',distance_m:200,section:'cooldown',distance:200,unit:'yd',description:'Backstroke',work:'swim'}]};
const mix=S.strokeMix(recipe);assert.deepEqual(mix.parts.map(x=>x.percent),[75,15,10]);
const plan=S.planView(recipe);assert.match(plan,/75%/);assert.match(plan,/Warm-up/);assert.match(plan,/Main work/);assert.match(plan,/Cool-down/);assert.match(plan,/Time —/);assert.doesNotMatch(plan,/<textarea|<input|<script>/);assert.match(plan,/FS &lt;script&gt;/);
const response={distance_m:2000,duration_minutes:40,avg_hr:130,hr_time_bpm_min:5200};
const view=S.analysisView({recipe,recipe_basis:'Athlete-described',described_mix:mix,watch_mix:{parts:[{stroke:'drill',label:'Drill',distance_m:400,percent:100}],total_m:400},response,history:[{date:'2026-10-08',watch_mix:mix,response:{...response,avg_hr:null}},{date:'2026-10-09',current:true,watch_mix:mix,response}]});
assert.match(view,/Watch-classified/);assert.match(view,/Stroke distance across swims/);assert.match(view,/Time, volume and heart-rate response/);assert.match(view,/HR × time/);assert.match(view,/Reported effort —/);assert.doesNotMatch(view,/NaN|undefined|<textarea/);
console.log('PASS Plan sectioned write-up, distance donut, body illustration, separate watch sources and response history with missing values');

assert.match(plan,/Estimated Intensity Heat Map/);assert.match(plan,/data-swim-body/);assert.doesNotMatch(plan,/Muscle shading is/);
const history=[{date:'2026-10-01',watch_mix:mix,response},{date:'2026-10-08',watch_mix:mix,response},{date:'2026-10-08',watch_mix:mix,response},{date:'2026-10-09',watch_mix:mix,response}];
assert.equal(S.historyBuckets(history,5,'session').length,3);
const daily=S.historyBuckets(history,5,'day');assert.equal(daily.length,5);assert.equal(daily[3].count,2);assert.equal(daily[3].distance_m,4000);assert.equal(daily[0].count,0);assert.equal(S.historyBuckets(history,30).length,4);
assert.match(view,/30 days/);console.log('PASS date windows, multiple swims per day, zero-record days and reused map legend');
const H=require('../web/swim-history.js');
assert.equal(H.monthStart('2026-10-09',6),'2026-05-01');assert.equal(H.validRange('2026-09-01','2026-10-09','2026-10-09'),'');assert.ok(H.validRange('2026-02-30','2026-10-09','2026-10-09'));assert.ok(H.validRange('2025-01-01','2026-10-09','2026-10-09'));
const settings={start:'2026-05-01',end:'2026-10-09',period:'month',span:2,count:6,source:'watch',group:'day'};
assert.equal(H.periods(history,[],settings).length,6);assert.equal(H.periods(history,[],settings)[0].mix.count,4);assert.equal(H.periods(history,[],settings)[5].mix.count,0);
assert.equal(H.series(history,settings).find(r=>r.date==='2026-10-08').mix.count,2);
assert.equal(H.periods(history,[],{...settings,period:'quarter'})[0].label,'Q4 2026');
const phase=H.periods(history,[{label:'Base',start:'2026-10-01',end:'2026-10-09'}],{...settings,period:'phase'});assert.equal(phase[0].end,'2026-10-08');assert.equal(phase[0].mix.count,3);
assert.equal(H.aggregate([{response:{distance_m:100}}],'written').parts[0].stroke,'unknown');
assert.equal(H.periods(history,[],{...settings,start:'2025-11-01',count:12}).length,12);
const fs=require('fs'),coach=fs.readFileSync(require('path').join(__dirname,'../web/coach.html'),'utf8');assert.doesNotMatch(coach,/SwimWorkout.historyView\(report.swim_analysis.history,90\)/);assert.match(coach,/swim-history-dashboard/);
console.log('PASS full dashboard calendar/quarter/phase periods, date validation, daily aggregation, missing descriptions and Plan-only mini history');

// A stable stroke/work hierarchy is independent of recording and recipe order.
const planned={total_m:2286,parts:[{stroke:'fly',distance_m:274.32,percent:12},{stroke:'free',distance_m:2011.68,percent:88}],work_parts:[{stroke:'fly',work:'drill',distance_m:274.32},{stroke:'free',work:'swim',distance_m:1645.92},{stroke:'free',work:'drill',distance_m:365.76}]};
const sourceRows=[{date:'2026-10-08',response:{distance_m:914.4},watch_mix:{total_m:914.4,parts:[{stroke:'drill',distance_m:200},{stroke:'free',distance_m:714.4}]}},{date:'2026-10-09',current:true,response:{distance_m:2286},planned_mix:planned,watch_mix:{total_m:2286,parts:[{stroke:'free',distance_m:1463.04},{stroke:'drill',distance_m:777.24},{stroke:'unknown',distance_m:45.72}]}}];
const planBuckets=S.historyBuckets(sourceRows,90,'session','plan');assert.equal(planBuckets[0].distance_m,0);assert.equal(planBuckets[0].missing,1);assert.equal(planBuckets[1].parts.at(-1).stroke,'fly');assert.equal(planBuckets[1].parts.at(-1).work,'drill');assert.equal(planBuckets[1].parts.at(-1).distance_m/planBuckets[1].distance_m,0.12);
assert.deepEqual(S.historyBuckets(sourceRows)[0].parts.map(x=>x.stroke),['free','drill']);
const ratioView=S.historyView(sourceRows,90,'session','plan','ratio',true);assert.match(ratioView,/Butterfly · drill · 274 m · 12%/);assert.match(ratioView,/No written workout/);assert.equal((ratioView.match(/class="swim-share-bar" style="height:100%"/g)||[]).length,1);
const distanceView=S.historyView(sourceRows);assert.match(distanceView,/height:40%/);assert.match(distanceView,/height:100%/);assert.doesNotMatch(distanceView,/Butterfly · drill/);
const paired=S.historyView(sourceRows,90,'session','compare','ratio');assert.equal((paired.match(/class="swim-history-column(?: |")/g)||[]).length,4);assert.match(paired,/Planned swim history/);assert.match(paired,/Watch detection/);assert.match(paired,/Drill · unresolved/);
const incompleteDay=S.historyBuckets(sourceRows.map(r=>({...r,date:'2026-10-09'})),5,'day','plan').at(-1);assert.equal(incompleteDay.count,2);assert.equal(incompleteDay.missing,1);assert.equal(incompleteDay.distance_m,2286);
assert.ok(plan.indexOf('Estimated Intensity Heat Map')<plan.indexOf('Stroke distance</h4>'));
assert.deepEqual(H.aggregate(sourceRows,'watch').parts.map(x=>x.stroke),['free','drill','unknown']);
console.log('PASS saved-plan butterfly drills, percentage/distance scales, paired sources, missing-plan coverage and stable stacking');

// One Planned source accepts an existing recorded description, without another UI filter.
const describedRows=[{...sourceRows[0],described_mix:planned}];
const described=S.historyBuckets(describedRows,90,'session','plan')[0];assert.equal(described.distance_m,2286);assert.equal(described.basis,'Recorded workout breakdown');
const simple=S.historyView(describedRows,90,'session','plan','ratio',false);assert.match(simple,/Freestyle · 2012 m · 88%/);assert.doesNotMatch(simple,/class="swim-work-drill"/);assert.doesNotMatch(simple,/>Athlete-described</);assert.match(simple,/>Planned</);assert.match(simple,/Drill, kick &amp; pull detail|Drill, kick & pull detail/);
assert.deepEqual(S.displayParts(planned.work_parts,false).map(x=>[x.stroke,x.distance_m]),[['free',2011.68],['fly',274.32]]);
assert.equal((paired.match(/class="swim-history-source-panel"/g)||[]).length,2);assert.match(paired,/swim-history-compare/);assert.match(paired,/aria-label="Swim history source"/);
assert.equal(S.historyBuckets([{...sourceRows[1],described_mix:{total_m:100,parts:[{stroke:'back',distance_m:100}]}}],90,'session','plan')[0].distance_m,100);
console.log('PASS unified Planned descriptions, optional work detail, compact source selector and separate comparison panels');

assert.deepEqual(S.orderedParts([{stroke:'free',work:'drill'},{stroke:'free'},{stroke:'free',work:'kick'}]).map(x=>x.work||'swim'),['swim','drill','kick']);

// Absent strokes remain zero; thin guides never become distance-bearing segments.
const zeros=S.historyZeroGuides([{stroke:'free',distance_m:880},{stroke:'fly',work:'drill',distance_m:120}],1000);
assert.deepEqual(zeros.map(x=>x.stroke),['breast','back']);assert.ok(zeros.every(x=>x.distance_m===0&&x.position===88));assert.notEqual(zeros[0].offset,zeros[1].offset);
const vertical=S.historyView([{date:'2026-10-09',planned_mix:planned}],90,'session','plan','ratio');
assert.match(vertical,/swim-history-vertical/);assert.match(vertical,/swim-history-columns/);assert.match(vertical,/09\/09|10\/09/);assert.match(vertical,/swim-work-drill/);assert.match(vertical,/background-color:#fbbf24/);assert.match(vertical,/Breaststroke · 0 m · 0% · zero marker/);assert.match(vertical,/Backstroke · 0 m · 0% · zero marker/);
assert.match(vertical,/height:12%;background-color:#fbbf24/);assert.doesNotMatch(vertical,/height:0%;background-color:#34d399/);
assert.match(vertical,/totals and percentages are unchanged/);assert.match(vertical,/data-work-details="true"/);
const dailyVertical=S.historyView(history,5,'day','watch','ratio');assert.equal((dailyVertical.match(/class="swim-history-column(?: |")/g)||[]).length,5);assert.ok(dailyVertical.indexOf('10/05')<dailyVertical.indexOf('10/09'));assert.match(dailyVertical,/No swim recorded/);
const styles=fs.readFileSync(require('path').join(__dirname,'../web/swim-workout.css'),'utf8');assert.match(styles,/flex-direction:column-reverse/);assert.match(styles,/swim-history-plots[^}]*display:grid/);assert.match(styles,/gap:2px/);assert.doesNotMatch(styles,/swim-history-compare\{[^}]*grid-template-columns/);
console.log('PASS vertical history, stacked comparison, chronological dates, typed drill patterns and zero-only guides without added volume');

const detectedDrill=[{date:'2026-10-09',watch_mix:{total_m:300,parts:[{stroke:'fly',distance_m:300}],work_parts:[{stroke:'fly',work:'drill',distance_m:300}]}}];
assert.match(S.historyView(detectedDrill),/Butterfly · drill · 300 m · 100%/);
assert.match(S.historyView(sourceRows),/class="swim-work-drill"[^>]*background-color:#fb923c/);
