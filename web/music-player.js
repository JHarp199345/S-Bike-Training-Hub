import {api,apple,applePlaylists,node,names,Queue,cadenceOf} from './music-common.js';
import {mountSettings} from './music-settings.js';
import {mountLibrary,icon,cover} from './music-library.js';
const byId=id=>document.getElementById(id),dock=byId('music-dock');
const audio=new Audio();audio.preload='metadata';const queue=new Queue();let provider='library',kit=null,generation=0,loaded='',blobURLs=[],listGeneration=0;
const title=byId('music-title'),detail=byId('music-detail'),play=byId('music-play'),message=byId('music-message'),tempoTag=byId('music-tempo'),artBox=byId('music-art');
byId('music-prev').append(icon('prev'));byId('music-next').append(icon('next'));byId('music-shuffle').append(icon('shuffle'));byId('music-vol-icon').append(icon('volume'));
byId('music-library-open').append(icon('library'));byId('music-settings-open').append(icon('gear'));
// The ride's cadence band and your recent cadence, read from the bridge only to suggest songs; music never changes the ride.
let band=null,cadences=[],matchMode=false;try{matchMode=localStorage.getItem('hub-music-match')==='yes';}catch(e){}
const cadence=()=>{const now=Date.now();cadences=cadences.filter(c=>now-c.t<60000);const on=cadences.filter(c=>c.v>0);return on.length>=3?Math.round(on.reduce((a,c)=>a+c.v,0)/on.length):null;};
async function watchCadence(){try{const r=await fetch('/status');if(r.ok){const s=await r.json();if(Array.isArray(s.band)&&s.band[0]>0)band=s.band.map(Math.round);cadences.push({t:Date.now(),v:s.cadence||0});render();}}catch(e){/* music works without the bridge */}
  setTimeout(watchCadence,document.hidden?15000:5000);}
function tempoText(item){if(!item?.bpm)return'';const bpm=Math.round(item.bpm),f=cadenceOf(item.bpm,band),cad=cadence();
  if(!f)return`${bpm} BPM`;if(cad&&Math.abs(f.rpm-cad)<=3)return`${bpm} BPM · matches your ${cad} rpm`;return f.fits?`${bpm} BPM · fits your ${band[0]}–${band[1]} rpm band`:`${bpm} BPM · fits ${f.rpm} rpm`;}
const listeners=new Set();
function say(text,error=false){message.textContent=text;message.classList.toggle('media-error',error);detail.textContent=text;}
function running(){return provider==='apple'?kit?.playbackState===window.MusicKit?.PlaybackStates?.playing:!audio.paused;}
function current(){return provider==='apple'?kit?.nowPlayingItem:queue.current();}
function render(){const item=current();const attrs=item?.attributes||item||{};
  title.firstChild.textContent=attrs.name||attrs.title||'Choose your music';detail.textContent=[attrs.artistName||attrs.artist,names[provider]].filter(Boolean).join(' · ');
  play.replaceChildren(icon(running()?'pause':'play'));play.setAttribute('aria-label',running()?'Pause music':'Play music');play.disabled=provider==='apple'?!loaded:!queue.current();
  byId('music-next').disabled=byId('music-prev').disabled=play.disabled;
  const art=provider==='apple'?null:item;if(artBox.dataset.art!==(art?.art||'')){artBox.dataset.art=art?.art||'';artBox.replaceChildren(...cover(art||{album:'♪'},'x').childNodes);}
  const t=provider==='apple'?'':tempoText(item);tempoTag.textContent=t;tempoTag.hidden=!t;tempoTag.classList.toggle('fits',/matches|fits your/.test(t));
  for(const fn of listeners)fn();
}
async function pause(){audio.pause();if(kit)await kit.pause();render();}
function loadCurrent(){const item=queue.current();audio.pause();if(item){audio.src=item.url;audio.load();}else{audio.removeAttribute('src');audio.load();}render();}
// With cadence matching on, the next song is one that fits the band (not one of the last few played), when there is one.
function matchNext(){if(!matchMode||!band||provider!=='library')return false;const recent=new Set([queue.index,...queue.history.slice(-8)]);
  const fits=queue.items.map((t,i)=>[t,i]).filter(([t,i])=>!recent.has(i)&&cadenceOf(t.bpm,band)?.fits);if(!fits.length)return false;
  queue.history.push(queue.index);queue.index=fits[Math.floor(Math.random()*fits.length)][1];return true;}
async function step(back=false){if(provider==='apple'){if(back)await kit.skipToPreviousItem();else await kit.skipToNextItem();}
  else{if(back)queue.previous();else if(!matchNext())queue.next();loadCurrent();await audio.play();}render();}
