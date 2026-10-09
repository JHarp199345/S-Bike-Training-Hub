const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../web/coach.html'),'utf8'),a=html.indexOf('function calendarPartial(s)'),b=html.indexOf('function calendarRecordedActivity(a)',a);
const ctx={esc:String,sportIcon:s=>s,calendarMinutes:s=>s.completion?.minutes??s.minutes,calendarActivity:s=>s.sport};vm.createContext(ctx);vm.runInContext(html.slice(a,b),ctx);
const swim={sport:'swim',name:'Swim',minutes:60,swim_recipe:{total_distance_m:2286},completion:{minutes:53,distance_m:2286}};
assert.equal(ctx.calendarPartial(swim),false);assert.match(ctx.calendarStatus(swim),/calendar-status completed/);assert.doesNotMatch(ctx.calendarStatus(swim),/status-fill/);
assert.equal(ctx.calendarPartial({...swim,completion:{minutes:53,km:2.29}}),false);
assert.equal(ctx.calendarPartial({...swim,completion:{minutes:53,distance_m:2282}}),false); // small unit rounding tolerance
const short={...swim,completion:{minutes:53,distance_m:1828.8}};
assert.equal(ctx.calendarPartial(short),true);assert.match(ctx.calendarStatus(short),/Partially completed: 1829 of 2286 m/);assert.match(ctx.calendarMarker(short),/2286 m planned/);
assert.equal(ctx.calendarPartial({...swim,completion:{minutes:53}}),false); // unknown distance cannot be judged by an estimated duration
assert.equal(ctx.calendarPartial({...swim,completion:{minutes:70,distance_m:1800}}),true);
assert.equal(ctx.calendarPartial({...short,completed:true}),false);
assert.equal(ctx.calendarPartial({sport:'ride',minutes:60,completion:{minutes:53}}),true);
assert.equal(ctx.calendarPartial({sport:'swim',minutes:60,completion:{minutes:53}}),true); // timed swim has a duration target
assert.match(ctx.calendarStatus({...swim,skipped_id:'cancelled'}),/calendar-status skipped/);
console.log('PASS distance-prescribed swim completion, genuinely short swims, unknown distance and existing timed-session statuses');
