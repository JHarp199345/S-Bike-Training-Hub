(function(root){
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number='(\\d+(?:\\.\\d+)?)',unit='(minutes?|mins?|seconds?|secs?)';
function normalize(s){return String(s||'').replace(/[–—−]/g,'-').replace(/×/g,'x').replace(/\r/g,'').trim();}
function time(text){const m=new RegExp(number+'\\s*'+unit+'\\b','i').exec(text);return m?{minutes:+m[1]*(/^s/i.test(m[2])?1/60:1),match:m[0],index:m.index}:null;}
function power(text){
 const m=new RegExp(number+'\\s*(?:(?:-|to)\\s*'+number+'\\s*)?(?:watts?|w)\\b','i').exec(text);
 if(!m)return null;const low=+m[1],high=m[2]?+m[2]:low;
 if(low<20||high>1500||high<low)throw Error('Use an ordered power target between 20 and 1500 W.');
 return {watts:Math.round((low+high)/2),...(high!==low?{watts_low:low,watts_high:high}:{}),match:m[0]};
}
function steady(text,section,label){const times=text.match(new RegExp(number+'\\s*'+unit+'\\b','ig'))||[],powers=text.match(new RegExp(number+'\\s*(?:(?:-|to)\\s*'+number+'\\s*)?(?:watts?|w)\\b','ig'))||[];if(times.length>1||powers.length>1)throw Error('Separate each timed stage with a new line, semicolon or “then”.');const t=time(text),p=power(text);if(!t)throw Error('Add a duration in minutes or seconds.');if(!p)throw Error('Add a watt target, including for recovery.');if(t.minutes<1/60||t.minutes>300)throw Error('Each stage must last 1 second to 300 minutes.');return {type:'steady',minutes:t.minutes,...p,match:undefined,label,section};}
function parse(fields,repeats=1,enteredMinutes){
 const blocks=[],issues=[],warnings=[],declared=[];repeats=Number(repeats);
 if(!Number.isInteger(repeats)||repeats<1||repeats>10)issues.push('Repeat count must be 1–10.');
 for(const section of ['warmup','main','cooldown']){
  let text=normalize(fields[section]);if(!text)continue;
  text=text.replace(new RegExp(number+'\\s*'+unit+'\\s+total\\b','ig'),(full,n,u)=>{declared.push({section,minutes:+n*(/^s/i.test(u)?1/60:1)});return '';});
  text=text.replace(/\b(?:warm[ -]?up|main work(?:out)?|cool[ -]?down)\s*:/ig,'');
  const sectionBlocks=[],issueCount=issues.length;
  // A repeat recipe spans one line, or a paragraph. Semicolons separate independent recipes.
  const lines=text.split(/\n|;|\bthen\b/i).map(x=>x.trim()).filter(Boolean);
  for(let line of lines){
   try{
    const count=new RegExp('^\\s*(\\d+)\\s*x\\s*\\(?\\s*','i').exec(line);
    if(count){
     const n=+count[1];if(n<1||n>50)throw Error('Use 1–50 interval repetitions.');
     const body=line.slice(count[0].length).replace(/\)\s*$/,'');
     const split=body.split(/\bwith\b|\bfollowed by\b|\brecover(?:y)?(?: for)?\b|\brest(?: for)?\b|\+|\//i);
     const workTotal=new RegExp('\\bfor\\s+'+number+'\\s*'+unit+'\\s+(?:worth of\\s+)?work\\b','i').exec(split[0]);
     const on=steady(workTotal?split[0].replace(workTotal[0],''):split[0],section,'Work');
     if(workTotal&&Math.abs(+workTotal[1]*(/^s/i.test(workTotal[2])?1/60:1)-n*on.minutes)>.01)throw Error('The stated work duration does not match the repeated work intervals.');
     if(split.length>2)throw Error('Use one work stage and one recovery stage per recipe, or separate recipes with semicolons.');
     let off=null,offCount=0;
     if(split[1]?.trim()){
      const restText=split[1].trim();const counted=new RegExp('^\\s*(\\d+)\\s*x\\s*','i').exec(restText);
      off=steady(restText.replace(new RegExp('^\\s*\\d+\\s*x\\s*','i'),''),section,'Recovery');
      offCount=counted?+counted[1]:n-1;
      if(!counted&&!/\b(?:between|inbetween|in between|after each|including (?:the )?last|each round)\b/i.test(line)&&!/[+\/]/.test(body))throw Error('Say “between intervals” or “after each interval” to place recovery.');
      if(!counted&&(/\b(?:after each|including (?:the )?last|each round)\b/i.test(line)||/[+\/]/.test(body)))offCount=n;
      if(offCount!==n-1&&offCount!==n)throw Error(`For ${n} work intervals, specify ${n-1} recoveries between them or ${n} including after the last.`);
     }else if(n>1&&!/\bno recovery\b/i.test(line))throw Error('Add the recovery duration and watt target, or explicitly say “no recovery”.');
     if(offCount===n&&n>1&&/\b(?:between|inbetween|in between)\b/i.test(line))throw Error(`There are only ${n-1} gaps between ${n} intervals. Say “after each interval” for ${n} recoveries.`);
     for(let i=0;i<n;i++){sectionBlocks.push({...on,label:'Work '+(i+1)});if(off&&i<offCount)sectionBlocks.push({...off,label:'Recovery '+(i+1)});}
    }else{
     const ramp=new RegExp('(?:from\\s+)?'+number+'\\s*(?:watts?|w)?\\s*(?:to|down to|up to|-)\\s*'+number+'\\s*(?:watts?|w)\\b','i').exec(line);
     if(/\bramp(?:ing)?\b/i.test(line)){
      const t=time(line);if(!t||!ramp)throw Error('Write a ramp with its duration and start/end watts, e.g. “8 minutes ramping from 160 to 80 watts”.');
      if(t.minutes<.5||t.minutes>120||+ramp[1]<20||+ramp[1]>1500||+ramp[2]<20||+ramp[2]>1500)throw Error('Ramps need 30 seconds–120 minutes and 20–1500 W endpoints.');
      sectionBlocks.push({type:'ramp',minutes:t.minutes,from_watts:+ramp[1],to_watts:+ramp[2],label:section==='cooldown'?'Cool-down ramp':'Ramp',section});
     }else{
      // Multiple durations/targets in one sentence cannot silently become one stage.
      const times=line.match(new RegExp(number+'\\s*'+unit+'\\b','ig'))||[];
      const powers=line.match(new RegExp(number+'\\s*(?:(?:-|to)\\s*'+number+'\\s*)?(?:watts?|w)\\b','ig'))||[];
      if(times.length!==1||powers.length!==1)throw Error('Separate each timed stage with a new line, semicolon or “then”.');
      sectionBlocks.push(steady(line,section,section==='warmup'?'Warm-up':section==='cooldown'?'Cool-down':'Main work'));
     }
    }
   }catch(e){issues.push((section==='warmup'?'Warm-up':section==='cooldown'?'Cool-down':'Main work')+': '+e.message);}
  }
  const sectionMinutes=sectionBlocks.reduce((a,b)=>a+b.minutes,0);
  for(const d of declared.filter(x=>x.section===section&&issues.length===issueCount))if(Math.abs(d.minutes-sectionMinutes)>.01)issues.push(`${section}: the stated ${d.minutes} minutes does not match ${+sectionMinutes.toFixed(2)} minutes of stages.`);
  const rounds=section==='main'&&Number.isInteger(repeats)&&repeats>=1&&repeats<=10?repeats:1;
  for(let i=0;i<rounds;i++)blocks.push(...sectionBlocks.map(b=>({...b,...(rounds>1?{label:b.label+' · round '+(i+1)}:{})})));
 }
 const minutes=+blocks.reduce((a,b)=>a+b.minutes,0).toFixed(4);
 if(!blocks.length)issues.push('Add at least one timed cycling stage with watts.');
 if(minutes>360)issues.push('Maximum ride duration is six hours.');
 if(blocks.reduce((sum,b)=>sum+(b.type==='ramp'?Math.min(120,Math.max(2,Math.round(b.minutes*4))):1),0)>200)issues.push('Maximum 200 power stages after expanding ramps; split this ride.');
 const complete=!issues.length;
 const mismatch=complete&&enteredMinutes!=null&&Math.abs(Number(enteredMinutes)-minutes)>.01;
 if(mismatch)issues.push(`Total time is ${+minutes.toFixed(2)} minutes including warm-up and cool-down, not ${enteredMinutes}.`);
 if(blocks.some(b=>b.watts_high-b.watts_low>=50))warnings.push('A wide power band spans different efforts. ERG uses its midpoint; the band is displayed as your intended range.');
 return {blocks,minutes,issues,warnings,mismatch,complete,valid:!issues.length};
}
function render(p){
 const max=Math.max(1,...p.blocks.flatMap(b=>[b.watts_high||b.watts||b.from_watts,b.to_watts||0]));
 const summary=b=>b.type==='ramp'?`${b.from_watts} → ${b.to_watts} W`:b.watts_low!=null?`${b.watts_low}–${b.watts_high} W · target ${b.watts} W`:`${b.watts} W`;
 return `<section class="ride-parse-preview"><h3>${p.complete?'Ride timeline':'Partial timeline — clarify below'} · ${+p.minutes.toFixed(2)} minutes${p.complete?'':' resolved'}</h3><p class="sub">Power ranges keep their bounds. ERG uses the midpoint as a single target; ramps follow their start and end watts. Targets are fixed watts, independent of FTP changes.</p><div class="ride-parse-chart" role="img" aria-label="Cycling power timeline">${p.blocks.map(b=>`<div style="flex:${b.minutes};--stage-color:${b.section==='warmup'?'#fb923c':b.section==='cooldown'?'#22d3ee':'#facc15'}" title="${esc(b.label)}: ${+b.minutes.toFixed(2)} min, ${esc(summary(b))}"><i style="height:${Math.max(8,100*(b.watts||Math.max(b.from_watts,b.to_watts))/max)}%;${b.type==='ramp'?`clip-path:polygon(0 ${100*(1-b.from_watts/Math.max(b.from_watts,b.to_watts))}%,100% ${100*(1-b.to_watts/Math.max(b.from_watts,b.to_watts))}%,100% 100%,0 100%)`:''}"></i></div>`).join('')}</div><ol>${p.blocks.map(b=>`<li><b>${esc(b.label)}</b> · ${+b.minutes.toFixed(2)} min · ${esc(summary(b))}</li>`).join('')}</ol>${p.warnings.map(s=>`<p class="note">${esc(s)}</p>`).join('')}${p.issues.map(s=>`<p class="note">${esc(s)}</p>`).join('')}${p.mismatch&&p.complete?'<button type="button" id="manual-use-duration">Use calculated total</button>':''}</section>`;
}
const api={parse,render};root.RideParser=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
