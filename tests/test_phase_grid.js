const assert=require('assert');
const G=require('../web/phase-grid.js');

// 2026-10-11 is a Sunday: the first row starts Monday 10-05 with six days outside the phase.
const p={label:'Development 1',start:'2026-10-11',end:'2026-10-31'};
const rows=G.rows(p);
assert.strictEqual(rows.length,4);
assert.strictEqual(rows[0][0].date,'2026-10-05');
assert.deepStrictEqual(rows[0].map(c=>c.inside),[false,false,false,false,false,false,true]);
assert.strictEqual(rows.flat().filter(c=>c.inside).length,20);
assert.strictEqual(G.slots(p,'2026-10-12'),null,'a phase nobody has planned is automatic');
assert.ok(!G.manual(p));

// Scattered days get a type added; a fourth session on a full day is refused.
assert.deepStrictEqual(G.addType(p,['2026-10-12','2026-10-14','2026-10-16'],'gym'),{added:3,full:0});
assert.ok(G.manual(p));
assert.deepStrictEqual(G.slots(p,'2026-10-12').map(s=>s.sport),['gym']);
assert.deepStrictEqual(G.slots(p,'2026-10-13'),[],'blank days are rest once planned by hand');
assert.strictEqual(p.weekly_pattern.length,7);
G.addType(p,['2026-10-12'],'swim');G.addType(p,['2026-10-12'],'ride');
assert.deepStrictEqual(G.addType(p,['2026-10-12'],'run'),{added:0,full:1});
assert.strictEqual(G.addType(p,['2026-11-05'],'run').added,0,'days outside the phase are ignored');

// Copy a week (Mon 10-12 … Sun 10-18) and fill it forward: it repeats on the same weekdays.
const week=G.dates(p).slice(1,8);
const clip=G.copy(p,week);
assert.strictEqual(clip.period,7);
const fill=G.fillTargets(p,week);
assert.strictEqual(fill[0].date,'2026-10-19');
assert.strictEqual(fill.at(-1).date,'2026-10-30','fill stops at the end of the phase');
assert.strictEqual(G.conflicts(p,fill).length,0);
G.apply(p,fill);
assert.deepStrictEqual(G.slots(p,'2026-10-26').map(s=>s.sport),['gym','swim','ride']);
assert.deepStrictEqual(G.slots(p,'2026-10-21').map(s=>s.sport),['gym']);

// Scattered days copy in whole weeks, so Monday stays Monday.
assert.strictEqual(G.copy(p,['2026-10-12','2026-10-16']).period,7);

// Pasting over planned days: conflicts are found; "empty only" leaves them, "replace" overwrites.
const rest={offset:0,slots:[]},bike={offset:0,slots:[{sport:'ride',purpose:'x'}]};
const over=G.targets(p,{period:7,cells:[bike]},'2026-10-14');
assert.strictEqual(G.conflicts(p,over).length,1);
assert.strictEqual(G.apply(p,over,'empty'),0);
assert.deepStrictEqual(G.slots(p,'2026-10-14').map(s=>s.sport),['gym']);
G.apply(p,over,'replace');
assert.deepStrictEqual(G.slots(p,'2026-10-14').map(s=>s.sport),['ride']);
G.apply(p,G.targets(p,{period:7,cells:[rest]},'2026-10-14'));
assert.deepStrictEqual(G.slots(p,'2026-10-14'),[],'pasting an empty day clears it');
assert.strictEqual(G.clear(p,['2026-10-12','2026-10-13']),1);

// A weekly template isn't on the calendar, so it shows nothing; hand planning keeps placements and empties the rest.
const t={label:'Base',start:'2026-11-02',end:'2026-11-16',weekly_pattern:[[{sport:'swim',purpose:'a'}],[{sport:'rest',purpose:'r'}],{sport:'ride',purpose:'b'},[],[],[],[]],date_placements:{'2026-11-09':[{sport:'swim',purpose:'a'}]}};
assert.deepStrictEqual(G.slots(t,'2026-11-02'),[]);
G.makeManual(t);
assert.deepStrictEqual(G.slots(t,'2026-11-09').map(s=>s.sport),['swim']);
assert.deepStrictEqual(G.slots(t,'2026-11-11'),[]);
assert.ok(t.weekly_pattern.every(x=>x[0].sport==='rest'));

// Saved calendar workouts show in the grid, can't be overwritten here, and copy like any other day.
G.setSaved({'2026-11-03':[{sport:'run',name:'Easy run'}]});
assert.deepStrictEqual(G.shown(t,'2026-11-03').map(s=>s.sport),['run']);
assert.strictEqual(G.addType(t,['2026-11-03'],'gym').added,0);
assert.strictEqual(G.targets(t,{period:7,cells:[{offset:0,slots:[]}]},'2026-11-03').length,0);
assert.deepStrictEqual(G.copy(t,['2026-11-03']).cells[0].slots.map(s=>s.sport),['run']);
G.setSaved({});

// A new phase starts with the previous phase's last week.
const next={label:'Development 2',start:'2026-11-16',end:'2026-11-30'};
assert.ok(G.seedFrom(t,next));
assert.deepStrictEqual(G.slots(next,'2026-11-23').map(s=>s.sport),['swim']);
assert.strictEqual(G.slots(next,'2026-11-23')[0].purpose,'Development 2');
assert.ok(!G.seedFrom({start:'2026-10-01',end:'2026-10-08'},{start:'2026-10-08',end:'2026-10-15'}),'an automatic phase seeds nothing');

console.log('PASS phase grid: rows, scattered add, copy/fill by whole weeks, conflicts, replace/empty, seeding');
