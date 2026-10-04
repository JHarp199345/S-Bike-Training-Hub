"""Opt-in public update metadata; no athlete data and no automatic installs."""
import json
import urllib.request
from pathlib import Path

URL='https://raw.githubusercontent.com/JHarp199345/S-Bike-Training-Hub/main/web/updates.json'
RELEASES='https://github.com/JHarp199345/S-Bike-Training-Hub/releases'

def check(web=None):
    local=json.loads(((web or Path(__file__).parent/'web')/'updates.json').read_text())
    req=urllib.request.Request(URL,headers={'User-Agent':'S-Bike-Training-Hub-Update-Check','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=6) as response:
        raw=response.read(131073)
    if len(raw)>131072:raise ValueError('Update information is too large')
    remote=json.loads(raw);entries=remote.get('entries')
    if not isinstance(entries,list) or not entries or not isinstance(remote.get('latest'),str):raise ValueError('Update information is incomplete')
    ids=[e.get('id') for e in entries if isinstance(e,dict)]
    present=local['latest'] in ids
    newer=remote['latest']!=local['latest'] and (ids.index(local['latest'])>0 if present else str(entries[0].get('date',''))>str(local['entries'][0].get('date','')))
    first=entries[0]
    return {'available':newer,'installed':local['latest'],'latest':remote['latest'],'title':str(first.get('title','Hub update'))[:200],
            'date':str(first.get('date',''))[:10],'changes':[str(c)[:400] for c in first.get('changes',[])[:8]],'url':RELEASES}
