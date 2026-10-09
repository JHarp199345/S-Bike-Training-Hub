// Recorded duration must stay distinct from a longer planned ride, including unknown and zero duration.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('web/coach.html','utf8');
const start=html.indexOf('function sessionDuration(s)'),end=html.indexOf('const activityReportCache',start);
const ctx={document:{addEventListener(){}},loadActivityReports:()=>{}};vm.createContext(ctx);vm.runInContext(html.slice(start,end),ctx);
const partial={sport:'ride',minutes:55,completion:{minutes:34}};
assert.equal(ctx.sessionDuration(partial),'34 min recorded · 55 min planned');
assert.equal(ctx.sessionState(partial),'Recorded');
assert.equal(ctx.sessionDuration({sport:'ride',minutes:30}),'30 min');
assert.equal(ctx.sessionDuration({sport:'ride',minutes:30,completion:{minutes:0}}),'0 min recorded · 30 min planned');
assert.equal(ctx.sessionDuration({sport:'ride',minutes:30,completion:{}}),'30 min planned · duration not recorded');
assert.equal(ctx.sessionState({...partial,skipped_id:'saved'}),'Cancelled');
assert.match(html,/\$\{sessionDuration\(s\)\} · \$\{sessionState\(s\)\}/,'Today and plan decks must use the actual duration summary');
assert.match(html,/\$\{sessionDuration\(cur\)\}/,'Plan overview must use the actual duration summary');
assert.match(html, /<details id="manual-preview-disclosure">/, 'New workout preview starts closed');
assert.match(html, /<details data-recorded-preview-disclosure>/, 'Recorded preview starts closed');
assert.match(html, /\$\('manual-preview-disclosure'\)\.open=false/, 'Opening the creator resets the preview to closed');
console.log('PASS: partial, unknown and zero recorded duration stay distinct from planned work');

// Imported actuals must remain visible even when the prescription is absent, without duplicates when matched.
ctx.esc=x=>String(x);ctx.COMPLETE_ICON='✓';ctx.WorkoutFormat={render:()=>''};
let a=html.indexOf('function unmatchedCalendarActivities(d)'),b=html.indexOf('function calendarMinutes',a);vm.runInContext(html.slice(a,b),ctx);
a=html.indexOf('function completedHtml(');b=html.indexOf('function swimOutlookHtml',a);vm.runInContext(html.slice(a,b),ctx);
a=html.indexOf('function workoutHeart(');b=html.indexOf('\nfunction ',a+10);ctx.day=ctx.day||{library_favorites:[]};vm.runInContext(html.slice(a,b),ctx);
a=html.indexOf('function recordedActivityHtml(d)');b=html.indexOf('function renderTodayWorkouts',a);vm.runInContext(html.slice(a,b),ctx);
const done={sport:'bike',minutes:34,km:10.36,load:{engine:28.4}};
assert.match(ctx.recordedActivityHtml({sessions:[],done:[done]}),/34 min recorded/);
assert.equal(ctx.recordedActivityHtml({sessions:[partial],done:[done]}),'');
console.log('PASS: imported activity stays visible without a plan and matched actuals are not duplicated');

// Recovery is a separate checked moon below the cancelled sport, not cancelled training.
a=html.indexOf('function calendarPartial(s)');b=html.indexOf('function calendarRecordedActivity(a)',a);vm.runInContext(html.slice(a,b),ctx);
ctx.sportIcon=s=>`icon-${s}`;ctx.calendarActivity=s=>ctx.sportIcon(s.sport);ctx.calendarMinutes=s=>s.completion?.minutes??s.minutes;
const cancelledLift={sport:'gym',minutes:20,skipped_id:'archived',name:'Strength'};
const markers=ctx.displaySessions({sessions:[cancelledLift],done:[],recovery_day:true});
assert.equal(markers.length,2);assert.equal(markers[0].sport,'gym');assert.equal(markers[1].sport,'rest');
assert.match(ctx.calendarMarker(markers[0]),/icon-gym.*cancel-cross/);
assert.match(ctx.calendarMarker(markers[1]),/recovery-record.*icon-rest.*calendar-status completed/);
assert.doesNotMatch(ctx.calendarMarker(markers[1]),/cancel-cross/);
assert.match(html,/\.calendar-activities>\.recovery-record\{grid-column:1\/-1/);
console.log('PASS cancelled lift icon and red X precede a separate checked recovery moon');


// Completed report opens and closes through the same button or its footer.
const reportButton={textContent:'View workout details',attrs:{},setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k];},focus(){this.focused=true;}},footer={};
const reportCard={hidden:true,innerHTML:'',querySelector(){return footer;}};ctx.$=id=>{assert.equal(id,'othercard');return reportCard;};
ctx.toggleReportedWorkout(reportButton,{sport:'swim',completion:{minutes:53}});
assert.equal(reportCard.hidden,false);assert.equal(reportButton.textContent,'Hide workout details');assert.equal(reportButton.attrs['aria-expanded'],'true');
ctx.toggleReportedWorkout(reportButton,{sport:'swim',completion:{minutes:53}});
assert.equal(reportCard.hidden,true);assert.equal(reportButton.textContent,'View workout details');
ctx.toggleReportedWorkout(reportButton,{sport:'swim',completion:{minutes:53}});footer.onclick();assert.equal(reportCard.hidden,true);assert.equal(reportButton.focused,true);
console.log('PASS completed report opens/collapses from the primary button and footer');

