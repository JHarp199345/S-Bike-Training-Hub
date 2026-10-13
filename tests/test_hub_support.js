const assert=require('node:assert/strict');
const p=require('../web/support-policy.js');
const state=p.fresh();let now=0;
function session(since,seconds){const s={mode:{id:'monster-chase',name:'Monster Chase',since},bike:true,power:150,cadence:80};for(let n=0;n<=seconds;n+=5){p.observe(state,s,now);now+=5;}assert.equal(p.pending(state),null);p.observe(state,{mode:null},now);now+=5;}
session(1,10);assert.equal(state.modules['monster-chase'],undefined,'menu previews must not count');
for(let i=2;i<=4;i++)session(i,65);
assert.equal(state.modules['monster-chase'],3);assert.equal(p.pending(state),'monster-chase');
state.shown['monster-chase']=true;assert.equal(p.pending(state),null,'dismissed invitations must never repeat');
state.modules.other=3;assert.equal(p.pending(state),'other');state.never=true;assert.equal(p.pending(state),null);state.never=false;state.supported=true;assert.equal(p.pending(state),null);
const idle=p.fresh();for(let i=0;i<100;i++)p.observe(idle,{mode:{id:'x',since:1},bike:true,cadence:0,power:0},i*5);p.observe(idle,{mode:null},501);assert.equal(idle.modules.x,undefined,'idle game must not count');
const disconnected=p.fresh();p.observe(disconnected,{mode:{id:'x',since:1},bike:true,power:200,cadence:80},0);p.observe(disconnected,{mode:{id:'x',since:1},bike:true,power:200,cadence:80},3600);assert.equal(disconnected.current.seconds,10,'connection gap must not count as an hour of riding');
console.log('PASS real-use threshold, short preview/idle exclusion, active-ride deferral, one invitation per module, global opt-out/support, disconnected gaps');
