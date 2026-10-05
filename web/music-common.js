// User-selected background music; this module never controls a trainer or workout.
export async function api(path, body) {
  const r = await fetch('/api/music/' + path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d = await r.json(); if (!r.ok) throw Error(d.error || 'Music could not load.'); return d;
}
export function node(tag, text, attrs={}) {
  const n=document.createElement(tag); if(text!==undefined)n.textContent=text;
  for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v); return n;
}
let applePromise;
export function apple() {
  if(!applePromise)applePromise=(async()=>{
    const {developer_token}=await api('apple');
    if(!window.MusicKit)await new Promise((resolve,reject)=>{
      const script=node('script',undefined,{src:'https://js-cdn.music.apple.com/musickit/v3/musickit.js'});
      script.onload=resolve;script.onerror=()=>reject(Error('Apple Music could not load. Check your connection.'));document.head.append(script);
    });
    return window.MusicKit.getInstance() || window.MusicKit.configure({developerToken:developer_token,app:{name:'S-Bike Training Hub',build:'1.0'}});
  })().catch(e=>{applePromise=null;throw e;});
  return applePromise;
}
export function appleRows(response) { return response?.data?.data || response?.data || []; }
export async function applePlaylists() {
  const kit=await apple();if(!kit.isAuthorized)throw Error('Connect Apple Music in Music settings first.');
  let path='/v1/me/library/playlists', rows=[];
  while(path && rows.length<5000){const d=await kit.api.music(path);rows.push(...appleRows(d));path=d?.data?.next||d?.next;}
  return rows.map(v=>({id:v.id,name:v.attributes?.name||'Playlist'}));
}
export const names={plex:'Plex',apple:'Apple Music',ibroadcast:'iBroadcast',subsonic:'OpenSubsonic',local:'Music from this computer'};

export class Queue {
  constructor(random=Math.random){this.random=random;this.items=[];this.index=-1;this.shuffle=false;this.history=[];this.bag=[];}
  set(items){this.items=items;this.index=items.length?0:-1;this.history=[];this.bag=[];}
  current(){return this.items[this.index];}
  next(){if(!this.items.length)return;this.history.push(this.index);
    if(this.shuffle && this.items.length>1){if(!this.bag.length)this.bag=this.items.map((_,i)=>i).filter(i=>i!==this.index);const n=Math.floor(this.random()*this.bag.length);this.index=this.bag.splice(n,1)[0];}
    else this.index=(this.index+1)%this.items.length;return this.current();}
  previous(){if(!this.items.length)return;this.index=this.history.length?this.history.pop():(this.index-1+this.items.length)%this.items.length;this.bag=[];return this.current();}
}
