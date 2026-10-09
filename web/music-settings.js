import {api,node} from './music-common.js';
// Music settings: your private folder of audio and video. Nothing else to connect.
export async function mountSettings(root) {
  root.classList.add('hub-music');root.replaceChildren();
  root.append(node('p','Your audio and video files live in one private folder on this computer. Choose it once, drop files in, then open the Library on the Ride screen. Media is independent of your workout.'));
  const notice=node('p','',{'role':'status'});
  const action=(label,fn)=>{const b=node('button',label,{type:'button'});b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){notice.textContent=e.message;}finally{b.disabled=b.dataset.locked==='1';}};return b;};
  const fcard=node('section',undefined,{'class':'music-card music-folder'});root.append(fcard,notice);
  const drawFolder=async()=>{let f;try{f=await api('folder');}catch(e){fcard.replaceChildren(node('h3','Your media folder'),node('p',e.message));return;}
    const zone=node('div','Drop audio or video files here, or click to choose',{'class':'music-drop','tabindex':'0','role':'button','aria-label':'Add audio or video files to your folder'});
    const pick=node('input',undefined,{type:'file',multiple:'',accept:'audio/*,video/*,.mp3,.m4a,.aac,.flac,.wav,.aif,.aiff,.ogg,.opus,.mp4,.m4v,.webm,.mov',hidden:''});
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
    const choose=action('Choose folder…',async()=>{status.textContent='Choose your folder in the window that opened (it may be behind this one).';const r=await api('folder/choose',{});status.textContent=r.cancelled?'Kept '+f.display+'.':'';if(!r.cancelled)await drawFolder();});
    const canChoose=f.choose_supported??/Mac/i.test(navigator.platform);
    if(!canChoose){choose.disabled=true;choose.dataset.locked='1';choose.title='The folder chooser works on a Mac. Elsewhere, set HUB_MUSIC_FOLDER.';}
    const help='Audio: mp3, m4a, flac, wav, aiff, ogg. Video: mp4, m4v, webm, mov (browser-playable). The Hub reads the folder and never moves or changes your files; nothing is uploaded anywhere.';
    if(!f.path){fcard.replaceChildren(node('h3','Your media folder'),node('p','No folder chosen yet. '+help),status,choose);return;}
    fcard.replaceChildren(node('h3','Your media folder'),node('p',`${f.display} · ${f.count} file${f.count===1?'':'s'} · ${f.megabytes} MB`),node('p',help),zone,pick,status,choose,action('Open folder',()=>api('folder/open',{})),f.count?recent:node('span'));};
  drawFolder();
  const destroy=()=>{};root.musicDestroy?.();root.musicDestroy=destroy;return destroy;
}
const target=document.getElementById('hub-music-settings');if(target)mountSettings(target);
