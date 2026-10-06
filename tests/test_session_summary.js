// Recorded duration must stay distinct from a longer planned ride, including unknown and zero duration.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('web/coach.html','utf8');
const start=html.indexOf('function sessionDuration(s)'),end=html.indexOf('function completedHtml(s)',start);
const ctx={};vm.createContext(ctx);vm.runInContext(html.slice(start,end),ctx);
const partial={sport:'ride',minutes:55,completion:{minutes:34}};
assert.equal(ctx.sessionDuration(partial),'34 min recorded · 55 min planned');
assert.equal(ctx.sessionState(partial),'Recorded');
assert.equal(ctx.sessionDuration({sport:'ride',minutes:30}),'30 min');
assert.equal(ctx.sessionDuration({sport:'ride',minutes:30,completion:{minutes:0}}),'0 min recorded · 30 min planned');
assert.equal(ctx.sessionDuration({sport:'ride',minutes:30,completion:{}}),'30 min planned · duration not recorded');
assert.equal(ctx.sessionState({...partial,skipped_id:'saved'}),'Skipped');
assert.match(html,/\$\{sessionDuration\(s\)\} · \$\{sessionState\(s\)\}/,'Today and plan decks must use the actual duration summary');
assert.match(html,/\$\{sessionDuration\(cur\)\}/,'Plan overview must use the actual duration summary');
console.log('PASS: partial, unknown and zero recorded duration stay distinct from planned work');

// Imported actuals must remain visible even when the prescription is absent, without duplicates when matched.
ctx.esc=x=>String(x);ctx.COMPLETE_ICON='✓';ctx.WorkoutFormat={render:()=>''};
let a=html.indexOf('function unmatchedCalendarActivities(d)'),b=html.indexOf('function calendarMinutes',a);vm.runInContext(html.slice(a,b),ctx);
a=html.indexOf('function completedHtml(s)');b=html.indexOf('function swimOutlookHtml',a);vm.runInContext(html.slice(a,b),ctx);
a=html.indexOf('function recordedActivityHtml(d)');b=html.indexOf('function renderTodayWorkouts',a);vm.runInContext(html.slice(a,b),ctx);
const done={sport:'bike',minutes:34,km:10.36,load:{engine:28.4}};
assert.match(ctx.recordedActivityHtml({sessions:[],done:[done]}),/34 min recorded/);
assert.equal(ctx.recordedActivityHtml({sessions:[partial],done:[done]}),'');
console.log('PASS: imported activity stays visible without a plan and matched actuals are not duplicated');
