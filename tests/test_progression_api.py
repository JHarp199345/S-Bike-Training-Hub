"""New feedback routes persist only scratch athlete data."""
import asyncio,json,pathlib,sys,tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,mapserver,progression

async def main():
    with tempfile.TemporaryDirectory() as tmp:
        base=pathlib.Path(tmp);(base/'rides').mkdir()
        b=SimpleNamespace(csv_path=str(base/'rides'/'test.csv'),workouts=[],profile={'ftp':180})
        d=coach.load(base/'coach.json');d['training_block']={'start':'2026-10-05','weeks':4,'status':'active'}
        coach.set_sessions(d,'2026-10-01',[{'sport':'swim','minutes':45,'name':'Easy swim'}]);coach.save(d)
        async def call(path,fields=None):
            code,_,body,_=await mapserver.coach_api(b,b'GET' if fields is None else b'POST',path,path,json.dumps(fields or {}).encode())
            return code,json.loads(body)
        with patch.object(coach,'today',return_value='2026-10-02'),patch.object(mapserver,'done_by_day',return_value={'2026-10-01':[{'sport':'swim','minutes':45}]}),patch.object(mapserver,'load_state',return_value={}),patch.object(mapserver,'capture_program_forecast'),patch.object(progression,'daily_adapt',return_value=[]):
            code,_=await call('/api/coach/progression',{'action':'enable'});assert code==200
            fields={'date':'2026-10-01','session_index':0,'effort':'too_easy','symptoms':[{'location':'achilles','side':'both','severity':2}]}
            code,r=await call('/api/coach/session-report',fields);assert code==200 and r['assessment']['decision']=='regression_candidate'
            fields['symptoms']=[];code,_=await call('/api/coach/session-report',fields);assert code==200
            code,r=await call('/api/coach/progression');assert r['active_symptoms'], 'Editing effort must not silently clear symptoms'
            code,_=await call('/api/coach/progression',{'action':'resolve_symptom','report_key':'2026-10-01:0','resolved':True});assert code==200
            code,r=await call('/api/coach/progression');assert not r['active_symptoms']
            fields['symptoms']=[{'location':'achilles','side':'both','severity':3}]
            code,_=await call('/api/coach/session-report',fields);assert code==200
            code,r=await call('/api/coach/progression');assert r['active_symptoms'], 'New discomfort must reopen the restriction'
            fields['date']='2026-10-03';code,_=await call('/api/coach/session-report',fields);assert code==400
        assert coach.load(base/'coach.json')['training_block']['progression']['enabled']
    print('PASS feedback API, symptom persistence, explicit resolution, recurrence and future-report rejection')

if __name__=='__main__':asyncio.run(main())
