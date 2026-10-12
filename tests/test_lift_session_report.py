"""A lift logged in the hub (activity id lift-<date>-<n>) has no watch file; its session report still saves."""
import asyncio,json,pathlib,sys,tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,mapserver,progression

async def main():
    with tempfile.TemporaryDirectory() as tmp:
        base=pathlib.Path(tmp);(base/'rides').mkdir()
        b=SimpleNamespace(csv_path=str(base/'rides'/'test.csv'),workouts=[],profile={'ftp':180})
        d=coach.load(base/'coach.json');coach.set_sessions(d,'2026-10-01',[{'sport':'gym','minutes':45,'name':'Lower body'}]);coach.save(d)
        done={'2026-10-01':[{'sport':'gym','minutes':45,'activity_id':'lift-2026-10-01-0'}]}
        async def call(path,fields):
            code,_,body,_=await mapserver.coach_api(b,b'POST',path,path,json.dumps(fields).encode())
            return code,json.loads(body)
        with patch.object(coach,'today',return_value='2026-10-02'),patch.object(mapserver,'done_by_day',return_value=done),patch.object(mapserver,'load_state',return_value={}),patch.object(mapserver,'capture_program_forecast'),patch.object(progression,'daily_adapt',return_value=[]):
            code,r=await call('/api/coach/session-report',{'date':'2026-10-01','session_index':0,'effort':'as_intended','symptoms':[],'activity_id':'lift-2026-10-01-0'})
            assert code==200,r
        assert any(v.get('effort')=='as_intended' for v in coach.load(base/'coach.json').get('training_feedback',{}).values())
    print('PASS a hub-logged lift saves its session report without a watch file')

if __name__=='__main__':asyncio.run(main())
