"""Completed routine identity, output provenance, editing and API isolation."""
import sys,pathlib,copy,asyncio,tempfile,json
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import coach,lifting,strength_workouts as sw,recorded_strength as rs,workout_library as lib,mapserver,activity_reports,mcp_server

REQ={'name':'Push and hips','fields':{'warmup':'TANK M4 level 1: 3 x 60 seconds','main':'Hip thrust machine: 1 x 12 at 105 lb tempo 3-0-3\nHip thrust machine: 2 x 10 at 195 lb tempo 3-0-3','cooldown':''},'note':'Actual notes', 'exercise_metadata':[
 {'kind':'other','equipment':'Torque TANK M4','style':'build','regions':{'quads':1},'per_set_rpe':[3,3,3],
 'sled':{'model':'TANK M4','front_level':1,'rear_level':1,'distance_per_trip_m':54.864,'distance_m':164.592,'seconds_low':60,'seconds_high':60}},
 {'kind':'machine','equipment':'Hip thrust machine','style':'build','regions':{'glutes':1},'per_set_rpe':[1]},
 {'kind':'machine','equipment':'Hip thrust machine','style':'build','regions':{'glutes':1},'per_set_rpe':[7,7]}]}
ACTIVITY={'id':'synthetic-gym','date':'2026-10-08','sport':'gym','minutes':34.2,'km':0}

def text_parity():
 text='''TANK M4 level 1: 3 x 60 seconds, 60 yd per trip, both magnets level 1, RPE: 3
TANK M4 level 2: 2 x 60 seconds, 60 yd per trip, both magnets level 2, RPE: 7–8
TANK M4 level 3: 1 x 62 seconds, 60 yd per trip, both magnets level 3, RPE: 9
Russian twist: 3 x 12 @ 50 lb, RPE: 5, 5, 6 — 12 total alternating reps, six per side
Hip thrust machine: 1 x 12 @ 105 lb tempo 3-0-3, RPE: 1
Hip thrust machine: 2 x 10 @ 195 lb tempo 3-0-3, RPE: 7'''
 d={'plans':{},'checkins':{},'ratings':{}};before=copy.deepcopy(d)
 result,_=sw.completed(d,{'name':'Actual gym','fields':{'warmup':'','main':text,'cooldown':''}},ACTIVITY)
 p=result['output'];assert d==before and len(p['sets'])==12
 assert p['log']['dose']['external_volume_lb']==6960 and p['log']['dose']['active_seconds']==698
 assert [x['reported_rpe'] for x in p['sets']]==[3,3,3,8,8,9,5,5,6,1,7,7]
 assert [p['sets'][i]['power_w_low'] for i in (0,3,5,6,9,10)]==[82.37,213.30,271.13,27.8,38.92,72.28]
 assert all(x['section']=='main' for x in p['sets']) and p['hr']['points']==[]
 assert result['log']['unscored'],'New movements do not get invented regional classifications'
 assert 'upper endpoint' in p['sets'][3]['effort_note']
 assert '12 total alternating' in p['log']['lifts'][3]['how']
 # Planned guesses remain targets; they are not actuals or load multipliers.
 preview=sw.preview(d,{'text':'Row 3 x 10 @ 50 lb, RPE: 7'})
 assert preview['lifts'][0]['planned_effort']==[7]*3 and 'rpe' not in preview['lifts'][0]
 blank=sw.preview(d,{'text':'Row 3 x 10 @ 50 lb'})
 editable=blank['editable_fields']['main'];assert 'planned effort: ' in editable and 'reported effort: ' in editable
 assert sw.preview(d,{'text':editable})['lifts'][0]['planned_effort']==[None]*3
 unknown,_=sw.completed(d,{'text':'TANK M4 level 2: 2 x 60 seconds, 60 yd per trip, RPE:'},ACTIVITY)
 assert all(x['power_w_low'] is None and x['reported_rpe'] is None for x in unknown['output']['sets'])
 for bad_text in ('Row 3 x 10 @ 50 lb, RPE: 11','Row 3 x 10 @ 50 lb, RPE: 5, 6','TANK M4: 2 x 60 seconds, both magnets level 4'):
  try:sw.completed(d,{'text':bad_text},ACTIVITY)
  except ValueError:pass
  else:raise AssertionError(bad_text)
 structured=copy.deepcopy(REQ);structured['fields']['warmup']+=' , 60 yd per trip, both magnets level 1, RPE: 3'
 both,_=sw.completed(d,structured,ACTIVITY);assert both['output']['sets'][0]['power_w_low']==82.37
 structured['exercise_metadata'][0]['per_set_rpe']=[8]*3
 try:sw.completed(d,structured,ACTIVITY)
 except ValueError as e:assert 'disagree' in str(e)
 else:raise AssertionError('Entry routes silently disagreed')
 headings=sw.preview(d,{'text':'Warm-up: Mobility 1 x 30 seconds\nMain work: Row 3 x 10 @ 50 lb — warm-up weight felt fine\nCool-down: Stretch 1 x 30 seconds'})
 assert headings['valid'] and [x['section'] for x in headings['lifts']]==['warmup','main','cooldown']
 dual=sw.preview(d,{'text':'Row 3 x 10 @ 50 lb, planned effort: 7, reported effort: 6'})
 assert dual['lifts'][0]['planned_effort']==[7]*3 and dual['exercise_metadata'][0]['per_set_rpe']==[6]*3
 install(d,{'name':'Actual gym','fields':{'main':text}})
 edited=install(d,{'text':'third set, push, TANK M4 push. That effort was a nine; TANK M4 level 1 set 3 planned effort 4'})
 assert len(edited['output']['sets'])==12 and edited['output']['sets'][2]['reported_rpe']==9 and edited['output']['sets'][2]['planned_effort']==4
 assert edited['parsed']['changes'] and 'reported effort: 9' in edited['details']['fields']['main']
 moved=install(d,{'text':'first three sets were a warm-up'})
 assert [s['section'] for s in moved['output']['sets']][:4]==['warmup']*3+['main']
 assert moved['details']['fields']['warmup'] and moved['output']['sets'][2]['planned_effort']==4
 assert moved['log']['dose']['external_volume_lb']==6960
 print('PASS manual/MCP text parity: 12 actual sets, 6960 lb, independent output/effort, explicit magnets, optional targets, notes and section headings')

