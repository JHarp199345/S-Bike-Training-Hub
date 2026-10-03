/* Pure duration allocation shared by the manual editor and its boundary checks. */
(function(root){
 function redistribute(phases,index,days,fixed){
  const next=phases.map(p=>({...p}));days=Math.round(Number(days));
  if(!Number.isFinite(days)||days<1||days>366)throw Error('A phase must last 1–366 days.');
  if(next[index].locked)throw Error('Unlock this phase before changing its duration.');
  const delta=days-next[index].days;
  if(fixed&&delta){
   const eligible=next.map((p,i)=>i!==index&&!p.locked?i:-1).filter(i=>i>=0);
   if(!eligible.length)throw Error('Unlock another phase to redistribute days, or choose a flexible end date.');
   let left=Math.abs(delta),weights=eligible.map(i=>next[i].days);
   if(delta>0&&eligible.reduce((n,i)=>n+next[i].days-1,0)<left)throw Error('There are not enough unlocked days; every phase needs at least one day.');
   if(delta<0&&eligible.reduce((n,i)=>n+366-next[i].days,0)<left)throw Error('The other phases would exceed 366 days.');
   while(left){
    let changed=false;const total=weights.reduce((a,b)=>a+b,0);
    for(let j=0;j<eligible.length&&left;j++){
     const i=eligible[j],capacity=delta>0?next[i].days-1:366-next[i].days;
     const share=Math.min(left,capacity,Math.max(1,Math.floor(left*weights[j]/total)));
     if(share){next[i].days+=delta>0?-share:share;left-=share;changed=true;}
    }
    if(!changed)throw Error('Unable to redistribute the requested days.');
   }
  }
  next[index].days=days;return next;
 }
 root.ProgramDraftMath={redistribute};
})(typeof module==='object'?module.exports:window);
