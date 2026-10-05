(function(root){
'use strict';
const aliases={
 'touch your toes':{name:'Supported toe-reach stretch',how:'Use support and reach only as far as comfortable; do not force the stretch.'},
 'quad stretch':{name:'Supported standing quad stretch',how:'Hold a stable support; gently bend one knee if comfortable. Choose another position if balance or knee comfort limits you.'},
 'easy mobility':{name:'Easy mobility',how:'Move through a comfortable range without forcing it.'}
};
function parse(text,defaultSection='main'){
 const lifts=[],unresolved=[],substitutions=[];
 const parts=String(text).replace(/\r/g,' ').split(/\b(warm[ -]?up|main (?:work(?:out)?|set)|cool[ -]?down)\b\s*:?/ig);
 let section=defaultSection;
 const rx=/(?:\b(\d+)\s*(?:x|×|sets?\s*(?:of)?)\s*(\d+)\s*(?:reps?)?(?:\s*(?:per|each)\s+side)?(?:\s*(?:at|@|with)\s*(\d+(?:\.\d+)?)\s*(lb(?:s)?|pounds?|kg))?(?:\s*(?:tempo)?\s*(\d+-\d+-\d+(?:-\d+)?))?|\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?)\b)/ig;
 for(const part of parts){
  if(/^(warm[ -]?up|main (?:work(?:out)?|set)|cool[ -]?down)$/i.test(part)){section=/^warm/i.test(part)?'warmup':/^cool/i.test(part)?'cooldown':'main';continue;}
  let start=0,m;rx.lastIndex=0;
  while((m=rx.exec(part))){
   let name=part.slice(start,m.index).replace(/^[\s,;.*•\n-]*(?:and\s+|then\s+|this is the\s+)?/i,'').replace(/[\s,;:.]+$/,'').trim();
   if(!name){unresolved.push(m[0]);start=rx.lastIndex;continue;}
   const alias=aliases[name.toLowerCase()];if(alias){substitutions.push({from:name,to:alias.name});name=alias.name;}
   const x={name,section,per_side:/\b(?:per|each)\s+side\b/i.test(m[0]),sets:m[1]?+m[1]:1,reps:m[2]?+m[2]:null,seconds:null,weight:m[3]?+m[3]:null,unit:m[4]&&/^kg/i.test(m[4])?'kg':'lb',tempo:null,how:alias?.how||'',scored:false};
   // Regex groups: tempo=5, duration=6, duration unit=7.
   const timed=m[1]?part.slice(rx.lastIndex).match(/^\s*(seconds?|secs?|s)\b/i):null;if(timed){rx.lastIndex+=timed[0].length;x.reps=null;x.seconds=+m[2];}
   if(!timed)x.seconds=m[6]?+m[6]*(/^min/i.test(m[7])?60:1):null;x.tempo=m[5]||null;
   const side=part.slice(rx.lastIndex).match(/^\s*(?:per|each)\s+side\b/i);if(side){x.per_side=true;rx.lastIndex+=side[0].length;}
   const extraWeight=part.slice(rx.lastIndex).match(/^\s*(?:@|at|with)\s*(\d+(?:\.\d+)?)\s*(lb(?:s)?|pounds?|kg)\b/i);if(extraWeight){x.weight=+extraWeight[1];x.unit=/^kg/i.test(extraWeight[2])?'kg':'lb';rx.lastIndex+=extraWeight[0].length;}
   const description=part.slice(rx.lastIndex).match(/^\s*(?:—|--)\s*("(?:\\.|[^"\\])*"|[^;\n]*)/);if(description){x.how=(description[1].startsWith('"')?JSON.parse(description[1]):description[1].trim()).slice(0,300);rx.lastIndex+=description[0].length;}
   if(name.length>80||x.sets>20||(x.reps&&x.reps>100)||(x.seconds&&x.seconds>600)||(x.weight&&x.weight>1000)){unresolved.push(part.slice(start,rx.lastIndex).trim());}
   else lifts.push(x);
   start=rx.lastIndex;
  }
  const tail=part.slice(start).replace(/^[\s,;:.]+|[\s,;:.]+$/g,'');if(tail)unresolved.push(tail);
 }
 if(lifts.length>30){unresolved.push('More than 30 exercises: split this into separate sessions.');lifts.length=30;}
 return {lifts,unresolved,substitutions};
}
root.WorkoutParser={parse};if(typeof module!=='undefined')module.exports=root.WorkoutParser;
})(typeof window!=='undefined'?window:globalThis);
// Repeated blocks retain a title; lifting sets include every repetition once.
(function(root){
 const parser=root.WorkoutParser||(typeof module!=='undefined'?module.exports:null);
 function outline(fields,repeats=1){
  repeats=Number(repeats);if(!Number.isInteger(repeats)||repeats<1||repeats>10)return {lifts:[],steps:[],unresolved:['Repeat count must be 1–10.'],substitutions:[]};
  const lifts=[],steps=[],unresolved=[],substitutions=[];
  for(const section of ['warmup','main','cooldown']){
   const text=String(fields[section]||'').trim();if(!text)continue;
   const chunks=text.split(/\b((?:interval|block|circuit)\s+\d+)\s*:?/ig);let block='';
   for(const chunk of chunks){if(/^(interval|block|circuit)\s+\d+$/i.test(chunk)){block=chunk;continue;}if(!chunk.trim())continue;
    const parsed=parser.parse(chunk,section),times=section==='main'?repeats:1;
    for(const lift of parsed.lifts){lift.sets*=times;if(lift.sets>20){unresolved.push(lift.name+': repeated sets exceed 20; split the workout.');continue;}if(block)lift.block=block;lift.block_repeats=times;lifts.push(lift);}
    substitutions.push(...parsed.substitutions);unresolved.push(...parsed.unresolved);
    const lines=chunk.trim().split(/\n|;/).map(x=>x.trim()).filter(Boolean);
    for(const line of lines)steps.push(`${section==='warmup'?'Warm-up':section==='cooldown'?'Cool-down':'Main work'}${block?' · '+block:''}${times>1?' · repeat '+times+' times':''}: ${line}`);
   }
  }
  if(lifts.length>30||steps.length>30)unresolved.push('Maximum 30 exercises or outline lines per session.');
  return {lifts,steps,unresolved,substitutions};
 }
 parser.outline=outline;
})(typeof window!=='undefined'?window:globalThis);
