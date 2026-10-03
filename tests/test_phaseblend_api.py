"""Real settings API against scratch storage; preview must not write athlete state."""
import asyncio,json,pathlib,sys,tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,mapserver

async def main():
    with tempfile.TemporaryDirectory() as tmp:
        base=pathlib.Path(tmp);(base/'rides').mkdir();d=coach.load(base/'coach.json')
        coach.set_sessions(d,'2026-10-06',[{'sport':'swim','minutes':40}]);coach.save(d)
        bridge=SimpleNamespace(csv_path=str(base/'rides'/'test.csv'),workouts=[],profile={'ftp':180})
        async def call(fields=None):
            code,_,body,_=await mapserver.coach_api(bridge,b'GET' if fields is None else b'POST','/api/coach/phase-profiles','/api/coach/phase-profiles',json.dumps(fields or {}).encode())
            return code,json.loads(body)
        with patch.object(coach,'today',return_value='2026-10-02'),patch.object(mapserver,'load_state',return_value={}):
            before=(base/'coach.json').read_text()
            code,r=await call({'action':'preview','start':'2026-10-05','weeks':4,'profile':'ride'})
            assert code==200 and r['current']['enabled'] and r['current']['sports']['run']['role']=='hold'
            assert (base/'coach.json').read_text()==before
            code,r=await call({'start':'2026-10-05','weeks':4,'profile':'ride'});assert code==200
            saved=coach.load(base/'coach.json');assert saved['plans']==d['plans'];assert len(saved['phase_profiles'])==1
            code,r=await call({'start':'2026-10-05','weeks':4,'profile':'gym'});assert code==200
            assert len(coach.load(base/'coach.json')['phase_profiles'])==1
            before=(base/'coach.json').read_text()
            code,r=await call({'start':'2026-10-12','weeks':4,'profile':'swim'});assert code==400
            assert (base/'coach.json').read_text()==before
            code,r=await call({'start':'2026-11-02','weeks':4,'profile':'swim'});assert code==200
            assert len(coach.load(base/'coach.json')['phase_profiles'])==2
    print('PASS preview isolation, saved phases, safe edits, overlap rejection and preserved sessions')

if __name__=='__main__':asyncio.run(main())
