"""Workout volume targets, zero-load briefs, favorites and response attribution."""
import sys,pathlib,copy,tempfile,json,asyncio
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import workout_library as lib,coach,mapserver,workouts
LIFT=[{'name':'Bench press','sets':3,'reps':10,'weight':100,'unit':'lb','section':'main','tempo':'3-0-3'}, {'name':'Row','sets':2,'reps':10,'weight':50,'unit':'lb','per_side':True,'section':'main'}, {'name':'Stretch','sets':1,'seconds':20,'section':'cooldown'}]
goals={'weight_moved':5000,'unit':'lb'}
p=lib.compare('gym',goals,{'lifts':LIFT});assert p['checks'][0]['calculated']==5000 and not p['requires_review'],p
assert p['totals']['active_seconds']==360 # 180 sec bench +160 sec unilateral rows +20 sec stretch
assert lib.compare('gym',dict(goals,weight_moved=6000),{'lifts':LIFT})['requires_review']
p=lib.compare('ride',{'power_low':140,'power_high':160,'minutes':20,'energy_kcal':300,'distance_km':10},{'minutes':20,'ride_blocks':[{'type':'steady','watts':100,'minutes':5,'section':'warmup'},{'type':'steady','watts':150,'minutes':10,'section':'main'},{'type':'steady','watts':80,'minutes':5,'section':'cooldown'}]})
assert p['checks'][-1]['calculated']==150 and p['checks'][-1]['matches']
assert p['totals']['external_work_kj']==144 and p['requires_review']
assert any(x['metric']=='energy_kcal' and x['calculated'] is None for x in p['checks'])
for sport,g in [('gym',{'weight_moved':float('nan')}),('ride',{'power_low':100}),('swim',{'distance':True}),('gym',{'weight_moved':100,'unit':'yd'}),('gym',{})]:
 try:lib.clean_goals(sport,g)
 except ValueError:pass
 else:raise AssertionError(g)
