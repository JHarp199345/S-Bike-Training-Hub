import {api,apple,node,names} from './music-common.js';
export async function mountSettings(root) {
  root.classList.add('hub-music');root.replaceChildren();
  const intro=node('p','Add your music to your folder, then open the Library in Ride. Plex connections are in progress while real-account playback is verified. Apple Music is in progress pending publisher setup. Your account access stays on this computer. Music is independent of your workout.');root.append(intro);
  const privacy=node('details');privacy.append(node('summary','Setup and privacy'),node('p','Your music folder stays on this computer: the Hub reads it and never moves, changes or uploads your files. Files you drop in are saved there. Files you pick from another device stay in that browser.'),node('p','Apple Music sign-in is handled by MusicKit in your browser. Plex access is saved locally in the Hub’s private music settings; Plex receives sign-in, library and playback requests. Music is not sent to your coaching assistant or logged as a workout. Disconnect removes the Hub’s saved access; revoke access in the service account too if needed.'),node('p','Plex needs your own reachable server. Apple Music requires the Hub publisher’s app setup first; athletes do not need developer accounts.'),node('a','Plex terms and privacy',{href:'https://www.plex.tv/about/privacy-legal/',target:'_blank',rel:'noopener noreferrer'}));root.append(privacy);
  const notice=node('p','Loading connections…',{'role':'status'}),cards=node('div',undefined,{'class':'music-cards'});root.append(notice,cards);
  // your music folder: drop files in, they're saved on this computer (outside the Hub's code, never shared)
  const fcard=node('section',undefined,{'class':'music-card music-folder'});root.insertBefore(fcard,notice);
  const drawFolder=async()=>{let f;try{f=await api('folder');}catch(e){fcard.replaceChildren(node('h3','Your music folder'),node('p',e.message));return;}
    const zone=node('div','Drop music files here, or click to choose',{'class':'music-drop','tabindex':'0','role':'button','aria-label':'Add music files to your folder'});
    const pick=node('input',undefined,{type:'file',multiple:'',accept:'audio/*,.mp3,.m4a,.aac,.flac,.wav,.aif,.aiff,.ogg,.opus',hidden:''});
    const status=node('p','',{'aria-live':'polite','class':'music-link-status'});
    const send=async files=>{files=[...files];let n=0;for(const [i,file] of files.entries()){status.textContent=`Adding ${file.name} (${i+1} of ${files.length})…`;
        try{const r=await fetch('/api/music/folder/upload?name='+encodeURIComponent(file.name),{method:'POST',body:file});const j=await r.json();if(!r.ok)throw Error(j.error||'That file could not be added.');n++;}
        catch(e){status.textContent=e.message;await new Promise(r=>setTimeout(r,1200));}}
      await drawFolder();fcard.querySelector('.music-link-status').textContent=`Added ${n} of ${files.length} file${files.length===1?'':'s'}.`;};
    zone.onclick=()=>pick.click();zone.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick.click();}};
    pick.onchange=()=>{if(pick.files.length)send(pick.files);};
    zone.ondragover=e=>{e.preventDefault();zone.classList.add('over');};zone.ondragleave=()=>zone.classList.remove('over');
    zone.ondrop=e=>{e.preventDefault();zone.classList.remove('over');if(e.dataTransfer.files.length)send(e.dataTransfer.files);};
    const recent=node('details');recent.append(node('summary',`Recently added (${Math.min(f.count,f.recent.length)} of ${f.count})`));const ul=node('ul');for(const r of f.recent)ul.append(node('li',r));recent.append(ul);
    const choose=action('Choose folder…',async()=>{status.textContent='Choose your music folder in the window that opened (it may be behind this one).';const r=await api('folder/choose',{});status.textContent=r.cancelled?'Kept '+f.display+'.':'';if(!r.cancelled)await drawFolder();});
    const canChoose=f.choose_supported??/Mac/i.test(navigator.platform);
    if(!canChoose){choose.disabled=true;choose.dataset.locked='1';choose.title='In progress · native folder chooser for Linux and Windows';}
    const folderHelp=canChoose?'Choose the folder that holds your music (or an empty one to drop songs into). The Hub reads it and never moves or changes your files.':'In progress · saved-folder selection on Linux and Windows. Use Playlists → Files from this device for music during your ride.';
    if(!f.path){fcard.replaceChildren(node('h3','Your music folder'),node('p','No folder chosen yet. '+folderHelp),status,choose);return;}
    fcard.replaceChildren(node('h3','Your music folder'),node('p',`${f.display} · ${f.count} song${f.count===1?'':'s'} · ${f.megabytes} MB`),node('p','The Hub plays the songs in this folder. Pick any folder you like; the Hub reads it and never moves or changes your files.'),zone,pick,status,choose,action('Open music folder',()=>api('folder/open',{})),f.count?recent:node('span'));};
  drawFolder();
  let alive=true;const timers=new Set();
  const destroy=()=>{alive=false;for(const t of timers)clearTimeout(t);};
  root.musicDestroy?.();root.musicDestroy=destroy;
  const report=e=>notice.textContent=e instanceof Error?e.message:e;
  const action=(label,fn)=>{const b=node('button',label,{type:'button'});b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){report(e);}finally{b.disabled=b.dataset.locked==='1';}};return b;};
  // a button that can't do anything yet stays visibly off, with the reason on hover
  const lock=(b,why)=>{b.disabled=true;b.dataset.locked='1';b.title=why;return b;};
  const input=(box,label,key,type='text',value='')=>{const l=node('label',label),i=node('input',undefined,{type,name:key,autocomplete:type==='password'?'off':'on'});i.value=value;l.append(i);box.append(l);return i;};
  const refresh=async()=>{const data=await api('settings');if(!alive)return;cards.replaceChildren();report('Choose the account you want to listen with.');
    for(const p of ['apple','plex']){
      const c=data.providers[p],card=node('section',undefined,{'class':'music-card'}),h=node('h3',names[p]),state=node('p',c.connected?'Connected'+(c.label?' · '+c.label:''):c.ready?'Not connected':'In progress · unavailable until the Hub\'s Apple Music publisher setup is complete. Use your music folder or files from this device.');card.append(h,state);cards.append(card);
      const status=node('div',undefined,{'class':'music-link-status','aria-live':'polite'});card.append(status);
      const selectServer=servers=>{status.replaceChildren(node('p','Choose your Plex server connection.'));if(!servers.length){status.append(node('p','No available personal server was found. Open Plex and make sure your server is running.'));return;}
        const select=node('select',undefined,{'aria-label':'Plex server'});for(const s of servers)select.append(node('option',s.name,{value:s.id}));status.append(select,action('Use this server',async()=>{await api('plex/select',{id:select.value});await refresh();}));};
      if(p==='plex'){
        card.append(node('p','In progress · real-account music and video playback still need verification. Video currently supports browser-playable files; conversion, subtitles and watch progress are not supported.'));
        const connectBtn=action(c.connected?'Reconnect':'Connect',async()=>{
          // Open from the click to avoid popup blocking after the network request.
          const popup=window.open('about:blank','hub-music-link','width=540,height=740');
          let d;try{d=await api('connect',{provider:p});}catch(e){popup?.close();throw e;}
          if(popup)popup.location=d.url;
          status.replaceChildren(node('p','Approve in the sign-in window, or scan this code with your phone.'));
          const a=node('a','Open sign-in',{href:d.url,target:'_blank',rel:'noopener noreferrer'}),img=node('img',undefined,{src:'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(d.qr),alt:'Scan to connect '+names[p],width:'200',height:'200'});
          status.append(img,a);if(d.code)status.append(node('p','Code: '+d.code));
          const poll=async()=>{if(!alive||!status.isConnected)return;try{const r=await api('connect/poll',{provider:p});if(r.connected){popup?.close();selectServer(r.servers);return;}}catch(e){status.replaceChildren(node('p',e.message));return;}
            const timer=setTimeout(()=>{timers.delete(timer);poll();},d.interval*1000);timers.add(timer);};
          const timer=setTimeout(()=>{timers.delete(timer);poll();},d.interval*1000);timers.add(timer);
        });
        card.append(connectBtn);
        const chooser=action('Choose server',async()=>selectServer((await api('plex/servers')).servers));card.append(c.connected||c.has_secret?chooser:lock(chooser,'Connect your Plex account first'));
      } else if(p==='apple') {
        const appleBtn=action('Connect Apple Music',async()=>{const kit=await apple();await kit.authorize();state.textContent='Connected · choose a playlist in Ride';report('Apple Music connected.');});
        card.append(c.ready?appleBtn:lock(appleBtn,'Waiting on the Hub\'s Apple Music developer setup'));
        // Preload after a configured token exists so the next click can open Apple's own sign-in immediately.
        if(c.ready)apple().then(kit=>{if(kit.isAuthorized)state.textContent='Connected in this browser';}).catch(report);
      }
      const off=action('Disconnect',async()=>{if(p==='apple')await (await apple()).unauthorize();await api('forget',{provider:p});window.dispatchEvent(new CustomEvent('hub-music-disconnect',{detail:p}));await refresh();});
      card.append(c.connected||c.has_secret||(p==='apple'&&c.ready)?off:lock(off,'Nothing connected yet'));
    }
    const pending=node('p','iBroadcast and OpenSubsonic · in progress. iBroadcast publisher registration and the OpenSubsonic connection interface are not ready.');cards.append(pending);
    const advanced=node('details',undefined,{'class':'music-advanced'}),summary=node('summary','Publisher / advanced setup');advanced.append(summary,node('p','Athletes use Connect above. App publishers configure Apple Music once. Signing keys do not belong here.'));
    for(const [p,label,key] of [['apple','Signed Apple Music developer token','developer_token'],['plex','Plex server address','server']]){
      const form=node('form'),field=input(form,label,key,key==='developer_token'?'password':'text');let token;
      if(p==='plex')token=input(form,'Plex access token','token','password');form.append(action('Save '+names[p]+' setup',async()=>{await api('settings',{provider:p,[key]:field.value,...(token?{token:token.value}:{})});await refresh();}));form.onsubmit=e=>e.preventDefault();advanced.append(form);
    }root.querySelector(':scope > .music-advanced')?.remove();root.append(advanced);
  };
  try{await refresh();}catch(e){report(e);}return destroy;
}
const target=document.getElementById('hub-music-settings');if(target)mountSettings(target);