def install(d,req=REQ,activity=ACTIVITY):
 result,state=sw.completed(d,req,activity)
 d['lifting']=state;d.setdefault('activity_workouts',{})[activity['id']]=result['details'];lib.reconcile_completed(d,activity['id'])
 return result

def pure():
 d={'plans':{},'checkins':{},'ratings':{}};original=copy.deepcopy(d)
 preview,_=sw.completed(d,REQ,ACTIVITY);assert d==original
 p=preview['output'];assert len(p['sets'])==6 and p['log']['dose']['external_volume_lb']==5160
 assert 82<p['sets'][0]['power_w_low']<83 and 164<p['sets'][0]['power_w_high']<165
 assert p['sets'][3]['power_w_low']==38.92 and p['sets'][4]['power_w_low']==72.28
 harder=copy.deepcopy(REQ);harder['exercise_metadata'][0]['per_set_rpe']=[9,10,8]
 q,_=sw.completed(d,harder,ACTIVITY)
 assert [(x['power_w_low'],x['power_w_high']) for x in q['output']['sets']]==[(x['power_w_low'],x['power_w_high']) for x in p['sets']]
 install(d);saved=lib.save_completed(d,ACTIVITY,{})
 assert saved['favorite'] is True, 'Keeping a completed routine hearts it immediately'
 assert d['plans']=={} and len(d['lifting']['logs'])==1
 assert lib.save_completed(d,ACTIVITY,{})['id']==saved['id']
 assert len(d['workout_library'][saved['id']]['completed_uses'])==1
 assert 'rpe' not in saved['session'] and 'calories_kcal' not in saved['session']
 assert all('rpe' not in x and 'set_details' not in x for x in saved['session']['lifts'])
 # Fresh immutable source, heavier actuals: same movement family, independent dated history.
 second={**ACTIVITY,'id':'synthetic-gym-2','date':'2026-10-09'}
 change=copy.deepcopy(REQ);change['fields']['main']=change['fields']['main'].replace('195 lb','205 lb')
 install(d,change,second);assert lib.save_completed(d,second,{})['id']==saved['id']
 history=lib.responses(d,d['workout_library'][saved['id']]);assert [h['activity_id'] for h in history]==[second['id'],ACTIVITY['id']]
 assert history[0]['external_volume_lb']==5360 and history[1]['external_volume_lb']==5160
 # Name/dose correction preserves per-set effort, classification, source and original plan.
 edit={'name':'Renamed actual','fields':copy.deepcopy(change['fields']),'note':'Extra athlete note'}
 result=install(d,edit,second)
 assert len(d['lifting']['logs'])==2 and result['log']['session']=='Renamed actual'
 assert [x['reported_rpe'] for x in result['output']['sets']]==[3,3,3,1,7,7]
 assert result['details']['library_id']==saved['id']
 assert result['output']['sets'][0]['power_w_low']==82.37
 # New movement correction detaches from old routine and saves as a new one.
 edit['fields']['main']=edit['fields']['main'].replace('Hip thrust machine','Leg press')
 result=install(d,edit,second)
 assert not result['details'].get('library_id')
 different=lib.save_completed(d,second,{})
 assert different['id']!=saved['id']
 assert len(lib.responses(d,d['workout_library'][saved['id']]))==1
 # Missing/out-of-range/mixed settings never get made-up watts.
 assert rs.sled_power({'model':'TANK M4','front_level':1,'rear_level':2,'distance_per_trip_m':54.864},60).get('power_w_low') is None
 assert rs.sled_power({'model':'TANK M4','front_level':3,'rear_level':3,'distance_per_trip_m':5},60).get('power_w_low') is None
 assert rs.sled_power({},60).get('power_w_low') is None
 hrs=rs.hr_trace([{'t':0,'hr':90},{'t':1,'hr':110},{'t':100,'hr':160}])
 assert hrs['points']==[{'seconds':0,'bpm':100.0},{'seconds':100,'bpm':160.0}]
 # Save a changed weight draft without fake library history at a scratch date.
 draft=copy.deepcopy(saved['session']);draft['lifts'][3]['weight']=999
 item=lib.save_template(d,draft);assert item['id']==saved['id'] and len(item['completed_uses'])==1
 assert item['session']['lifts'][3]['weight']==999
 # Explicit library reuse resolves otherwise ambiguous old same-movement entries.
 duplicate=copy.deepcopy(d['workout_library'][saved['id']]);duplicate['id']='a'*32;duplicate['signature']='old variant';d['workout_library'][duplicate['id']]=duplicate
 draft['library_id']=saved['id'];draft['lifts'][3]['weight']=998
 assert lib.save_template(d,draft)['id']==saved['id']
 assert d['plans']=={}
 print('PASS independent output/RPE, force assumptions, source idempotence, name/dose corrections, family history, changed movements and missing data')

