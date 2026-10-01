"""Exercise real Coach handlers against scratch state, without opening a server."""
import asyncio,copy,datetime as dt,json,pathlib,sys,tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,damage,mapserver,recovery


async def main():
    base=pathlib.Path(tempfile.mkdtemp());(base/'rides').mkdir()
    bridge=SimpleNamespace(csv_path=str(base/'rides'/'ride_test.csv'),workouts=[],profile={'ftp':180})
    first=dt.date(2026,1,1);dates=[(first+dt.timedelta(days=i)).isoformat() for i in range(24)]
    doses=[100,100,100]+[0]*21
    d=coach.load(base/'coach.json')
    for i,kind in [(17,'strength'),(18,'balance')]:
        recovery.record_check(d,{'test_date':dates[i],'kind':kind,'name':kind,'symptoms':0,'controlled':True,'gritted':False,
                                'after_ok':True,'followup_date':dates[i+1],'next_day_ok':True},dates[i+1])
    coach.save(d)
    def state(_):
        data=coach.load(base/'coach.json')
        return {'systems':{'impact':{'tissue':{'remodeling':damage.remodeling_response(dates[:21],doses[:21],block=100,
                              reviews=(data.get('run_progression') or {}).get('reviews'))}}}}
    async def call(path,fields=None):
        code,_,body,_=await mapserver.coach_api(bridge,b'GET' if fields is None else b'POST',path,path,json.dumps(fields or {}).encode())
        return code,json.loads(body)
    with patch.object(coach,'today',return_value=dates[20]),patch.object(mapserver,'load_state',side_effect=state):
        code,status=await call('/api/coach/run-progression');assert code==200 and status['review_eligible']
        code,_=await call('/api/coach/run-progression',{'action':'begin_decline','note':'Test review'})
        assert code==200 and coach.load(base/'coach.json')['run_progression']['reviews'][-1]['action']=='begin_decline'
        code,_=await call('/api/coach/run-progression',{'action':'begin_decline'});assert code==400
        code,_=await call('/api/coach/run-progression',{'test_date':dates[23],'kind':'loading'});assert code==400
        # Good tests cannot authorize scheduling while mechanical load is high.
        before=json.loads((base/'coach.json').read_text())
        with patch('loads.readiness',return_value={'running':{'verdict':'rest','why':['mechanical backlog']}}):
            code,result=await call('/api/coach/session/add',{'date':dates[22],'sport':'run','minutes':10})
            assert code==400 and 'unscheduled' in result['error']
            code,result=await call('/api/coach/plan',{'date':dates[22],'sport':'run','minutes':10})
            assert code==400
        assert json.loads((base/'coach.json').read_text())==before
    original_save=recovery.save_forecasts
    with patch.object(coach,'today',return_value=dates[20]),patch.object(mapserver,'load_state',return_value={}),patch.object(mapserver,'done_by_day',return_value={}),patch.object(recovery,'save_forecasts',side_effect=lambda data,f,done:original_save(data,f,done,now=dates[20]+'T08:00:00')):
        code,result=await call('/api/coach/forecast/save',{})
        assert code==200 and result['saved_dates']
        assert coach.load(base/'coach.json')['load_forecasts']
    print('PASS real API persistence, protected review, duplicate rejection and prospective snapshots')

if __name__=='__main__':asyncio.run(main())
