const assert=require('node:assert/strict'),P=require('../web/workout-parser.js'),F=require('../web/workout-format.js');
let x=P.parse('warm-up touch your toes 10 seconds quad stretch 10 seconds main work bench press 3 x 10 @ 100 lb tempo 3-0-3 cool down easy mobility 2 minutes');
assert.equal(x.lifts.length,4);assert.deepEqual(x.lifts.map(y=>y.section),['warmup','warmup','main','cooldown']);assert.equal(x.lifts[2].weight,100);assert.equal(x.lifts[2].tempo,'3-0-3');assert.equal(x.lifts[3].seconds,120);assert.equal(x.unresolved.length,0);
x=P.outline({warmup:'easy mobility 60 seconds',main:'Block 1: bench press 2 x 10 @ 100 lb; row 2 x 10 @ 40 lb Block 2: dead bug 1 x 8',cooldown:'quad stretch 20 seconds'},4);
assert.deepEqual(x.lifts.map(y=>y.sets),[1,8,8,4,1]);assert.equal(x.lifts[1].block,'Block 1');assert.equal(x.lifts[3].block,'Block 2');assert.equal(x.lifts[1].block_repeats,4);assert.equal(x.unresolved.length,0);
assert(F.render({sport:'gym',lifts:x.lifts},{preview:true}).includes('4 rounds (included in sets)'));
assert(P.outline({main:'press 6 x 8'},4).unresolved.length);assert(P.parse('something vague').unresolved.length);assert(P.outline({main:'100m drill; 100m swim'},2).steps.every(y=>y.includes('repeat 2 times')));
console.log('PASS section parsing, repeated blocks counted once, substitutions, bounds, and ambiguous input');

x=P.parse('dead bug 2 x 8 per side; bridge hold 3 x 30 seconds');assert(x.lifts[0].per_side);assert.equal(x.lifts[1].seconds,30);assert.equal(x.lifts[1].reps,null);

x=P.parse('V-ups 3 x 10 — Lie on your back and lift the legs and torso; row 2 x 8 @ 40 lb — Keep the movement controlled');assert.equal(x.lifts[0].name,'V-ups');assert.equal(x.lifts[0].how,'Lie on your back and lift the legs and torso');assert.equal(x.lifts[1].name,'row');assert.equal(x.unresolved.length,0);

x=P.parse('carry 3 x 30 seconds per side @ 35 lb — Walk tall');assert(x.lifts[0].per_side);assert.equal(x.lifts[0].weight,35);assert.equal(x.lifts[0].seconds,30);assert.equal(x.unresolved.length,0);
