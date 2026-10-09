"""Single-workout edits must not alter completed neighbors or append a duplicate."""
import asyncio, copy, json, pathlib, sys, tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import coach,mapserver,swim_workouts,run_workouts,workouts
async def main():
 with tempfile.TemporaryDirectory() as temp:
  base=pathlib.Path(temp);(base/'rides').mkdir();(base/'activities').mkdir()
  date=coach.today();bridge=SimpleNamespace(csv_path=base/'rides/test.csv',profile={'ftp':180},workouts=[],reload_workouts=lambda:None)
  async def api(path,req):
   code,_,body,_=await mapserver.coach_api(bridge,b'POST',path,path,json.dumps(req).encode());return code,json.loads(body)
  actual={date:[{'sport':'swim','minutes':20,'activity_id':'completed-watch','workout_link':{'mode':'scheduled','session_index':0}}]}
  finished={'sport':'swim','name':'Completed swim','minutes':20,'steps':['200 FS'],'recorded_activity_id':'completed-watch','explanation':{'purpose':'Keep this exact record'},'custom_metadata':{'preserved':True}}
  payloads=[
   ('swim',{'swim_recipe':{'fields':{'main':'200 FS'},'unit':'yd'},'minutes':20}),
   ('ride',{'ride_blocks':[{'type':'steady','minutes':20,'watts':100}],'minutes':20}),
   ('run',{'run_recipe':run_workouts.parse({'main':'10 minutes jog'}),'minutes':10}),
   ('gym',{'lifts':[{'name':'Russian twist','sets':2,'reps':10,'weight':20,'unit':'lb'}],'typed_workout':{'main':'Russian twist 2 x 10 @ 20 lb','repeats':1},'draft':True,'minutes':20}),
   ('walk',{'steps':['20 minutes walking'],'typed_workout':{'main':'20 minutes walking'},'minutes':20}),
   ('other',{'steps':['20 minutes movement'],'typed_workout':{'main':'20 minutes movement'},'minutes':20}),
  ]
  with patch.object(mapserver,'capture_program_forecast'),patch.object(mapserver,'done_by_day',return_value=actual),patch('training_block.running_gate',return_value={'status':'open_for_review'}),patch.object(workouts,'FOLDER',base/'workouts'):
   for sport,extra in payloads:
    d=coach.load(base/'coach.json');d['plans']={date:{'sessions':[copy.deepcopy(finished),{'sport':sport,'name':'Unfinished','minutes':20,'steps':[]}]}};coach.save(d)
    req={'date':date,'index':1,'sport':sport,'name':'Edited',**extra}
    path='/api/coach/lifting/plan' if sport=='gym' else '/api/coach/session/add'
    code,result=await api(path,req);assert code==200,(sport,result)
    saved=coach.load(base/'coach.json')['plans'][date]['sessions'];assert len(saved)==2 and saved[1]['name']=='Edited',saved
    assert saved[0]==finished,(sport,saved[0])
    before=(base/'coach.json').read_bytes()
    code,result=await api('/api/coach/session/add',{'date':date,'index':0,'sport':'swim','name':'Overwrite','minutes':20,'swim_recipe':{'fields':{'main':'100 FS'},'unit':'yd'}})
    assert code==400 and 'completed' in result['error'],result
    assert (base/'coach.json').read_bytes()==before
    for invalid in [True,-1,2]:
     code,result=await api(path,{**req,'index':invalid});assert code==400,(sport,invalid,result)
     assert (base/'coach.json').read_bytes()==before
   # A route outline edit retains the route and power settings without creating an ERG workout.
   original={'sport':'ride','name':'Route ride','minutes':20,'route_id':'test-route','workout':'saved-ride','cadence':[70,90],'bike_plan':{'power_steps':[{'minutes':20,'watts':100}],'basis':'Saved route power'}}
   d=coach.load(base/'coach.json');d['plans']={date:{'sessions':[copy.deepcopy(finished),original]}};coach.save(d)
   with patch('routes.load',return_value=SimpleNamespace(id='test-route')):
    code,result=await api('/api/coach/session/add',{'date':date,'index':1,'sport':'ride','name':'Route ride edited','minutes':20,'steps':['Main work: Ride the saved route comfortably'],'typed_workout':{'main':'Ride the saved route comfortably'}})
   assert code==200,result
   saved=coach.load(base/'coach.json')['plans'][date]['sessions']
   assert saved[0]==finished and len(saved)==2
   for key in ('route_id','workout','cadence','bike_plan'):assert saved[1][key]==original[key],(key,saved[1])
   # Inferred completion also protects its exact session.
   d=coach.load(base/'coach.json');d['plans']={date:{'sessions':[{'sport':'swim','name':'Matched swim','minutes':20}]}};coach.save(d)
   with patch.object(mapserver,'done_by_day',return_value={date:[{'sport':'swim','minutes':20,'activity_id':'inferred'}]}):
    code,result=await api('/api/coach/session/add',{'date':date,'index':0,'sport':'swim','name':'Overwrite','minutes':20,'swim_recipe':{'fields':{'main':'100 FS'},'unit':'yd'}})
    assert code==400 and 'completed' in result['error'],result
 print('PASS unfinished edits across six sports, no duplicates, completed neighbor metadata/links retained, inferred completion and invalid indices protected')
asyncio.run(main())
