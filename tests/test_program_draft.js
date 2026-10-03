const assert=require('node:assert/strict');const {ProgramDraftMath:m}=require('../web/program-draft.js');
const phases=[{days:20},{days:30},{days:10,locked:true}];
const next=m.redistribute(phases,0,25,true);assert.equal(next.reduce((s,p)=>s+p.days,0),60);assert.equal(next[2].days,10);assert.equal(phases[0].days,20);
assert.throws(()=>m.redistribute(phases,2,11,true));assert.throws(()=>m.redistribute([{days:5},{days:1}],0,6,true));
assert.equal(m.redistribute(phases,0,25,false).reduce((s,p)=>s+p.days,0),65);
for(let n=1;n<50;n++){const r=m.redistribute([{days:10},{days:30},{days:40}],0,n,true);assert.equal(r.reduce((s,p)=>s+p.days,0),80);assert.ok(r.every(p=>p.days>=1));}
console.log('Duration allocation: boundaries, locks and totals passed.');
