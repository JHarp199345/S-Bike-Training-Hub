"""Run the actual installable MCP archive against an isolated Hub, without site packages."""
import datetime as dt
import asyncio, hashlib, json, os, pathlib, sys, tempfile, zipfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import coach, mapserver, panel, rider, workouts
ROOT = pathlib.Path(__file__).resolve().parent.parent

async def main():
 with tempfile.TemporaryDirectory(prefix='sbike-bundle-test-') as temp:
  base = pathlib.Path(temp); (base/'rides').mkdir(); (base/'workouts').mkdir()
  version=json.loads((ROOT/'mcpb/manifest.json').read_text())['version']
  override=os.environ.get('S_BIKE_TEST_BUNDLE')
  bundle = pathlib.Path(override) if override else ROOT/f'mcpb/s-bike-hub-mcp-{version}.mcpb'
  if bundle.exists() and not override:
   assert hashlib.sha256(bundle.read_bytes()).hexdigest() == json.loads((ROOT/'server.json').read_text())['packages'][0]['fileSha256']
  elif not bundle.exists():
   if override: raise FileNotFoundError(bundle)
   # Release archives are ignored by Git; a fresh checkout tests the same source layout.
   bundle=base/'source-test.mcpb'
   with zipfile.ZipFile(bundle,'w') as z:
    z.write(ROOT/'mcpb/manifest.json','manifest.json')
    z.write(ROOT/'mcp_server.py','server/mcp_server.py')
  with zipfile.ZipFile(bundle) as z: z.extractall(base/'extension')
  manifest = json.loads((base/'extension/manifest.json').read_text())
  entry = pathlib.Path(os.environ.get('S_BIKE_TEST_INSTALLED_SERVER', base/'extension/server/mcp_server.py'))
  assert entry.read_bytes() == (ROOT/'mcp_server.py').read_bytes()
  assert manifest['server']['mcp_config']['command'] == 'python3'
  profile={'ftp':150, 'weight_kg':75, 'hr_rest':60, 'hr_max':180}
  (base/'profile.json').write_text(json.dumps(profile))
  d=coach.load(base/'coach.json'); coach.save(d)
  bridge=SimpleNamespace(csv_path=base/'rides/example.csv', profile=profile, workouts=[], args=SimpleNamespace(no_bike=True),event=lambda *a:None)
  fields={'start':coach.today(),'horizon_days':42,'sport':'general','hours':4,'priorities':{'ride':'improve','gym':'maintain','swim':'maintain','run':'pause'},'assessment':'existing','starter_enabled':True,'starter_equipment':'barbell','strength_anchors':[{'name':n,'weight':w,'unit':'lb','reps':8,'rir':3} for n,w in [('BB squat',95),('BB bench press',65),('BB row',55)]]}
  with patch.object(mapserver,'load_state',return_value={}),patch.object(workouts,'FOLDER',base/'workouts'),patch.object(rider,'PATH',base/'profile.json'):
   server=await panel.serve(bridge,0,lan=False); port=server.sockets[0].getsockname()[1]
   # Apple's stock Python 3.9 and a minimal desktop-style PATH, with no repo cwd/dependencies.
   runtime='/usr/bin/python3' if pathlib.Path('/usr/bin/python3').exists() else sys.executable
   proc=await asyncio.create_subprocess_exec(runtime,str(entry),cwd=base,env={'PATH':'/usr/bin:/bin','S29_HUB_URL':f'http://127.0.0.1:{port}',**({k:os.environ[k] for k in ('SYSTEMROOT','SYSTEMDRIVE','TEMP','TMP') if k in os.environ} if os.name=='nt' else {})},stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,limit=8*1024*1024)
   async def rpc(i, method, params):
    proc.stdin.write((json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\n').encode()); await proc.stdin.drain()
    msg=json.loads(await asyncio.wait_for(proc.stdout.readline(),30)); assert 'error' not in msg,msg
    return msg['result']
   async def tool(i,name,args={}):
    r=await rpc(i,'tools/call',{'name':name,'arguments':args}); assert not r.get('isError'),r
    print(name, len(r['content'][0]['text'].encode()), 'response bytes')
    out=json.loads(r['content'][0]['text'])
    if name in ('preview_program','apply_program','get_today','get_training_calendar','explain_training_reading'):assert len(r['content'][0]['text'].encode())<100000, 'AI response budget exceeded'
    return out
   try:
    await rpc(1,'initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'installation-test','version':'1'}})
    listed=(await rpc(2,'tools/list',{}))['tools']
    import mcp_server
    assert {t['name'] for t in listed}=={t['name'] for t in mcp_server.handle({'id':1,'method':'tools/list'})['tools']}
    await tool(3,'get_program')
    before=(base/'coach.json').read_bytes()
    preview=await tool(4,'preview_program',{'fields':fields}); assert len(preview['starter']['candidates'])==3
    assert (base/'coach.json').read_bytes()==before
    detail=await tool(9,'preview_program',{'fields':fields,'detail_start':coach.today(),'detail_days':2}); assert len(detail['starter']['detail'])==2
    rejected=await rpc(10,'tools/call',{'name':'apply_program','arguments':{}});assert rejected['isError']
    await tool(5,'apply_program',{'draft_id':preview['draft']['id']}); assert coach.load(base/'coach.json')['program_goal']
    checked=await tool(6,'record_checkin',{'date':coach.today(),'legs':3,'feet':2,'shoulders':2,'gut':'go','journal':'Synthetic installation test.'})
    assert checked['attention'] and 'items' in checked['attention'] and checked['attention']['routine'],checked.get('attention')
    needs=await tool(17,'get_attention',{'days':7}); assert needs['days']==7 and isinstance(needs['items'],list)
    prompt=await rpc(18,'prompts/get',{'name':'daily-check-in'}); assert 'attention list' in prompt['messages'][0]['content']['text']
    await tool(7,'get_today')
    await tool(8,'get_progress_evidence')
    cal=await tool(11,'get_training_calendar',{'days':7});assert len(cal['calendar'])==7
    evidence=await tool(12,'explain_training_reading',{'metric':'cardio_conditioning'});assert '42' in evidence['formula']
    await tool(13,'get_adaptation_review')
    outlook=await tool(14,'get_coaching_review',{'days':14});assert outlook['outlook']['days']==14
    future=(dt.date.fromisoformat(coach.today())+dt.timedelta(days=2)).isoformat()
    reviewed=await tool(15,'preview_coaching_change',{'kind':'calendar','changes':[{'date':future,'sessions':[]}],'note':'Synthetic reviewed rest replacement'})
    assert not reviewed['violations']
    await tool(16,'apply_coaching_change',{'draft_id':reviewed['draft_id'],'approved':True})
    assert not coach.load(base/'coach.json')['plans'][future]['sessions']

    lifts=[{'name':'BB bench press','kind':'barbell','sets':2,'reps':8,'weight':65,'unit':'lb','hold':3,'regions':{'pecs':100}},
           {'name':'Cable curl hold','kind':'cable','sets':2,'seconds':10,'weight':15,'unit':'lb','regions':{'biceps':100}}]
    await tool(19,'evaluate_lift_session',{'lifts':lifts})
    planned=await tool(20,'plan_lift_session',{'date':coach.today(),'name':'Synthetic hold check','lifts':lifts})
    gyms=[s for s in planned['plan']['sessions'] if s.get('sport')=='gym' and s.get('lifts')]
    index=next(i for i,s in enumerate(gyms) if s['name']=='Synthetic hold check')
    logged=await tool(21,'log_lift_session',{'date':coach.today(),'session_index':index,'done':[{'hold':6,'failure':True},{'seconds':20}],'rpe':7,'wellness':8})
    rows=logged['log']['lifts']
    assert rows[0]['hold']==6 and rows[0]['failure'] is True,rows
    assert rows[1]['seconds']==20,rows

    context=(await tool(22,'get_training_calendar',{'days':1}))['calendar'][0]['sessions'][0]
    unchanged=coach.load(base/'coach.json')['plans'][coach.today()]['sessions'][0].copy()
    updated=await tool(23,'update_session_explanation',{'date':coach.today(),'session_index':0,'text':'Easy work supports this recovery week.','context_token':context['explanation']['context_token']})
    assert updated['changed']
    stored=coach.load(base/'coach.json')['plans'][coach.today()]['sessions'][0].copy();stored.pop('coaching_context')
    assert stored==unchanged,'Explanation update changed the workout dose'
    repeat=await tool(24,'update_session_explanation',{'date':coach.today(),'session_index':0,'text':'Easy work supports this recovery week.','context_token':context['explanation']['context_token']});assert not repeat['changed']

    proc.stdin.close(); await asyncio.wait_for(proc.wait(),5); assert proc.returncode==0,(await proc.stderr.read()).decode()
   finally:
    if proc.returncode is None: proc.kill(); await proc.wait()
    server.close(); await server.wait_closed()
 print('PASS installable bundle: stock runtime, current tool contracts, read/preview/apply/check-in/progress; isolated athlete data')
if __name__=='__main__': asyncio.run(main())
