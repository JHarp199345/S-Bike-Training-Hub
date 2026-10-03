"""Run the actual installable MCP archive against an isolated Hub, without site packages."""
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
  bundle = ROOT/f'mcpb/s-bike-hub-mcp-{version}.mcpb'
  if bundle.exists():
   assert hashlib.sha256(bundle.read_bytes()).hexdigest() == json.loads((ROOT/'server.json').read_text())['packages'][0]['fileSha256']
  else:
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
   proc=await asyncio.create_subprocess_exec(runtime,str(entry),cwd=base,env={'PATH':'/usr/bin:/bin','S29_HUB_URL':f'http://127.0.0.1:{port}'},stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,limit=8*1024*1024)
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
    assert len((await rpc(2,'tools/list',{}))['tools'])==55
    await tool(3,'get_program')
    before=(base/'coach.json').read_bytes()
    preview=await tool(4,'preview_program',{'fields':fields}); assert len(preview['starter']['candidates'])==3
    assert (base/'coach.json').read_bytes()==before
    detail=await tool(9,'preview_program',{'fields':fields,'detail_start':coach.today(),'detail_days':2}); assert len(detail['starter']['detail'])==2
    rejected=await rpc(10,'tools/call',{'name':'apply_program','arguments':{}});assert rejected['isError']
    await tool(5,'apply_program',{'draft_id':preview['draft']['id']}); assert coach.load(base/'coach.json')['program_goal']
    await tool(6,'record_checkin',{'date':coach.today(),'legs':3,'feet':2,'shoulders':2,'gut':'go','journal':'Synthetic installation test.'})
    await tool(7,'get_today')
    await tool(8,'get_progress_evidence')
    cal=await tool(11,'get_training_calendar',{'days':7});assert len(cal['calendar'])==7
    evidence=await tool(12,'explain_training_reading',{'metric':'cardio_conditioning'});assert '42' in evidence['formula']
    await tool(13,'get_adaptation_review')
    proc.stdin.close(); await asyncio.wait_for(proc.wait(),5); assert proc.returncode==0,(await proc.stderr.read()).decode()
   finally:
    if proc.returncode is None: proc.kill(); await proc.wait()
    server.close(); await server.wait_closed()
 print('PASS installable bundle: stock runtime, 55 tools, read/preview/apply/check-in/progress; isolated athlete data')
if __name__=='__main__': asyncio.run(main())
