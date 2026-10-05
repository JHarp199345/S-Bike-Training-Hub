"""Running prescriptions stay canonical, gated and separate from completed work."""
import asyncio, copy, json, pathlib, sys, tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import run_workouts as rw, coach, mapserver, routes, map_paths
fields={'warmup':'5 minutes walk','main':'6 x (2 minutes jog zone 2 / 1 minute walk)','cooldown':'5 minutes walk'}
p=rw.parse(fields)
assert p['valid'] and p['minutes']==28 and len(p['stages'])==14
assert [r['kind'] for r in p['stages'][1:5]]==['run','walk','run','walk']
assert rw.exposure(p,{'weight_kg':120})['estimated_steps']==3480
assert rw.exposure(p,{'weight_kg':120})['impact_points'] is None
q=rw.parse({'main':'2 km jog pace 6:00/km 160 spm'})
assert q['minutes']==12 and rw.exposure(q,{'weight_kg':120})['impact_points']>0
assert rw.exposure(q,{'weight_kg':float('nan')})['impact_points'] is None
assert not rw.parse({'main':'5 minutes run 3 minutes walk'})['valid']
assert not rw.parse({'main':'5 minutes run 180–130 bpm'})['valid']
for bad in [True,0,11]:
 try: rw.parse(fields,bad)
 except ValueError: pass
 else: raise AssertionError(bad)
async def main():
 with tempfile.TemporaryDirectory() as tmp:
  base=pathlib.Path(tmp);(base/'rides').mkdir();d=coach.load(base/'coach.json');coach.save(d)
  br=SimpleNamespace(csv_path=str(base/'rides'/'example.csv'),profile={'weight_kg':120,'ftp':180})
  async def api(path,req):return await mapserver.coach_api(br,b'POST',path,path,json.dumps(req).encode())
  req={'date':'2026-10-05','sport':'run','name':'Run walk','minutes':28,'run_recipe':p}
  with patch.object(mapserver,'capture_program_forecast'),patch.object(mapserver,'done_by_day',return_value={}),patch('training_block.running_gate',return_value={'status':'open_for_review'}):
   before=copy.deepcopy(d)
   code,_,body,_=await api('/api/coach/run/preview',{'fields':fields});assert code==200,body
   assert coach.load(base/'coach.json')==before
   code,_,body,_=await api('/api/coach/session/add',req);assert code==200,body
   saved=coach.load(base/'coach.json');assert saved['plans'][req['date']]['sessions'][0]['run_recipe']['minutes']==28
   code,_,body,_=await api('/api/coach/session/add',dict(req,index=0,name='Edited'));assert code==200,body
   assert len(coach.load(base/'coach.json')['plans'][req['date']]['sessions'])==1
   stable=(base/'coach.json').read_bytes()
   for bad in [dict(req,sport='gym'),dict(req,minutes=25),dict(req,minutes=30)]:
    code,_,body,_=await api('/api/coach/session/add',bad);assert code==400,body;assert (base/'coach.json').read_bytes()==stable
  with patch('training_block.running_gate',return_value={'status':'hold','reasons':['load']}):
   code,_,body,_=await api('/api/coach/session/add',req);assert code==400 and b'unscheduled' in body,body
  with patch.object(mapserver,'done_by_day',return_value={req['date']:[{'sport':'run'}]}),patch('training_block.running_gate',return_value={'status':'open_for_review'}):
   code,_,body,_=await api('/api/coach/session/add',dict(req,index=0));assert code==400,body
  with patch.object(routes,'ROUTES',base/'routes'),patch.object(mapserver,'capture_program_forecast'):
   route=routes.Route([(34,-118,100),(34.01,-118,110)],'Test route');route.save()
   code,_,body,_=await api('/api/coach/route/plan',{'date':'2026-10-06','route_id':route.id,'minutes':45});assert code==200,body
   assert coach.load(base/'coach.json')['plans']['2026-10-06']['sessions'][0]['route_id']==route.id
   code,_,body,_=await api('/api/coach/route/plan',{'date':'2026-10-07','route_id':'../coach','minutes':45});assert code==400,body
  root=base/'app';root.mkdir();shared=base/'bikebridge-maps'/'web'/'maplibre';shared.mkdir(parents=True)
  with patch.dict('os.environ',{},clear=True):
   assert map_paths.locate(root)==shared.parent.parent
   (root/'maps').mkdir();assert map_paths.locate(root)==root/'maps'
  with patch.dict('os.environ',{'S_BIKE_MAPS':str(base/'override')}):assert map_paths.locate(root)==(base/'override').resolve()
 print('PASS running stages, pace, steps, honest unknown impact, canonical save/edit, hold gate, completed protection, route scheduling and map path precedence')
asyncio.run(main())
