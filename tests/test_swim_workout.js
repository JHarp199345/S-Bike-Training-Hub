const assert=require('node:assert/strict');
const {render}=require('../web/swim-workout.js');
const p={unit:'yd',total_distance:400,sendoff_minutes:8,sets:[{section:'main',group:'Main <set>',distance:100,distance_m:365.76,repetitions:4,unit:'yd',description:'Free <script>alert(1)</script> @ 2:00',sendoff_seconds:120}]};
const html=render(p,true);assert(html.includes('400 yd'));assert(html.includes('start-to-start, not fixed rest'));assert(!html.includes('<script>'));assert(html.includes('Main &lt;set&gt;'));
const rest=render({...p,sets:[{...p.sets[0],sendoff_seconds:null,rest_seconds:20}]});assert(rest.includes('Rest 20 seconds'));assert(!rest.includes('Send off every'));
console.log('PASS swim display preserves distance, timing meaning and escapes imported text');
