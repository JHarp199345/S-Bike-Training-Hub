(function(root){
 'use strict';
 function artworkURL(value){if(typeof value!=='string')return null;if(/^\/web\/[a-zA-Z0-9_./-]+$/.test(value)&&!value.includes('..'))return value;try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)?url.href:null;}catch(e){return null;}}
 function badgeFor(event){
  // Organizer artwork is used only when its permission is recorded explicitly.
  if(event.artwork_permission===true){const source=artworkURL(event.organizer_artwork);if(source)return source;}
  return null;
 }
 function upcoming(events,today){return (events||[]).filter(e=>/^\d{4}-\d{2}-\d{2}$/.test(e.date||'')&&e.date>=today).slice().sort((a,b)=>a.date.localeCompare(b.date)||String(a.id||a.name).localeCompare(String(b.id||b.name)));}
 function primaryGoal(goal,events){if(goal?.event_id&&!(events||[]).some(e=>e.id===goal.event_id))return null;return goal||null;}
 const api={badgeFor,upcoming,artworkURL,primaryGoal};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.EventGoals=api;
})(typeof globalThis!=='undefined'?globalThis:this);
