"""Real Hub handler and MCP adapter, with only synthetic data and recordings."""
import asyncio,datetime as dt,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import coach,mapserver,mcp_server
async def main():
 with tempfile.TemporaryDirectory() as tmp:
  base=Path(tmp);(base/'rides').mkdir();date=coach.today();previous=(dt.date.fromisoformat(date)-dt.timedelta(days=1)).isoformat()
  d=coach.load(base/'coach.json')
  coach.set_sessions(d,date,[{'sport':'ride','name':'Ride','minutes':40},{'sport':'swim','name':'Swim','minutes':20}]);coach.save(d)
  bridge=SimpleNamespace(csv_path=base/'rides/demo.csv',profile={'ftp':150},workouts=[])
  async def api(path,body=None):
   result=await mapserver.coach_api(bridge,b'POST' if body is not None else b'GET',path,path.split('?')[0],json.dumps(body or {}).encode())
   return result[0],json.loads(result[2])
  with patch.object(mapserver,'load_state',return_value={}),patch.object(mapserver,'capture_program_forecast'),patch.object(mapserver,'done_by_day',return_value={date:[{'sport':'bike','minutes':40}]}):
   code,result=await api('/api/coach/session/action',{'date':date,'index':1,'action':'skip'});assert code==200,result
   code,result=await api('/api/coach/session/action',{'date':date,'index':0,'action':'skip'});assert code==400,result
   code,result=await api('/api/coach/week?date='+date)
   selected=next(x for x in result['week'] if x['date']==date)
   assert selected['sessions'][1]['sport']=='swim' and selected['sessions'][1]['skipped_id']
   assert selected['sessions'][0]['completion'] and not selected['recovery_day']
  with patch.object(coach,'today',return_value=(dt.date.fromisoformat(date)+dt.timedelta(days=1)).isoformat()),patch.object(mapserver,'done_by_day',return_value={date:[{'sport':'bike','minutes':40}]}):
   code,a=await api('/api/coach/adherence?days=28&date='+coach.today());assert code==200
   assert a['counts']['completed']==1 and a['counts']['cancelled']==1 and a['prescribed_minutes']==60
   assert a['plan_revision_count']==0 and a['completion_share']==.667
  with patch.object(mcp_server,'call',return_value=a) as call:
   assert mcp_server.t_schedule_adherence({'days':28,'date':date})==a
   assert call.call_args.args[0]=='/api/coach/adherence?date='+date+'&days=28'
asyncio.run(main())
print('PASS real cancellation API preserves another completed session, refuses cancelling actuals, retains icons and exposes separate adherence through MCP')