def corrections():
 d={'plans':{},'checkins':{},'ratings':{}};install(d)
 baseline=copy.deepcopy(d)
 def check(text,indices,value=4,field='planned_effort'):
  result,_=sw.completed(d,{'text':text},ACTIVITY)
  rows=result['output']['sets'];assert d==baseline
  actual=[i for i,row in enumerate(rows) if row[field]==value]
  assert actual==indices,(text,actual)
  assert result['details']['edit_history'][-1]['before']!=result['details']['edit_history'][-1]['after']
  if field=='planned_effort':
   assert result['log']['points_total']==baseline['lifting']['logs'][0]['points_total']
   assert result['log']['regions']==baseline['lifting']['logs'][0]['regions']
  return result
 check('M4 tank sets two through three planned effort four',[1,2])
 check('sled pushes sets 1, 3 planned effort 4',[0,2])
 check('last two hip thruster sets planned effort four',[4,5])
 check('all TANK sets planned effort four',[0,1,2])
 check('warm-up second set planned effort four',[1])
 check('third M4 tank set planned effort four',[2])
 # Optional mixed targets survive canonical text regeneration and parsing.
 mixed=check('TANK set two planned effort four',[1])
 candidate=copy.deepcopy(d);candidate['lifting']['logs'][0]=mixed['log'];candidate['activity_workouts'][ACTIVITY['id']]=mixed['details']
 roundtrip,_=sw.completed(candidate,{'fields':mixed['details']['fields']},ACTIVITY)
 assert roundtrip['output']['sets'][0]['planned_effort'] is None
 assert roundtrip['output']['sets'][1]['planned_effort']==4
 assert roundtrip['output']['sets'][2]['planned_effort'] is None
 assert roundtrip['log']['points_total']==mixed['log']['points_total']
 for text in ('banana set 3 effort 9','TANK set 99 effort 4','TANK sets 3 to 2 effort 4',
              'TANK set 3 reported effort 7 reported effort 9','TANK set 3 effort 9.5',
              'TANK and hip thrust set 3 effort 9','TANK set 3 delete reps effort 9',
              'effort 9','unknown move set 2 effort 4'):
  try:sw.completed(d,{'text':text},ACTIVITY)
  except ValueError:assert d==baseline
  else:raise AssertionError('Ambiguous or unsupported correction accepted: '+text)
 # Explicit conflicting planned targets fail equally through structured MCP input.
 req=copy.deepcopy(REQ);req['fields']['warmup']+=', planned effort: 4'
 req['exercise_metadata'][0]['planned_effort']=[7]*3
 try:sw.completed(d,req,ACTIVITY)
 except ValueError as e:assert 'disagree' in str(e)
 else:raise AssertionError('Conflicting planned targets accepted')
 print('PASS correction aliases, section scope, ranges, written numbers, optional target roundtrip, historical score preservation and ambiguity rejection')

