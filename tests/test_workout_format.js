const assert=require('node:assert/strict');
const f=require('../web/workout-format.js');
const a=f.totals([{name:'Lift',sets:3,reps:10,weight:100,unit:'lb',tempo:'3-0-3',hold:2},{name:'Static hold',sets:2,seconds:30,weight:50,unit:'kg',per_side:true}]);
assert(Math.abs(a.kg-1360.77711)<.0001); assert.equal(a.seconds,360);
const b=f.totals([{name:'Row',sets:2,reps:5,weight:10,unit:'kg',per_side:true},{name:'Unknown',sets:1,reps:8}]);
assert.equal(b.kg,200);assert.equal(b.unknownWeight,1);assert.equal(b.assumed,2);
assert.equal(f.stepSection('Warm-up · 5 min'),'warmup');assert.equal(f.stepSection('Cool-down · 3 min'),'cooldown');
assert.equal(f.section({style:'restorative'}),'main');
assert(!f.render({lifts:[{name:'<script>',sets:1,seconds:30}]},{actual:true}).includes('<script>'));
console.log('PASS workout-format quantities, incomplete data, stages, and escaped exercise names');

const inferred=f.organize({lifts:[{name:'Prep',style:'restorative'},{name:'Lift',style:'build'},{name:'Ease',style:'restorative'}]});assert.deepEqual(inferred.lifts.map(f.section),['warmup','main','cooldown']);assert(inferred.inferred);assert(!f.organize({lifts:[{name:'Explicit main',style:'restorative',section:'main'}]}).inferred);

const actualTimes=f.setTable({name:'Timed push',sets:3,seconds:60,set_details:[{seconds:60},{seconds:60},{seconds:60}]});
assert(!actualTimes.includes('180 s') && (actualTimes.match(/60 s/g)||[]).length===6,'Each set displays its own duration');
const actualTotal=f.render({sport:'gym',points_total:151.2,lifts:[{name:'A',sets:1,reps:1,weight:1,points:151.4}]},{actual:true});
assert(actualTotal.includes('151.2 strength points · logged estimate'),'Historical session total survives section rounding');
