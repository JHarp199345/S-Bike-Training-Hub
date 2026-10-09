"""Watch association is explicit, sport-neutral, persistent and lossless for source files."""
import copy, datetime as dt, json, pathlib, sys, tempfile
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools/demo'))
import recording_links as R, loads, coach, activity_reports, watch_files, progression, fitwrite
base=pathlib.Path(tempfile.mkdtemp());(base/'rides').mkdir();(base/'activities').mkdir()
t=dt.datetime(2026,10,8,9).timestamp();date='2026-10-08'
def activity(ident,sport='bike',source='watch',offset=0):
 return {'id':ident,'source':source,'sport':sport,'start':t+offset,'minutes':10,'distance_m':2000,'records':[{'t':t+offset+i,'hr':145 if source=='watch' else None,'w':180 if source=='bridge' else 20,'rpm':80 if source=='bridge' else 60} for i in range(600)],'session':{'total_calories':300} if source=='watch' else {}}
w=activity('watch');bike=activity('bike',source='bridge');raw=[w,bike]
def planned(sport='ride'):return {'plans':{date:{'sessions':[{'sport':sport,'name':'Scheduled','minutes':40,'target':100}]}},'training_feedback':{},'events':[]}
with patch.object(loads,'gather',return_value=raw):
 d=planned();before=copy.deepcopy(d)
 preview=R.select(base,d,dict(activity_id='watch',mode='scheduled',session_index=0,target_activity_id='bike'))
 assert d==before and preview['canonical_activity_id']=='bike' and preview['measurements']['avg_power']==180 and preview['measurements']['avg_heart_rate']==145
 R.select(base,d,dict(activity_id='watch',mode='scheduled',session_index=0,target_activity_id='bike',save=True))
 assert d['plans'][date]['sessions'][0]['recorded_activity_id']=='bike' and d['plans'][date]['sessions'][0]['target']==100
 merged=R.apply(raw,d['recording_links']);assert len(merged)==1 and merged[0]['id']=='bike'
 assert all(r['w']==180 and r['rpm']==80 and r['hr']==145 for r in merged[0]['records'])
 assert raw==[w,bike] # immutable
 done=[{'activity_id':'bike','sport':'bike','minutes':10,'workout_link':d['recording_links']['watch']}]
 assert coach.attach_completions(d,date,copy.deepcopy(d['plans'][date]['sessions']),done)[0]['completion']['activity_id']=='bike'
 R.select(base,d,dict(activity_id='watch',mode='scheduled',session_index=0,target_activity_id='bike',save=True));assert len(R.apply(raw,d['recording_links']))==1
 R.select(base,d,dict(activity_id='watch',mode='new',save=True));assert 'recorded_activity_id' not in d['plans'][date]['sessions'][0] and len(R.apply(raw,d['recording_links']))==2
 for req in [dict(mode='activity',target_activity_id='watch'),dict(mode='activity',target_activity_id='missing'),dict(mode='new',save=1),dict(mode='new',offset_seconds=True),dict(mode='new',target_activity_id='bike'),dict(mode='scheduled',session_index=True),dict(mode='activity',target_activity_id='bike',offset_seconds=700)]:
  snapshot=copy.deepcopy(d)
  try:R.select(base,d,{'activity_id':'watch','save':True,**req});raise AssertionError(req)
  except ValueError:pass
  assert d==snapshot
 for sport in ['swim','run','gym','walk','other']:
  a=activity(sport,sport);d=planned(sport)
  with patch.object(loads,'gather',return_value=[a]):
   assert len(R.choices(base,d,sport)['scheduled'])==1
   R.select(base,d,dict(activity_id=sport,mode='new',save=True))
   done=[{'sport':sport,'minutes':10,'activity_id':sport,'workout_link':d['recording_links'][sport]}]
   assert not coach.attach_completions(d,date,copy.deepcopy(d['plans'][date]['sessions']),done)[0].get('completion')
   report=progression.report(d,date,0,dict(activity_id=sport,effort='as_intended',rpe=6),{date:done},date)
   assert report['activity_id']==sport and report['rpe']==6 and report['session_index'] is None
   R.select(base,d,dict(activity_id=sport,mode='scheduled',session_index=0,save=True))
   assert coach.attach_completions(d,date,copy.deepcopy(d['plans'][date]['sessions']),done)[0]['completion']['activity_id']==sport