// Recorded corrections preview without saving, reject stale results, and approve only reviewed current input.
async function recordedPreviewTests(){
 ctx.clearTimeout=()=>{};ctx.setTimeout=()=>1;ctx.loadToday=async()=>{};
 ctx.SwimWorkout={render:r=>'parsed '+r.total_distance};
 const nodes={};for(const k of ['[data-recorded-text]','[data-recorded-unit]','[data-recorded-difference] input','[data-recorded-status]','[data-recorded-preview-body]','[data-recorded-difference]','[data-recorded-preview]','[data-recorded-preview-disclosure]'])nodes[k]={value:'',checked:false,disabled:false,innerHTML:'',textContent:'',style:{},scrollHeight:180,setAttribute(){}};
 nodes['[data-recorded-text]'].value='200 fs';nodes['[data-recorded-unit]'].value='yd';
 const box={dataset:{recordedSwim:'watch-swim'},isConnected:true,querySelector:s=>nodes[s]},calls=[];
 const response=(n,valid=true,diff=false)=>({ok:true,j:{recipe:{total_distance:n,valid,issues:valid?[]:['Clarify drill']},distance_difference:diff}});
 ctx.post=async(path,body)=>{calls.push({path,body});return response(200);};
 nodes['[data-recorded-preview-disclosure]'].open=false;
 await ctx.previewRecordedSwim(box);
 assert.equal(nodes['[data-recorded-preview-disclosure]'].open,false);
 nodes['[data-recorded-preview-disclosure]'].open=true;
 assert.equal(nodes['[data-recorded-preview-body]'].innerHTML,'parsed 200');
 assert.equal(nodes['[data-recorded-preview]'].disabled,false);
 assert(calls.every(x=>!x.body.save),'Preview must never mutate the imported workout');
 nodes['[data-recorded-text]'].value='500 fs';ctx.queueRecordedSwimPreview(box);
 assert.equal(nodes['[data-recorded-preview]'].disabled,true);
 const count=calls.length;await ctx.approveRecordedSwim(box);assert.equal(calls.length,count,'A pending or stale preview cannot save');
 const requests=[];ctx.post=(path,body)=>new Promise(resolve=>requests.push({body,resolve}));
 const older=ctx.previewRecordedSwim(box);nodes['[data-recorded-text]'].value='900 fs';const newer=ctx.previewRecordedSwim(box);
 requests[1].resolve(response(900));await newer;requests[0].resolve(response(500));await older;
 assert.equal(nodes['[data-recorded-preview-body]'].innerHTML,'parsed 900','A late response must not replace the current preview');
 assert.equal(nodes['[data-recorded-preview-disclosure]'].open,true,'Recalculating preserves an opened preview');
 ctx.post=async()=>response(900,false);await ctx.previewRecordedSwim(box);
 assert.equal(nodes['[data-recorded-preview]'].disabled,true);assert.match(nodes['[data-recorded-status]'].textContent,/Clarify drill/);
 ctx.post=async()=>response(900,true,true);await ctx.previewRecordedSwim(box);
 assert.equal(nodes['[data-recorded-difference]'].hidden,false);assert.equal(nodes['[data-recorded-preview]'].disabled,true);
 nodes['[data-recorded-difference] input'].checked=true;ctx.recordedSwimApproval(box);assert.equal(nodes['[data-recorded-preview]'].disabled,false);
 ctx.post=async(path,body)=>{calls.push({path,body});assert(nodes['[data-recorded-text]'].disabled);return {ok:true,j:{saved:true}};};
 await ctx.approveRecordedSwim(box);assert.equal(calls.at(-1).body.text,'900 fs');assert.equal(calls.at(-1).body.save,true);assert.equal(calls.at(-1).body.distance_difference_reviewed,true);
 assert.equal(nodes['[data-recorded-text]'].disabled,false);
 ctx.post=async()=>({ok:false,j:{error:'Preview unavailable'}});await ctx.previewRecordedSwim(box);
 assert.equal(nodes['[data-recorded-preview]'].disabled,true);assert.equal(nodes['[data-recorded-preview-body]'].innerHTML,'');
 assert.match(html,/\$\('manual-preview'\)\.hidden=false/,'Opening the disclosure must reveal the current preview even before Continue');
 console.log('PASS recorded correction live preview, no save on preview, stale-response protection, validation and distance review before approval');
}
recordedPreviewTests().catch(e=>{console.error(e);process.exitCode=1;});

