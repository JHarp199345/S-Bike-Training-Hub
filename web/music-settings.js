import {api,apple,node,names} from './music-common.js';
export async function mountSettings(root) {
  root.classList.add('hub-music');root.replaceChildren();
  const intro=node('p','Connect once, then choose a playlist in Ride. Your account access stays on this computer. Music is independent of your workout.');root.append(intro);
  const privacy=node('details');privacy.append(node('summary','Setup and privacy'),node('p','Your service access is saved locally in the Hub’s private music settings. Apple sign-in is handled by MusicKit in your browser. Local audio files stay in your browser and are not uploaded.'),node('p','Your chosen services receive sign-in, library, and playback requests. iBroadcast also receives play and skip history. Music is not sent to your coaching assistant or logged as a workout. Disconnect removes the Hub’s saved access; revoke access in the service account too if needed.'),node('p','Plex needs your own reachable server. OpenSubsonic needs your server account or API key. iBroadcast and Apple Music require the Hub publisher’s app setup first; athletes do not need developer accounts.'),node('a','Plex terms and privacy',{href:'https://www.plex.tv/about/privacy-legal/',target:'_blank',rel:'noopener noreferrer'}));root.append(privacy);
  const notice=node('p','Loading connections…',{'role':'status'}),cards=node('div',undefined,{'class':'music-cards'});root.append(notice,cards);
  let alive=true;const timers=new Set();
  const destroy=()=>{alive=false;for(const t of timers)clearTimeout(t);};
  root.musicDestroy?.();root.musicDestroy=destroy;
  const report=e=>notice.textContent=e instanceof Error?e.message:e;
  const action=(label,fn)=>{const b=node('button',label,{type:'button'});b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){report(e);}finally{b.disabled=b.dataset.locked==='1';}};return b;};
  // a button that can't do anything yet stays visibly off, with the reason on hover
  const lock=(b,why)=>{b.disabled=true;b.dataset.locked='1';b.title=why;return b;};
  const input=(box,label,key,type='text',value='')=>{const l=node('label',label),i=node('input',undefined,{type,name:key,autocomplete:type==='password'?'off':'on'});i.value=value;l.append(i);box.append(l);return i;};
  const refresh=async()=>{const data=await api('settings');if(!alive)return;cards.replaceChildren();report('Choose the account you want to listen with.');
    for(const p of ['plex','apple','ibroadcast','subsonic']){
      const c=data.providers[p],card=node('section',undefined,{'class':'music-card'}),h=node('h3',names[p]),state=node('p',c.connected?'Connected'+(c.label?' · '+c.label:''):c.ready?'Not connected':'Not available yet: waiting on the Hub\'s app registration with '+names[p]+'. Plex, OpenSubsonic and your own music files work now.');card.append(h,state);cards.append(card);
      const status=node('div',undefined,{'class':'music-link-status','aria-live':'polite'});card.append(status);
      const selectServer=servers=>{status.replaceChildren(node('p','Choose your Plex server connection.'));if(!servers.length){status.append(node('p','No available personal server was found. Open Plex and make sure your server is running.'));return;}
        const select=node('select',undefined,{'aria-label':'Plex server'});for(const s of servers)select.append(node('option',s.name,{value:s.id}));status.append(select,action('Use this server',async()=>{await api('plex/select',{id:select.value});await refresh();}));};
      if(p==='plex'||p==='ibroadcast'){
        const connectBtn=action(c.connected?'Reconnect':'Connect',async()=>{
          // Open from the click to avoid popup blocking after the network request.
          const popup=window.open('about:blank','hub-music-link','width=540,height=740');
          let d;try{d=await api('connect',{provider:p});}catch(e){popup?.close();throw e;}
          if(popup)popup.location=d.url;
          status.replaceChildren(node('p','Approve in the sign-in window, or scan this code with your phone.'));
          const a=node('a','Open sign-in',{href:d.url,target:'_blank',rel:'noopener noreferrer'}),img=node('img',undefined,{src:'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(d.qr),alt:'Scan to connect '+names[p],width:'200',height:'200'});
          status.append(img,a);if(d.code)status.append(node('p','Code: '+d.code));
          const poll=async()=>{if(!alive||!status.isConnected)return;try{const r=await api('connect/poll',{provider:p});if(r.connected){popup?.close();if(p==='plex')selectServer(r.servers);else await refresh();return;}}catch(e){status.replaceChildren(node('p',e.message));return;}
            const timer=setTimeout(()=>{timers.delete(timer);poll();},d.interval*1000);timers.add(timer);};
          const timer=setTimeout(()=>{timers.delete(timer);poll();},d.interval*1000);timers.add(timer);
        });
        card.append(c.ready?connectBtn:lock(connectBtn,'Waiting on the Hub\'s app registration'));
        if(p==='plex'){const chooser=action('Choose server',async()=>selectServer((await api('plex/servers')).servers));card.append(c.connected||c.has_secret?chooser:lock(chooser,'Connect your Plex account first'));}
      } else if(p==='apple') {
        const appleBtn=action('Connect Apple Music',async()=>{const kit=await apple();await kit.authorize();state.textContent='Connected · choose a playlist in Ride';report('Apple Music connected.');});
        card.append(c.ready?appleBtn:lock(appleBtn,'Waiting on the Hub\'s Apple Music developer setup'));
        // Preload after a configured token exists so the next click can open Apple's own sign-in immediately.
        if(c.ready)apple().then(kit=>{if(kit.isAuthorized)state.textContent='Connected in this browser';}).catch(report);
      } else {
        const form=node('form'),server=input(form,'Server address','server','url',c.server),mode=node('select',undefined,{name:'auth_mode','aria-label':'Account type'});
        mode.append(node('option','Username and password',{value:'password'}),node('option','API key',{value:'api_key'}));mode.value=c.auth_mode;form.append(node('label','Account access'),mode);
        const user=input(form,'Username','username','text',c.username),pass=input(form,'Password · leave blank to keep saved access','password','password'),key=input(form,'API key · leave blank to keep saved access','api_key','password');
        const change=()=>{user.parentNode.hidden=pass.parentNode.hidden=mode.value==='api_key';key.parentNode.hidden=mode.value!=='api_key';};mode.onchange=change;change();
        form.append(action('Save connection',async()=>{await api('settings',{provider:p,server:server.value,auth_mode:mode.value,username:user.value,password:pass.value,api_key:key.value});await api('playlists?provider='+p);await refresh();report('Music server connected.');}));form.onsubmit=e=>e.preventDefault();card.append(form);
      }
      const off=action('Disconnect',async()=>{if(p==='apple')await (await apple()).unauthorize();await api('forget',{provider:p});window.dispatchEvent(new CustomEvent('hub-music-disconnect',{detail:p}));await refresh();});
      card.append(c.connected||c.has_secret||(p==='apple'&&c.ready)?off:lock(off,'Nothing connected yet'));
    }
    const advanced=node('details'),summary=node('summary','Publisher / advanced setup');advanced.append(summary,node('p','Athletes use Connect above. App publishers configure iBroadcast registration and Apple Music once. Signing keys do not belong here.'));
    for(const [p,label,key] of [['ibroadcast','iBroadcast app client ID','client_id'],['apple','Signed Apple Music developer token','developer_token'],['plex','Plex server address','server']]){
      const form=node('form'),field=input(form,label,key,key==='developer_token'?'password':'text');let token;
      if(p==='plex')token=input(form,'Plex access token','token','password');form.append(action('Save '+names[p]+' setup',async()=>{await api('settings',{provider:p,[key]:field.value,...(token?{token:token.value}:{})});await refresh();}));form.onsubmit=e=>e.preventDefault();advanced.append(form);
    }root.querySelector(':scope > details')?.remove();root.append(advanced);
  };
  try{await refresh();}catch(e){report(e);}return destroy;
}
const target=document.getElementById('hub-music-settings');if(target)mountSettings(target);
