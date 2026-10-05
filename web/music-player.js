import {api,apple,applePlaylists,node,names,Queue} from './music-common.js';
import {mountSettings} from './music-settings.js';
const byId=id=>document.getElementById(id),dock=byId('music-dock');
const audio=new Audio();audio.preload='metadata';const queue=new Queue();let provider='local',kit=null,generation=0,loaded='',blobURLs=[],listGeneration=0;
let heard=0,played=false,lastSecond=0;
const title=byId('music-title'),detail=byId('music-detail'),play=byId('music-play'),message=byId('music-message');
function say(text,error=false){message.textContent=text;message.classList.toggle('media-error',error);detail.textContent=text;}
function running(){return provider==='apple'?kit?.playbackState===window.MusicKit?.PlaybackStates?.playing:!audio.paused;}
function render(){const item=provider==='apple'?kit?.nowPlayingItem:queue.current();const attrs=item?.attributes||item||{};
  title.firstChild.textContent=attrs.name||attrs.title||'Choose your music';detail.textContent=[attrs.artistName||attrs.artist,names[provider]].filter(Boolean).join(' · ');
  play.textContent=running()?'Pause':'Play';play.setAttribute('aria-label',running()?'Pause music':'Play music');play.disabled=provider==='apple'?!loaded:!queue.current();
  byId('music-next').disabled=byId('music-prev').disabled=play.disabled;
}
async function pause(){audio.pause();if(kit)await kit.pause();render();}
async function history(event){if(provider!=='ibroadcast'||!queue.current())return;try{await api('history',{provider,event,track:queue.current().id});}catch(e){/* Playback stays usable if listening history is unavailable. */}}
function resetHistory(){heard=0;played=false;lastSecond=0;}
function loadCurrent(){const item=queue.current();audio.pause();resetHistory();if(item){audio.src=item.url;audio.load();}else{audio.removeAttribute('src');audio.load();}render();}
async function step(back=false,ended=false){if(!ended)await history('skip');if(provider==='apple'){if(back)await kit.skipToPreviousItem();else await kit.skipToNextItem();}
  else{if(back)queue.previous();else queue.next();loadCurrent();await audio.play();}render();}
const guard=fn=>async(e)=>{try{await fn(e);}catch(e){say(e.message,true);}};
play.onclick=guard(async()=>{if(running())await pause();else{if(provider==='apple')await kit.play();else await audio.play();render();}});
byId('music-next').onclick=guard(()=>step());byId('music-prev').onclick=guard(()=>step(true));
byId('music-shuffle').onclick=()=>{queue.shuffle=!queue.shuffle;queue.bag=[];byId('music-shuffle').setAttribute('aria-pressed',String(queue.shuffle));byId('setup-shuffle').checked=queue.shuffle;if(kit)kit.shuffleMode=queue.shuffle?window.MusicKit.PlayerShuffleMode.songs:window.MusicKit.PlayerShuffleMode.off;};
byId('music-volume').oninput=e=>{audio.volume=Number(e.target.value);if(kit)kit.volume=audio.volume;};audio.volume=.7;
audio.onplay=audio.onpause=render;audio.onended=guard(()=>step(false,true));audio.onerror=()=>say('This audio format could not play. Choose another file or playlist.',true);
audio.ontimeupdate=()=>{const now=audio.currentTime;if(!audio.paused&&now>=lastSecond&&now-lastSecond<3)heard+=now-lastSecond;lastSecond=now;if(heard>=10&&!played){played=true;history('play');}};
const picker=byId('music-picker'),sources=byId('music-source'),list=byId('music-playlists');
for(const [id,name] of Object.entries(names))sources.append(node('option',name,{value:id}));
sources.value='local';
async function playlists(){const stamp=++listGeneration;list.replaceChildren();message.textContent='Loading…';const p=sources.value;
  byId('music-files').hidden=p!=='local';if(p==='local'){message.textContent='Choose audio files from your computer. They stay on this device; select them again after a page reload.';return;}
  try{const rows=p==='apple'?await applePlaylists():(await api('playlists?provider='+p)).playlists;if(stamp!==listGeneration)return;
    message.textContent=rows.length?'Choose a playlist, then press Play.':'No playlists found. Create one in your music service first.';
    for(const row of rows){const b=node('button',row.name+(row.count!==undefined?' · '+row.count+' tracks':''));b.onclick=guard(async()=>{
      b.disabled=true;const transaction=++generation;
      try{if(p==='apple'){const nextKit=await apple();if(transaction!==generation)return;await pause();provider=p;kit=nextKit;await kit.setQueue({playlist:row.id});if(transaction!==generation)return;loaded=row.id;
          if(!kit.__hubWired){kit.__hubWired=true;for(const event of ['playbackStateDidChange','nowPlayingItemDidChange'])kit.addEventListener(event,render);kit.addEventListener('mediaPlaybackError',()=>say('Apple Music could not play this selection. Check your subscription and connection.',true));}kit.volume=audio.volume;}
        else{const result=await api('tracks?provider='+p+'&playlist='+encodeURIComponent(row.id));if(transaction!==generation)return;await pause();provider=p;loaded=row.id;queue.set(result.tracks);loadCurrent();}
        render();picker.close();say('Playlist selected. Press Play when you want music.');
      }finally{b.disabled=false;}
    });list.append(b);}
  }catch(e){if(stamp===listGeneration)say(e.message,true);}
}
sources.onchange=playlists;byId('music-choose').onclick=()=>{picker.showModal();playlists();};
byId('music-files').onchange=guard(async e=>{const files=Array.from(e.target.files||[]).filter(f=>f.type.startsWith('audio/')||/\.(mp3|m4a|aac|ogg|wav|flac|opus)$/i.test(f.name));if(!files.length)return;
  ++generation;await pause();for(const url of blobURLs)URL.revokeObjectURL(url);blobURLs=[];provider='local';queue.set(files.map((f,i)=>{const url=URL.createObjectURL(f);blobURLs.push(url);return{id:String(i),title:f.name,url};}));loadCurrent();picker.close();});
const settings=byId('music-settings-dialog');byId('music-settings-open').onclick=()=>{settings.showModal();mountSettings(byId('ride-music-settings'));};settings.addEventListener('close',()=>byId('ride-music-settings').musicDestroy?.());
for(const b of document.querySelectorAll('[data-close-dialog]'))b.onclick=()=>byId(b.dataset.closeDialog).close();
window.addEventListener('hub-music-disconnect',e=>{if(e.detail===provider){++generation;pause();loaded='';queue.set([]);loadCurrent();}});
window.addEventListener('hub-video-play',()=>pause());
// Deliberately independent of ride/scenery status, wattage and training intensity.
render();