// Detailed observations show legitimate zeros, hide absent measurements and keep load estimates labeled.
let metricsStart=html.indexOf('const activityReportCache'),metricsEnd=html.indexOf('function completedHtml(',metricsStart);
ctx.window={addEventListener(){},dispatchEvent(){}};ctx.Event=class{constructor(type){this.type=type;}};
ctx.document.readyState='loading';ctx.document.addEventListener=()=>{};ctx.document.querySelectorAll=()=>[];
vm.runInContext(fs.readFileSync('web/energy-units.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('web/recorded-strength.js','utf8'),ctx);ctx.RecordedStrength=ctx.window.RecordedStrength;
vm.runInContext(html.slice(metricsStart,metricsEnd),ctx);
let output=ctx.activityMetricsHtml({duration_seconds:1500,distance_m:5000,calories_kcal:0,avg_hr:140,max_hr:null,run:{pace_per_km_seconds:300,cadence_steps_min:160,steps:4000,drift_pct:0},load:{engine:30,impact:0,muscle:null}});
assert.match(output,/Watch calories/);assert.match(output,/>0 <small>kcal/);assert.match(output,/5:00/);assert.match(output,/Heart-rate drift/);assert.doesNotMatch(output,/Peak heart rate/);assert.doesNotMatch(output,/Muscle load · estimate/);
assert.match(output,/Estimated energy rate/,'Legacy watch record can show a converted rate');
output=ctx.activityMetricsHtml({energy_rate:{metabolic_power_w:1394.67,kcal_per_min:20,source:'motion',duration_basis:'Recorded timer'}});
assert.match(output,/<details><summary>Rate calculation<\/summary>/,'Calculation stays collapsed');
assert.match(output,/20 <small>kcal\/min/);assert.match(output,/wr-conversion.*1,394.67 W/);
ctx.window.EnergyUnits.set('joules');
output=ctx.activityMetricsHtml({energy_rate:{metabolic_power_w:1394.67,kcal_per_min:20,source:'motion',duration_basis:'Recorded timer'}});
assert.match(output,/1,394.67 <small>W/);assert.match(output,/wr-conversion.*20 kcal\/min/);assert.match(output,/Distance and gradient energy estimate/);
assert.match(output,/Not measured cycling power, a heart-rate zone or effort rating/);
assert.doesNotMatch(ctx.activityMetricsHtml({energy_rate:{metabolic_power_w:Infinity}}),/Estimated metabolic power/);
assert.doesNotMatch(ctx.activityMetricsHtml({calories_kcal:200,duration_seconds:0}),/Estimated metabolic power/);
const feedbackStart=html.indexOf('const workoutReportSnapshots'),feedbackEnd=html.indexOf("document.addEventListener('click',async e=>{const button=e.target.closest('[data-effort]')",feedbackStart);
vm.runInContext(html.slice(feedbackStart,feedbackEnd),ctx);
output=ctx.feedbackHtml('2026-10-06',null,null,'run-id','run');assert.match(output,/After-run report/);assert.match(output,/Overall session effort/);assert.match(output,/data-feedback-activity="run-id"/);assert.match(output,/data-effort="as_intended" disabled/,'Imported feedback must wait for backend capability verification');
console.log('PASS activity metric zeros, unknowns, units and imported report compatibility gate');
