"""Manual and assistant workflows share saved swim targets and optional recall."""
import asyncio,datetime as dt,json,pathlib,sys,tempfile,copy
from types import SimpleNamespace
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/demo')]
import coach,mapserver,swim_workouts as sw,fitwrite,mcp_server
from test_swim_timing import TEXT
async def main():
 with tempfile.TemporaryDirectory() as temp:
  base=pathlib.Path(temp);(base/'rides').mkdir();(base/'activities').mkdir()
  date=coach.today();start=dt.datetime.fromisoformat(date+'T06:00').timestamp()
  # Coarse drill lap, regular lengths and a coarse backstroke lap; no invented splits.
  w=fitwrite.Writer();t=start
  for distance,seconds in [(365.76,960),(365.76,420),(91.44,130),(365.76,390),(91.44,120),(365.76,500),(182.88,300)]:
   w.add('lap',start_time=t,timestamp=t+seconds,total_distance=distance,total_timer_time=seconds);t+=seconds
  w.add('session',sport=5,start_time=start,timestamp=t,total_distance=1828.8,total_timer_time=t-start,pool_length=22.86,avg_heart_rate=130,max_heart_rate=160)
  (base/'activities/swim_test.fit').write_bytes(w.bytes())
  bridge=SimpleNamespace(csv_path=base/'rides/ride_test.csv',profile={'ftp':180},workouts=[])
  async def api(path,data=None):
   code,_,body,_=await mapserver.coach_api(bridge,b'GET' if data is None else b'POST',path,path.split('?')[0],b'' if data is None else json.dumps(data).encode())
   return code,json.loads(body)
  with patch.object(mapserver,'capture_program_forecast'):
   code,p=await api('/api/coach/swim/preview',{'text':TEXT,'minutes':55,'pool_length':25});assert code==200 and p['valid']
   _,bad=await api('/api/coach/swim/preview',{'text':TEXT,'minutes':30});assert not bad['valid']
   code,_=await api('/api/coach/session/add',{'date':date,'name':'Timing test','sport':'swim','minutes':55,'swim_recipe':{'fields':p['fields'],'unit':'yd','pool_length':25}});assert code==200
   code,x=await api('/api/coach/recording-link',{'activity_id':'swim_test','mode':'scheduled','session_index':0,'save':True});assert code==200,x
   code,r=await api('/api/coach/activity-report?activity_id=swim_test');assert code==200 and r['swim_timing']['grade']['status']=='As or better than expected',r
   assert r['swim_analysis']['planned_mix']['parts'][0]['percent']==15
   assert r['swim_analysis']['watch_mix']['parts'][0]['stroke']=='unknown'
   assert r['swim_analysis']['history'][-1]['current'] and r['swim_analysis']['response']['avg_hr']==130
   assert r['swim_timing']['rows'][0]['combined'] and r['swim_timing']['rows'][0]['actual_seconds']==960
   code,_=await api('/api/coach/swim/splits',{'activity_id':'swim_test','splits':[{'set_index':0,'seconds':800},{'set_index':1,'seconds':130}]});assert code==200
   _,r=await api('/api/coach/activity-report?activity_id=swim_test');assert r['swim_timing']['reported_splits'][0]['actual_seconds']==800 and r['swim_timing']['rows'][0]['actual_seconds']==960
   d=coach.load(base/'coach.json');assert d['swim_timing_baselines']['swim_test']['recipe']['completion_goal_minutes']==39
   # API and MCP forward precisely the same payload, not a separately written record.
   with patch.object(mcp_server,'call',return_value={'saved':True}) as called:
    mcp_server.t_swim_splits({'activity_id':'swim_test','splits':[{'set_index':0,'seconds':800}]})
    assert called.call_args.args==('/api/coach/swim/splits',{'activity_id':'swim_test','splits':[{'set_index':0,'seconds':800}]})
 print('PASS shared manual/API/MCP swim timing, saved plan snapshot, coarse drill watch block and athlete splits')
asyncio.run(main())
