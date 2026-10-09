"""Parser actuals, set-specific dose, chart bounds and uncertain HR evidence."""
import sys,pathlib,copy,asyncio,json,tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import lifting,strength_workouts as sw,coach,mapserver,mcp_server,swim_workouts

ACTUAL_SWIM='200 fs\n500 fs kick\n200 fs drill (catch x bow and arrow)\n500 fs\n200 bs drill (single arm bs, lead arm at the side)\n500 bs kick\n200 fs'

def main():
 d={'plans':{},'checkins':{},'ratings':{}}
 plan={'name':'Lat pulldowns','kind':'machine','sets':3,'reps':10,'weight':100,'hold':6,'regions':{'lats':70,'biceps':30}}
 lifting.set_session(d,'2026-10-06',[plan]);prescription=copy.deepcopy(d['plans'])
 parsed=sw.preview(d,{'text':'Lat pulldowns 3 x 10 at 100 lb tempo 3-0-3'})
 assert parsed['valid'],parsed
 assert parsed['dose']['external_volume_lb']==3000 and parsed['dose']['active_seconds']==180
 done=sw.actuals(d,{'text':'Lat pulldowns 3 x 10 at 100 lb tempo 3-0-3'},'2026-10-06')
 assert len(done[0]['set_details'])==3
 result=lifting.log(d,'2026-10-06',done,None,None,source_activity_id='watch')
 assert d['plans']==prescription and result['dose']['active_seconds']==180
 assert [s['external_volume'] for s in result['lifts'][0]['dose']['sets']]==[1000]*3
 assert result['source_activity_id']=='watch'
 varied=[{'rpe':6,'set_details':[{'weight':100,'reps':10,'tempo':'3-0-3','hold':0},{'weight':110,'reps':8,'tempo':'3-0-3','hold':0},{'done':False}]}]
 result=lifting.log(d,'2026-10-06',varied,None,None)
 assert result['dose']['external_volume_lb']==1880 and result['dose']['active_seconds']==108,result['dose']
 assert result['lifts'][0]['sets']==2
 assert len(lifting.state(d)['logs'])==1 and lifting.state(d)['library'][lifting.key(plan['name'])]['times_done']==1
 assert d['plans']==prescription
 for bad in ({'set_details':[]},{'tempo':'nonsense'},{'sets':-1},{'weight':float('nan')}):
  try:lifting.log(copy.deepcopy(d),'2026-10-06',[bad],None,None)
  except ValueError:pass
  else:raise AssertionError(bad)
 chart=sw.sled_preview({'distance_per_leg_m':27.432,'seconds_low':60,'seconds_high':90,'front_level':2,'rear_level':2})
 assert chart['equivalent_weight_lb_low'] is None and 86<chart['equivalent_weight_lb_high']<89,chart
 atone=sw.sled_preview({'distance_per_leg_m':.44704*60,'seconds_low':60,'seconds_high':60,'front_level':2,'rear_level':2})
 assert atone['equivalent_weight_lb_low']==86
 synthetic=[{'t':i,'hr':80+(i//2 if i<80 else max(0,80-i//2))} for i in range(180)]
 windows=sw.hr_windows(synthetic);assert windows['windows'] and 'not mechanical work' in windows['method']
 assert not sw.hr_windows([{'t':i,'hr':100} for i in range(120)])['windows']
 recipe=swim_workouts.parse(swim_workouts.split_sections(ACTUAL_SWIM),distance_unit='yd')
 assert recipe['valid'] and recipe['total_distance']==2300 and len(recipe['sets'])==7
 assert {work:sum(x['distance']*x['repetitions'] for x in recipe['sets'] if x['work']==work) for work in ('swim','kick','drill')}=={'swim':900,'kick':1000,'drill':400}
 detected=swim_workouts.recording_draft({'pool_length_m':22.86,'distance_m':100*.9144,'swim_lengths':[{'length_type':1,'swim_stroke':0},{'length_type':1,'swim_stroke':1},{'length_type':1,'swim_stroke':4},{'length_type':0,'swim_stroke':0}]})
 assert detected['text']=='25 free\n25 back\n25 drill (identify the drill or kick)' and len(detected['warnings'])==2
 print('PASS text parsing, actual set details, exact dose, unchanged prescription, idempotent log, chart range, HR uncertainty')

async def api_test():
 with tempfile.TemporaryDirectory() as tmp:
  base=pathlib.Path(tmp);(base/'rides').mkdir();(base/'activities').mkdir()
  d=coach.load(base/'coach.json')
  lifting.set_session(d,'2026-10-06',[{'name':'Lat pulldowns','kind':'machine','sets':3,'reps':10,'weight':100,'hold':6,'regions':{'lats':70,'biceps':30}}])
  lifting.log(d,'2026-10-06',[{'rpe':6}],None,None,source_activity_id='gym');coach.save(d)
  oldplan=copy.deepcopy(d['plans'])
  bridge=SimpleNamespace(csv_path=str(base/'rides/demo.csv'),workouts=[],profile={'ftp':180})
  state={'activities':[{'id':'gym','date':'2026-10-06','sport':'gym','minutes':23,'km':0},{'id':'swim','date':'2026-10-06','sport':'swim','minutes':53,'km':2.10312}]}
  async def api(path,body):
   code,_,raw,_=await mapserver.coach_api(bridge,b'POST',path,path,json.dumps(body).encode());return code,json.loads(raw)
  with patch.object(mapserver,'load_state',return_value=state), patch('activity_reports.read_activity',return_value={'id':'swim','sport':'swim','start':1791280800,'distance_m':2103.12,'minutes':53,'laps':[]}):
   code,r=await api('/api/coach/lifting/log',{'date':'2026-10-06','text':'Lat pulldowns 3 x 10 at 100 lb tempo 3-0-3'})
   assert code==200 and r['log']['source_activity_id']=='gym' and r['log']['dose']['active_seconds']==180,r
   code,p=await api('/api/coach/recorded-swim',{'activity_id':'swim','text':'2300 free easy','unit':'yd'})
   assert code==200 and p['recipe']['valid'] and not p['distance_difference'],p
   before=(base/'coach.json').read_bytes()
   assert 'activity_workouts' not in coach.load(base/'coach.json')
   code,saved=await api('/api/coach/recorded-swim',{'activity_id':'swim','text':ACTUAL_SWIM,'unit':'yd','save':True})
   assert code==200 and saved['saved']
   after=coach.load(base/'coach.json');assert after['plans']==oldplan
   assert after['activity_workouts']['swim']['text']==ACTUAL_SWIM
   done=mapserver.done_by_day(base,after);assert len([a for a in done['2026-10-06'] if a['sport']=='swim'])==1
   assert next(a for a in done['2026-10-06'] if a['sport']=='swim')['workout_details']['recipe']['total_distance']==2300
   for text in ('200 free easy','nonsense'):
    prior=(base/'coach.json').read_bytes()
    code,rejected=await api('/api/coach/recorded-swim',{'activity_id':'swim','text':text,'unit':'yd','save':True})
    assert code==400 and (base/'coach.json').read_bytes()==prior,rejected
 print('PASS normal API text correction preserves watch link, swim annotation previews/readbacks, no duplicate or rewritten plans')

def completed_test():
 d={'plans':{'2026-10-08':{'sessions':[{'sport':'bike','name':'Keep prescribed ride','minutes':40}]}},'checkins':{},'ratings':{}}
 before=copy.deepcopy(d)
 req={'text':'TANK M4 level 1: 3 x 60 seconds\nHip thrust machine: 1 x 12 at 105 lb tempo 3-0-3\nHip thrust machine: 2 x 10 at 195 lb tempo 3-0-3',
      'name':'Actual gym','exercise_metadata':[
       {'kind':'other','style':'build','regions':{'quads':.5,'glutes':.5},'rpe':3},
       {'kind':'machine','style':'build','regions':{'glutes':.8,'hamstrings':.2},'rpe':1},
       {'kind':'machine','style':'build','regions':{'glutes':.8,'hamstrings':.2},'per_set_rpe':[7,7]}]}
 activity={'id':'gym-new','date':'2026-10-08','sport':'gym','minutes':34.2}
 result,state=sw.completed(d,req,activity)
 assert d==before and result['log']['dose']['external_volume_lb']==5160
 assert result['log']['dose']['active_seconds']==372 and not result['log']['unscored']
 assert [r['rpe'] for r in result['log']['lifts']]==[3,1,7]
 d['lifting']=state
 second,state=sw.completed(d,req,activity)
 assert len(state['logs'])==1 and d['plans']==before['plans']
 assert state['library'][lifting.key('TANK M4 level 1')]['times_done']==1
 bad={**req,'exercise_metadata':[{'weight':999}]*3}
 try:sw.completed(d,bad,activity)
 except ValueError:pass
 else:raise AssertionError('Metadata overwrote dose')
 # Unplanned completed activity uses the same server protocol, with preview isolation.
 async def call_api():
  with tempfile.TemporaryDirectory() as tmp:
   base=pathlib.Path(tmp);(base/'rides').mkdir();(base/'activities').mkdir()
   original=coach.load(base/'coach.json');original['plans']=before['plans'];coach.save(original)
   bridge=SimpleNamespace(csv_path=str(base/'rides/demo.csv'),workouts=[],profile={'ftp':180})
   async def call(body):
    code,_,raw,_=await mapserver.coach_api(bridge,b'POST','/api/coach/lifting/recorded','/api/coach/lifting/recorded',json.dumps(body).encode())
    return code,json.loads(raw)
   with patch.object(mapserver,'load_state',return_value={'activities':[activity]}):
    prior=(base/'coach.json').read_bytes()
    code,p=await call({**req,'activity_id':'gym-new'})
    assert code==200 and p['valid'] and (base/'coach.json').read_bytes()==prior,p
    for _ in range(2):
     code,p=await call({**req,'activity_id':'gym-new','save':True})
     assert code==200 and p['saved'],p
    saved=coach.load(base/'coach.json')
    assert saved['plans']==before['plans'] and len(saved['lifting']['logs'])==1
    assert saved['lifting']['logs'][0]['source_activity_id']=='gym-new'
    code,p=await call({**req,'activity_id':'not-imported','save':True})
    assert code==400,p
 asyncio.run(call_api())
 print('PASS completed-only MCP/API preview, exact dose, per-set efforts, linked idempotent save, plan preservation')

if __name__=='__main__':main();asyncio.run(api_test());completed_test()
