import {node,names,Queue,cadenceOf} from './music-common.js';
import {mountSettings} from './music-settings.js';
import {mountLibrary,icon,cover} from './music-library.js';
// The ride's player for your own audio (folder or this device). Video plays on the ride screen's Watch view.
const byId=id=>document.getElementById(id);
const audio=new Audio();audio.preload='metadata';const queue=new Queue();let provider='library',generation=0,blobURLs=[];
const title=byId('music-title'),detail=byId('music-detail'),play=byId('music-play'),tempoTag=byId('music-tempo'),artBox=byId('music-art');
byId('music-prev').append(icon('prev'));byId('music-next').append(icon('next'));byId('music-shuffle').append(icon('shuffle'));byId('music-vol-icon').append(icon('volume'));
byId('music-library-open').append(icon('library'));byId('music-settings-open').append(icon('gear'));
// The ride's cadence band and recent cadence, read only to label a song's tempo; music never changes the ride.
let band=null,cadences=[];
const cadence=()=>{const now=Date.now();cadences=cadences.filter(c=>now-c.t<60000);const on=cadences.filter(c=>c.v>0);return on.length>=3?Math.round(on.reduce((a,c)=>a+c.v,0)/on.length):null;};
async function watchCadence(){try{const r=await fetch('/status');if(r.ok){const s=await r.json();if(Array.isArray(s.band)&&s.band[0]>0)band=s.band.map(Math.round);cadences.push({t:Date.now(),v:s.cadence||0});render();}}catch(e){/* music works without the bridge */}
  setTimeout(watchCadence,document.hidden?15000:5000);}
function tempoText(item){if(!item?.bpm)return'';const bpm=Math.round(item.bpm),f=cadenceOf(item.bpm,band),cad=cadence();
  if(!f)return`${bpm} BPM`;if(cad&&Math.abs(f.rpm-cad)<=3)return`${bpm} BPM · matches your ${cad} rpm`;return f.fits?`${bpm} BPM · fits your ${band[0]}–${band[1]} rpm band`:`${bpm} BPM · fits ${f.rpm} rpm`;}
function say(text){detail.textContent=text;}
const running=()=>!audio.paused;
function render(){const item=queue.current()||{};
  title.firstChild.textContent=item.title||'Choose your music';detail.textContent=[item.artist,names[provider]].filter(Boolean).join(' · ');
  play.replaceChildren(icon(running()?'pause':'play'));play.setAttribute('aria-label',running()?'Pause music':'Play music');play.disabled=!queue.current();
  byId('music-next').disabled=byId('music-prev').disabled=play.disabled;
  if(artBox.dataset.art!==(item.art||'')){artBox.dataset.art=item.art||'';artBox.replaceChildren(...cover(item.title?item:{album:'♪'},'x').childNodes);}
  const t=tempoText(item);tempoTag.textContent=t;tempoTag.hidden=!t;tempoTag.classList.toggle('fits',/matches|fits your/.test(t));}
function pause(){audio.pause();render();}
function loadCurrent(){const item=queue.current();audio.pause();if(item){audio.src=item.url;audio.load();}else{audio.removeAttribute('src');audio.load();}render();}
async function step(back=false){if(back)queue.previous();else queue.next();loadCurrent();await audio.play();render();}
const guard=fn=>async(...args)=>{try{await fn(...args);}catch(e){say(e.message);}};
async function toggle(){if(running())pause();else{await audio.play();render();}}
function setShuffle(on){queue.shuffle=on;queue.bag=[];byId('music-shuffle').setAttribute('aria-pressed',String(on));const box=byId('setup-shuffle');if(box)box.checked=on;}
play.onclick=guard(toggle);byId('music-next').onclick=guard(()=>step());byId('music-prev').onclick=guard(()=>step(true));
byId('music-shuffle').onclick=()=>setShuffle(!queue.shuffle);
byId('music-volume').oninput=e=>{audio.volume=Number(e.target.value);};audio.volume=.7;
audio.onplay=audio.onpause=render;audio.onended=guard(()=>step());audio.onerror=()=>{if(audio.getAttribute('src'))say('This song could not play. Choose another one.');};
async function playTracks(tracks,index=0,shuffled=false){++generation;pause();provider='library';
  queue.set(tracks.map(t=>({...t,url:t.url||'/api/music/library/file/'+t.id})));queue.index=Math.max(0,Math.min(index,tracks.length-1));setShuffle(shuffled||queue.shuffle);loadCurrent();await audio.play();render();}
function playFiles(files){const audioFiles=files.filter(f=>f.type.startsWith('audio/')||/\.(mp3|m4a|aac|ogg|wav|flac|opus)$/i.test(f.name)),video=files.find(f=>f.type.startsWith('video/')||/\.(mp4|m4v|webm|mov)$/i.test(f.name));
  if(video&&!audioFiles.length){window.dispatchEvent(new CustomEvent('hub-play-video',{detail:{url:URL.createObjectURL(video),title:video.name}}));return;}
  ++generation;pause();for(const url of blobURLs)URL.revokeObjectURL(url);blobURLs=[];provider='local';
  queue.set(audioFiles.map((f,i)=>{const url=URL.createObjectURL(f);blobURLs.push(url);return{id:String(i),title:f.name,url};}));loadCurrent();audio.play().catch(()=>{});}
const settings=byId('music-settings-dialog');const openSettings=()=>{settings.showModal();mountSettings(byId('ride-music-settings'));};byId('music-settings-open').onclick=openSettings;settings.addEventListener('close',()=>byId('ride-music-settings').musicDestroy?.());
const library=mountLibrary(byId('music-library'),{play:guard(playTracks),playFiles,openSettings,
  playVideo:t=>{pause();window.dispatchEvent(new CustomEvent('hub-play-video',{detail:{url:t.url,title:t.title}}));}});
byId('music-library-open').onclick=()=>library.open();artBox.onclick=()=>library.open();
window.addEventListener('hub-open-library',e=>library.open(e.detail));
for(const b of document.querySelectorAll('[data-close-dialog]'))b.onclick=()=>byId(b.dataset.closeDialog).close();
window.addEventListener('hub-video-play',()=>pause());
// Deliberately independent of ride/scenery status, wattage and training intensity: cadence only labels a song's tempo.
render();watchCadence();