async def main():
 with tempfile.TemporaryDirectory() as tmp:
  base=pathlib.Path(tmp);(base/'rides').mkdir();(base/'workouts').mkdir();d=coach.load(base/'coach.json');coach.save(d)
  before=copy.deepcopy(d['plans']);brief=lib.save_goal(d,{'date':'2026-10-06','sport':'gym','name':'Volume brief','goals':goals})
  assert d['plans']==before and not d.get('training_feedback')
  req={'sport':'gym','draft':True,'name':'Strength draft','minutes':None,'lifts':LIFT,'typed_workout':{'main':'Bench press 3 x 10 @ 100 lb; row 2 x 10 per side @ 50 lb','repeats':1},'favorite':True,'workout_goals':goals}
  item=lib.save_template(d,req);assert item['favorite'] and item['uses']==[] and d['plans']==before
  assert lib.save_template(d,req)['id']==item['id'] and len(d['workout_library'])==1
  coach.save(d)
  bridge=SimpleNamespace(csv_path=str(base/'rides'/'scratch.csv'),profile={'ftp':180},workouts=[])
  async def api(path,data=None):return await mapserver.coach_api(bridge,b'POST' if data is not None else b'GET',path,path,json.dumps(data).encode() if data is not None else b'')
  with patch.object(mapserver,'capture_program_forecast'),patch.object(mapserver,'done_by_day',return_value={}):
   code,_,body,_=await api('/api/coach/workout-library');assert code==200 and len([w for w in json.loads(body)['workouts'] if w['origin']!='starter'])==1,body
   code,_,body,_=await api('/api/coach/workout-library/favorite',{'id':item['id'],'favorite':False});assert code==200
   assert coach.load(base/'coach.json')['plans']==before
   code,_,body,_=await api('/api/coach/workout-goals');assert json.loads(body)['goals'][0]['status']=='needs_workout'
   bad=dict(req,date='2026-10-06',goal_request_id=brief['id'],workout_goals=dict(goals,weight_moved=6000))
   disk=(base/'coach.json').read_bytes();code,_,body,_=await api('/api/coach/session/add',bad);assert code==400,body;assert (base/'coach.json').read_bytes()==disk
   code,_,body,_=await api('/api/coach/session/add',dict(req,date='2026-10-06',goal_request_id=brief['id']));assert code==200,body
   after=coach.load(base/'coach.json');session=after['plans']['2026-10-06']['sessions'][0]
   assert session['library_id'] and session['minutes']>0 and session['goal_comparison']['checks'][0]['matches']
   assert after['workout_goal_requests'][brief['id']]['status']=='workout_created'
   assert len([i for i in after['workout_library'].values() if i['origin']!='starter'])==1,'one athlete workout expected'
   # Reports attach to one dated use; reusing or hearting never creates a second activity.
   after['training_feedback']={'2026-10-06:0':{'effort':'as_intended','session_name':'Strength draft'}}
   after['capacity_followups']={'2026-10-06:0':{'recovery':'good','reported_on':'2026-10-08'}}
   result=lib.listing(after)[0];assert result['response_count']==1 and result['responses'][0]['delayed_capacity_followup']['recovery']=='good'
   # Index replacement cannot silently borrow the previous workout's biology.
   after['plans']['2026-10-06']['sessions'][0].pop('library_id');assert not lib.responses(after,result)
  # Imported workouts of every supported sport can be kept without a new
  # scheduled session, duplicate activity, copied watch metrics, or invented stages.
  import swim_workouts
  swim_fields={'warmup':'200 free','main':'300 breast drill; 100 fly drill; 400 free','cooldown':''}
  recipe=swim_workouts.parse(swim_fields,1,'yd')
  assert recipe['valid'],recipe
  live={'id':'synthetic-swim','date':'2026-10-08','sport':'swim','minutes':30,'km':.9144,'avg_hr':123,'calories_kcal':382}
  fresh=coach.load(base/'coach.json')
  fresh.setdefault('activity_workouts',{})[live['id']]={'fields':swim_fields,'recipe':recipe,'text':'original swim notes'}
  coach.save(fresh)
  plans=copy.deepcopy(fresh['plans']);source=copy.deepcopy(live)
  with patch.object(mapserver,'load_state',return_value={'activities':[live]}):
   disk=(base/'coach.json').read_bytes()
   code,_,body,_=await api('/api/coach/workout-library/completed',{'activity_id':live['id']})
   assert code==200,body
   assert (base/'coach.json').read_bytes()==disk,'Preview must not write'
   code,_,body,_=await api('/api/coach/workout-library/completed',{'activity_id':live['id'],'save':True})
   assert code==200,body
   item=json.loads(body)['workout'];uid=item['id']
   assert item['favorite'] and item['session']['sport']=='swim'
   assert item['session']['swim_recipe']['total_distance_m']==recipe['total_distance_m']
   assert item['session']['typed_workout']['warmup']=='200 free'
   assert 'avg_hr' not in item['session'] and 'calories_kcal' not in item['session']
   code,_,body,_=await api('/api/coach/workout-library/completed',{'activity_id':live['id'],'save':True})
   assert code==200 and json.loads(body)['workout']['id']==uid,body
  fresh=coach.load(base/'coach.json')
  assert fresh['plans']==plans and live==source
  assert fresh['activity_workouts'][live['id']]['text']=='original swim notes'
  assert len(fresh['workout_library'][uid]['completed_uses'])==1
  completion={'activity_id':live['id'],'minutes':30,'avg_hr':123}
  assert lib.responses(fresh,fresh['workout_library'][uid],{'2026-10-08':[completion]})[0]['completion']==completion
  for sport in ('bike','ride','run','other'):
   activity={**live,'id':'synthetic-'+sport,'sport':sport}
   before=copy.deepcopy(fresh['plans'])
   saved=lib.save_completed(fresh,activity,{'save':True})
   assert saved['favorite'] and saved['session']['sport']==('ride' if sport=='bike' else sport)
   assert saved['session']['steps']==['Recorded 30 min · 0.9144 km']
   assert 'bike_plan' not in saved['session'],'No invented power targets'
   assert fresh['plans']==before
 print('PASS total moved weight, units, honest power/energy checks, zero-load briefs, library-only save, deduplication, calendar resolution and response attribution')
if __name__=='__main__':asyncio.run(main())