const guard=fn=>async(...args)=>{try{await fn(...args);}catch(e){say(e.message,true);}};
async function toggle(){if(running())await pause();else{if(provider==='apple')await kit.play();else await audio.play();render();}}
play.onclick=guard(toggle);
byId('music-next').onclick=guard(()=>step());byId('music-prev').onclick=guard(()=>step(true));
byId('music-shuffle').onclick=()=>{queue.shuffle=!queue.shuffle;queue.bag=[];byId('music-shuffle').setAttribute('aria-pressed',String(queue.shuffle));byId('setup-shuffle').checked=queue.shuffle;if(kit)kit.shuffleMode=queue.shuffle?window.MusicKit.PlayerShuffleMode.songs:window.MusicKit.PlayerShuffleMode.off;};
byId('music-volume').oninput=e=>{audio.volume=Number(e.target.value);if(kit)kit.volume=audio.volume;};audio.volume=.7;
audio.onplay=audio.onpause=render;audio.onended=guard(()=>step());audio.onerror=()=>{if(audio.getAttribute('src'))say('This song could not play. Choose another song or playlist.',true);};
// Play songs from your music folder (the library view, or the Playlists picker).
async function playTracks(tracks,index=0){++generation;await pause();provider='library';loaded='library';
  queue.set(tracks.map(t=>({...t,url:t.url||'/api/music/library/file/'+t.id})));queue.index=Math.max(0,Math.min(index,tracks.length-1));loadCurrent();await audio.play();render();}
const picker=byId('music-picker'),sources=byId('music-source'),list=byId('music-playlists');
for(const [id,name] of Object.entries(names))sources.append(node('option',name,{value:id}));
sources.value='library';
async function playlists(){const stamp=++listGeneration;list.replaceChildren();message.textContent='Loading…';const p=sources.value;
  byId('music-files').hidden=p!=='local';if(p==='local'){message.textContent='Choose audio files from this device. They stay in this browser; select them again after a page reload.';return;}
  try{const rows=p==='apple'?await applePlaylists():(await api('playlists?provider='+p)).playlists;if(stamp!==listGeneration)return;
    message.textContent=rows.length?'Choose a playlist, then press Play.':p==='library'?'Your music folder is empty. Add songs in Music settings.':'No playlists found. Create one in your music service first.';
    for(const row of rows){const b=node('button',row.name+(row.count!==undefined?' · '+row.count+(p==='library'?' songs':' tracks'):''));b.onclick=guard(async()=>{
      b.disabled=true;const transaction=++generation;
      try{if(p==='apple'){const nextKit=await apple();if(transaction!==generation)return;await pause();provider=p;kit=nextKit;await kit.setQueue({playlist:row.id});if(transaction!==generation)return;loaded=row.id;
          if(!kit.__hubWired){kit.__hubWired=true;for(const event of ['playbackStateDidChange','nowPlayingItemDidChange'])kit.addEventListener(event,render);kit.addEventListener('mediaPlaybackError',()=>say('Apple Music could not play this selection. Check your subscription and connection.',true));}kit.volume=audio.volume;}
        else{const result=await api('tracks?provider='+p+'&playlist='+encodeURIComponent(row.id));if(transaction!==generation)return;await pause();provider=p;loaded=row.id;queue.set(result.tracks);loadCurrent();}
        render();picker.close();say('Playlist selected. Press Play when you want music.');
      }finally{b.disabled=false;}
    });list.append(b);}
  }catch(e){if(stamp===listGeneration)say(e.message,true);}
}
sources.onchange=playlists;
const openPicker=guard(async()=>{
 picker.showModal();
 try{const settings=await api('settings');const option=sources.querySelector('option[value="apple"]');
  option.disabled=!settings.providers.apple.ready;option.textContent=option.disabled?'Apple Music · in progress':names.apple;
  if(option.disabled&&sources.value==='apple')sources.value='library';
 }catch(e){say('Connection status could not be checked. '+e.message,true);return;}
 await playlists();
});byId('music-choose').onclick=openPicker;
byId('music-files').onchange=guard(async e=>{const files=Array.from(e.target.files||[]).filter(f=>f.type.startsWith('audio/')||/\.(mp3|m4a|aac|ogg|wav|flac|opus)$/i.test(f.name));if(!files.length)return;
  ++generation;await pause();for(const url of blobURLs)URL.revokeObjectURL(url);blobURLs=[];provider='local';queue.set(files.map((f,i)=>{const url=URL.createObjectURL(f);blobURLs.push(url);return{id:String(i),title:f.name,url};}));loadCurrent();picker.close();});
const settings=byId('music-settings-dialog');const openSettings=()=>{settings.showModal();mountSettings(byId('ride-music-settings'));};byId('music-settings-open').onclick=openSettings;settings.addEventListener('close',()=>byId('ride-music-settings').musicDestroy?.());
const library=mountLibrary(byId('music-library'),{audio,play:guard(playTracks),toggle:guard(toggle),next:guard(()=>step()),prev:guard(()=>step(true)),current:()=>provider==='apple'?null:queue.current(),running,
  band:()=>band,cadence,tempoText,onChange:fn=>listeners.add(fn),openPlaylists:openPicker,openSettings,
  match:{get:()=>matchMode,set:v=>{matchMode=!!v;try{localStorage.setItem('hub-music-match',matchMode?'yes':'no');}catch(e){}}}});
byId('music-library-open').onclick=()=>library.open();artBox.onclick=()=>library.open();
for(const b of document.querySelectorAll('[data-close-dialog]'))b.onclick=()=>byId(b.dataset.closeDialog).close();
window.addEventListener('hub-music-disconnect',e=>{if(e.detail===provider){++generation;pause();loaded='';queue.set([]);loadCurrent();}});
window.addEventListener('hub-video-play',()=>pause());
// Deliberately independent of ride/scenery status, wattage and training intensity: cadence only suggests songs.
render();watchCadence();