# Clock offset is explicit, and missing HR samples aren't invented.
gap=copy.deepcopy(w);gap['records']=[r for r in gap['records'] if not t+100<=r['t']<=t+200]
for r in gap['records']:r['t']+=30
m=R.merge(bike,gap,-30);assert m['recording_alignment']['matched_hr_samples']<600
assert all(r['hr'] is None for r in m['records'][103:198]);assert m['session']['avg_power']==180
# Actual import stores validated bytes once; collisions never overwrite files.
fitwrite.run(base/'first.fit',t,600,140,2000);payload=(base/'first.fit').read_bytes()
r=watch_files.store(base,'same.fit',payload);assert r['imported']==['same.fit']
assert watch_files.store(base,'renamed.fit',payload)['already']==['same.fit']
fitwrite.run(base/'second.fit',t+3600,600,150,2200);other=(base/'second.fit').read_bytes()
r=watch_files.store(base,'same.fit',other);assert r['imported'][0]!='same.fit' and (base/'activities/same.fit').read_bytes()==payload
# Real source readers, canonical report alias and persistent gathering.
writer=fitwrite.Writer()
for i in range(600):writer.add('record',timestamp=t+i,heart_rate=145,power=20,cadence=60)
writer.add('session',start_time=t,timestamp=t+600,sport=2,total_timer_time=600,total_distance=0)
(base/'activities/cycle.fit').write_bytes(writer.bytes())
(base/'rides/ride_bike.csv').write_text('time,power_w,cadence_rpm\n'+''.join(f'{dt.datetime.fromtimestamp(t+i).isoformat()},180,80\n' for i in range(600)))
d=planned();R.select(base,d,dict(activity_id='cycle',mode='scheduled',session_index=0,target_activity_id='ride_bike',save=True));(base/'coach.json').write_text(json.dumps(d))
canonical=loads.gather(base/'activities',base/'rides');assert len([a for a in canonical if a['id'] in ('ride_bike','cycle')])==1
report=activity_reports.build(activity_reports.read_activity(base,'cycle'),d=d)
assert report['activity_id']=='ride_bike' and report['bike']['avg_power_w']==180 and report['avg_hr']==145
assert (base/'activities/cycle.fit').read_bytes()==writer.bytes()
print('PASS explicit all-sport choices, preview/save, canonical count, preserved targets/sources, repeat association, offsets/gaps, invalid requests, reports and collision-safe imports')
# Saved effort and lifting details follow the canonical session, with an audit copy.
with patch.object(loads,'gather',return_value=raw):
 d=planned();d['activity_workouts']={'watch':{'text':'Saved workout notes'}}
 d['training_feedback']={'activity:watch':{'activity_id':'watch','date':date,'session_index':None,'rpe':7}}
 d['lifting']={'logs':[{'source_activity_id':'watch','lifts':[]}]}
 request=dict(activity_id='watch',mode='scheduled',target_activity_id='bike',session_index=0,save=True)
 R.select(base,d,request)
 assert list(d['training_feedback'])==[date+':0'] and d['training_feedback'][date+':0']['rpe']==7
 assert d['activity_workouts']['bike']['text']=='Saved workout notes' and d['lifting']['logs'][0]['source_activity_id']=='bike'
 assert d['recording_link_report_history'][0]['report']['activity_id']=='watch'
 R.select(base,d,request) # repeat doesn't duplicate annotations or reports
 assert len(d['training_feedback'])==1
 R.select(base,d,dict(activity_id='watch',mode='new',save=True))
 assert list(d['training_feedback'])==['activity:watch'] and d['lifting']['logs'][0]['source_activity_id']=='watch'
print('PASS existing notes, lifting source identity and one session report survive association changes with an audit copy')
d={'plans':{},'lifting':{'logs':[{'date':date,'session':'First lift','minutes':10,'source_activity_id':'gym-canonical'}]}}
sessions=[{'sport':'gym','name':'First lift','minutes':10,'recorded_activity_id':'gym-canonical'},{'sport':'gym','name':'Second lift','minutes':10}]
marked=coach.attach_completions(d,date,sessions,[{'sport':'gym','minutes':10,'activity_id':'gym-canonical'}])
assert marked[0]['completion']['activity_id']=='gym-canonical' and not marked[1].get('completion')
print('PASS an explicitly linked lifting log cannot complete a second scheduled workout')

assert not list((base/'activities').glob('validate-*'))
try:watch_files.store(base,'bad.tcx',b'<TrainingCenterDatabase/>')
except ValueError:pass
else:raise AssertionError('Empty watch file must be rejected')
assert not list((base/'activities').glob('validate-*'))
print('PASS temporary watch validation files are closed before reading and cleaned on success/failure')
