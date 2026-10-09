"""Parsed power timeline -> saved prescription -> actual ride engine, in scratch storage."""
import sys,pathlib,json,tempfile,asyncio,copy
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import workouts,coach,ride_workouts,mapserver,rider
from erg import Erg
blocks=[{'type':'steady','minutes':5,'watts':100,'watts_low':90,'watts_high':110,'label':'Warm-up','section':'warmup'}]
for i in range(3):
 blocks.append({'type':'steady','minutes':9,'watts':150,'watts_low':140,'watts_high':160,'label':f'Work {i+1}','section':'main'})
 if i<2:blocks.append({'type':'steady','minutes':3,'watts':100,'watts_low':90,'watts_high':110,'label':f'Recovery {i+1}','section':'main'})
blocks.append({'type':'ramp','minutes':8,'from_watts':160,'to_watts':80,'label':'Cool-down','section':'cooldown'})
req={'sport':'ride','name':'Scratch ride','minutes':46,'ride_blocks':blocks,'typed_workout':{'warmup':'5 minutes at 90-110 W','main':'3 x 9 minutes at 140-160 W with 3 minutes at 90-110 W between','cooldown':'8 minutes ramping from 160 to 80 W','repeats':1}}
async def main():
 with tempfile.TemporaryDirectory() as tmp:
  base=pathlib.Path(tmp);folder=base/'workouts';(base/'rides').mkdir();folder.mkdir()
  d=coach.load(base/'coach.json');coach.set_sessions(d,'2026-10-04',[{'sport':'rest','minutes':0}]);coach.save(d)
  before=copy.deepcopy(d)
  candidate,wid=ride_workouts.add(d,'2026-10-05',req,folder)
  assert d==before and candidate['plans']['2026-10-04']==before['plans']['2026-10-04']
  session=candidate['plans']['2026-10-05']['sessions'][0];assert session['workout']==wid;assert session['bike_plan']['power_steps'][0]['watts_low']==90
  saved=json.loads((folder/(wid+'.json')).read_text());assert saved['adaptive'] is False;assert len(saved['steps'])==38
  assert abs(sum(s['minutes'] for s in saved['steps'])-46)<.01
  assert saved['steps'][6]['watts']==160 and saved['steps'][-1]['watts']==80
  for ftp in [180,250]:assert rider.workout_watts(saved,ftp)['steps']==saved['steps']
  assert rider.workout_watts({'steps':[{'minutes':1,'pct':50,'label':'Easy'}]},180)['steps']==[{'minutes':1,'watts':90,'label':'Easy'}]
  engine=Erg();engine.start_workout(rider.workout_watts(saved,180),1)
  assert not engine.workout['adaptive'];assert engine.workout_status(1)['prescribed_band']==[90,110]
  engine.workout['active']=300;assert engine.workout_status(301)['watts']==150;assert engine.workout_status(301)['prescribed_band']==[140,160]
  assert engine.adaptive_state()['prescribed_bands'][1]==[140,160]
  for bad in [dict(req,minutes=36),dict(req,ride_blocks=[dict(blocks[0],watts_low=120)])]:
   count=len(list(folder.glob('*.json')))
   try:ride_workouts.add(d,'2026-10-05',bad,folder)
   except ValueError:pass
   else:raise AssertionError('Invalid timeline accepted')
   assert len(list(folder.glob('*.json')))==count
  edited,_=ride_workouts.add(candidate,'2026-10-05',dict(req,index=0),folder);assert len(edited['plans']['2026-10-05']['sessions'])==1
  # End-to-end endpoint against scratch state; no bike commands or private athlete writes.
  bridge=SimpleNamespace(csv_path=str(base/'rides'/'example.csv'),profile={'ftp':180},reload_workouts=lambda:None,workouts=[])
  with patch.object(workouts,'FOLDER',folder),patch.object(mapserver,'capture_program_forecast'),patch.object(mapserver,'done_by_day',return_value={}):
   code,_,body,_=await mapserver.coach_api(bridge,b'POST','/api/coach/session/add','/api/coach/session/add',json.dumps(dict(req,date='2026-10-05')).encode());assert code==200,body
   after=coach.load(base/'coach.json');assert after['plans']['2026-10-04']==before['plans']['2026-10-04'];assert after['plans']['2026-10-05']['sessions'][0]['workout']
   # The actual Ride now endpoint must preserve these targets when it clones the editor's parts.
   parts=[dict(b,kind='ramp' if b['type']=='ramp' else 'interval') for b in blocks]
   launched=[]
   def launch(ident):
    launched.append(ident)
    data=json.loads((folder/(ident+'.json')).read_text())
    engine.start_workout(rider.workout_watts(data,250),1)
   bridge.workout_start_id=launch
   code,_,body,_=await mapserver.coach_api(bridge,b'POST','/api/coach/split/save','/api/coach/split/save',json.dumps({'name':'Scratch launch','parts':parts,'adaptive':False,'ride':True}).encode());assert code==200,body
   assert launched and engine.workout_status(1)['watts']==100 and engine.workout_status(1)['prescribed_band']==[90,110]
   assert not engine.workout['adaptive']
   launched_data=json.loads((folder/(launched[0]+'.json')).read_text());assert launched_data['steps']==saved['steps']
   bad_before=(base/'coach.json').read_text()
   code,_,body,_=await mapserver.coach_api(bridge,b'POST','/api/coach/session/add','/api/coach/session/add',json.dumps(dict(req,date='2026-10-05',minutes=36)).encode());assert code==400,body;assert (base/'coach.json').read_text()==bad_before
  with patch.object(workouts,'FOLDER',folder),patch.object(mapserver,'done_by_day',return_value={'2026-10-05':[{'sport':'ride','minutes':46,'activity_id':'completed-test-ride'}]}):
   code,_,body,_=await mapserver.coach_api(bridge,b'POST','/api/coach/session/add','/api/coach/session/add',json.dumps(dict(req,date='2026-10-05',index=0)).encode());assert code==400,body
 print('PASS: saved executable ride, bands, ramps, fixed watts, no auto-adaptation, duration rejection, edit identity and actual-record protection')
if __name__=='__main__':asyncio.run(main())
