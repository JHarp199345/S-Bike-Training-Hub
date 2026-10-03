"""Program preview/apply through the real API against scratch athlete storage."""
import asyncio,json,pathlib,sys,tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,mapserver,mcp_server
async def main():
 with tempfile.TemporaryDirectory() as tmp:
  base=pathlib.Path(tmp);(base/'rides').mkdir();d=coach.load(base/'coach.json')
  coach.set_sessions(d,'2026-10-03',[{'sport':'swim','minutes':25}]);coach.save(d)
  bridge=SimpleNamespace(csv_path=str(base/'rides'/'example.csv'),workouts=[],profile={'ftp':150})
  fields={'start':'2026-10-02','horizon_days':42,'sport':'general','hours':4,'priorities':{'ride':'improve','gym':'maintain','swim':'maintain','run':'pause'},'assessment':'existing','starter_enabled':True,'starter_equipment':'barbell','strength_anchors':[{'name':n,'weight':w,'unit':'lb','reps':8,'rir':3} for n,w in [('BB squat',95),('BB bench press',65),('BB row',55)]]}
  async def call(action):
   code,_,body,_=await mapserver.coach_api(bridge,b'POST','/api/coach/program-builder','/api/coach/program-builder',json.dumps({**fields,'action':action}).encode());return code,json.loads(body)
  with patch.object(coach,'today',return_value='2026-10-02'),patch.object(mapserver,'load_state',return_value={}):
   before=(base/'coach.json').read_text();code,r=await call('preview');assert code==200,r
   assert (base/'coach.json').read_text()==before
   assert len(r['starter']['candidates'])==3
   lifts=[l for p in r['starter']['plans'].values() for s in p['sessions'] for l in s.get('lifts',[]) if l['kind']=='barbell'];assert lifts and all(l['weight'] is not None for l in lifts)
   code,r=await call('accept');assert code==200,r
   saved=coach.load(base/'coach.json');assert saved['plans']['2026-10-03']==d['plans']['2026-10-03'];assert saved['program_forecast_history']
  with patch.object(mcp_server,'call',return_value={}) as c:
   mcp_server.t_program_preview({'fields':fields});assert c.call_args.args[1]['action']=='preview'
   mcp_server.t_program_apply({'fields':fields});assert c.call_args.args[1]['action']=='accept'
 print('PASS real preview isolation, three forecasts, weighted starters, apply preservation and MCP dispatch')
if __name__=='__main__':asyncio.run(main())