async def api_test():
 with tempfile.TemporaryDirectory() as tmp:
  base=pathlib.Path(tmp);(base/'rides').mkdir();(base/'activities').mkdir()
  d=coach.load(base/'coach.json');install(d);coach.save(d)
  bridge=SimpleNamespace(csv_path=str(base/'rides/demo.csv'),profile={'ftp':180},workouts=[])
  async def api(path,body=None):
   code,_,raw,_=await mapserver.coach_api(bridge,b'POST' if body is not None else b'GET',path,path,json.dumps(body).encode() if body is not None else b'');return code,json.loads(raw)
  with patch.object(mapserver,'load_state',return_value={'activities':[ACTIVITY]}):
   path=base/'coach.json';baseline=path.read_bytes()
   code,preview=await api('/api/coach/workout-library/completed',{'activity_id':ACTIVITY['id']})
   assert code==200 and preview['saved'] is False and path.read_bytes()==baseline
   code,saved=await api('/api/coach/workout-library/completed',{'activity_id':ACTIVITY['id'],'save':True});assert code==200 and saved['saved']
   ident=saved['workout']['id'];code,history=await api('/api/coach/workout-library/'+ident)
   assert code==200 and len(history['workout']['responses'])==1
   code,preview=await api('/api/coach/lifting/recorded',{'activity_id':ACTIVITY['id'],'name':'Corrected name','fields':REQ['fields']})
   assert code==200 and preview['output']['sets'][0]['reported_rpe']==3
   assert coach.load(path)['lifting']['logs'][0]['session']=='Push and hips'
   code,saved=await api('/api/coach/lifting/recorded',{'activity_id':ACTIVITY['id'],'name':'Corrected name','fields':REQ['fields'],'save':True});assert code==200
   d=coach.load(path);assert len(d['lifting']['logs'])==1 and d['plans']=={}
   done=mapserver.done_by_day(base,d)[ACTIVITY['date']]
   assert done[0]['workout_name']=='Corrected name' and done[0]['lifting']['dose']['external_volume_lb']==5160
   raw={'id':ACTIVITY['id'],'sport':'gym','start':1791471600,'minutes':34.2,'session':{'total_timer_time':2052,'total_calories':389},'records':[{'t':1,'hr':125}]}
   report=activity_reports.build(raw,ACTIVITY,d)
   assert report['strength']['library_id']==ident and report['strength']['hr']['points']
   assert report['calories_kcal']==389 and report['duration_seconds']==2052
   old=path.read_bytes();code,err=await api('/api/coach/lifting/recorded',{'activity_id':ACTIVITY['id'],'text':'nonsense','save':True})
   assert code==400 and path.read_bytes()==old
  tools={x[0]:x for x in mcp_server.TOOLS}
  assert 'save_completed_workout_to_library' in tools
 print('PASS completed-library preview/save/readback, edit isolation, calendar labels and canonical activity report')

if __name__=='__main__':text_parity();pure();corrections();asyncio.run(api_test())
