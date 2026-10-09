// Your own audio and video from your folder; this module never controls a trainer or workout.
export async function api(path, body) {
  const r = await fetch('/api/music/' + path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d = await r.json(); if (!r.ok) throw Error(d.error || 'Music could not load.'); return d;
}
export function node(tag, text, attrs={}) {
  const n=document.createElement(tag); if(text!==undefined)n.textContent=text;
  for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v); return n;
}
export const names={library:'Your folder',local:'Files from this device'};
// A song fits at its tempo or half of it (174 BPM = one beat per pedal stroke at 87 rpm); within 2 rpm of the band counts.
export function cadenceOf(bpm,band){if(!bpm||!band)return null;const mid=(band[0]+band[1])/2,fit=Math.abs(bpm/2-mid)<Math.abs(bpm-mid)?bpm/2:bpm;return {rpm:Math.round(fit),fits:fit>=band[0]-2&&fit<=band[1]+2};}

export class Queue {
  constructor(random=Math.random){this.random=random;this.items=[];this.index=-1;this.shuffle=false;this.history=[];this.bag=[];}
  set(items){this.items=items;this.index=items.length?0:-1;this.history=[];this.bag=[];}
  current(){return this.items[this.index];}
  next(){if(!this.items.length)return;this.history.push(this.index);
    if(this.shuffle && this.items.length>1){if(!this.bag.length)this.bag=this.items.map((_,i)=>i).filter(i=>i!==this.index);const n=Math.floor(this.random()*this.bag.length);this.index=this.bag.splice(n,1)[0];}
    else this.index=(this.index+1)%this.items.length;return this.current();}
  previous(){if(!this.items.length)return;this.index=this.history.length?this.history.pop():(this.index-1+this.items.length)%this.items.length;this.bag=[];return this.current();}
}
