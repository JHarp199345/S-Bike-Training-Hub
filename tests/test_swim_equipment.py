"""Equipment affects separate dose pathways without counting propulsion as arm force."""
import copy, pathlib, sys, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import loads, swimload, bodymap
p={'weight_kg':80,'hr_rest':60,'hr_max':180,'ftp':180,'swim_css':120}
a={'sport':'swim','minutes':10,'distance_m':600,'records':[{'t':i,'hr':130,'w':None,'rpm':None} for i in range(600)],
   'pool_length_m':25,'swim_lengths':[{'length_type':1,'total_strokes':10,'avg_speed':1,'total_timer_time':25,'swim_stroke':0} for _ in range(20)]}
f=copy.deepcopy(a);f.update(fins=True,snorkel=True,swim_rpe=5)
base=loads.score(a,p,1);equipped=loads.score(f,p,1)
assert base['engine_from']=='swim pace vs CSS'
assert equipped['engine_from']=='heart rate · fins (pace excluded)'
faster=copy.deepcopy(f);faster['distance_m']*=2
assert loads.score(faster,p,1)['engine']==equipped['engine'], 'assisted speed does not inflate cardio'
assert equipped['impact']==0 and equipped['muscle']>base['muscle']
assert abs(swimload.kick_dose(f)['active_minutes']-20*25/60)<.01
assert swimload.dose(faster)['units']==swimload.dose(f)['units']
for x in faster['swim_lengths']:x['avg_speed']*=2
assert swimload.dose(faster)['units']==swimload.dose(f)['units'], 'assisted speed does not inflate shoulder exposure'
partial=copy.deepcopy(f);partial['fins_fraction']=.5
assert min(swimload.dose(a)['units'],swimload.dose(f)['units'])<=swimload.dose(partial)['units']<=max(swimload.dose(a)['units'],swimload.dose(f)['units'])
assert min(base['muscle'],equipped['muscle'])<=loads.score(partial,p,1)['muscle']<=max(base['muscle'],equipped['muscle'])
drill=copy.deepcopy(f)
for x in drill['swim_lengths']:x['total_strokes']=0
assert swimload.kick_dose(drill)['points']==swimload.kick_dose(f)['points'], 'kick drills must not disappear with zero arm strokes'
missing=copy.deepcopy(f);missing['records']=[]
assert 'effort proxy' in loads.score(missing,p,1)['engine_from']
snorkel=copy.deepcopy(a);snorkel['snorkel']=True
assert loads.score(snorkel,p,1)['engine']==base['engine']
assert swimload.dose(snorkel)['units']==swimload.dose(a)['units']
map_=bodymap.build(10,.5,.2,swim_leg_ratio=.3)
assert 'swim_kick' in map_['regions']['calves']['contributions']
assert 'swim' not in map_['regions']['calves']['contributions']
assert 'swim_kick' not in map_['regions']['shoulders']['contributions']
with tempfile.TemporaryDirectory() as temp:
 old=loads.gather
 try:
  loads.gather=lambda *args:[{'id':'swim','sport':'swim'}]
  (pathlib.Path(temp)/'activities').mkdir()
  meta=loads.set_swim_activity(temp,'swim',fins=True,snorkel=True,fins_fraction=1,kick_rpe=5)
  assert meta['fins'] and meta['fins_fraction']==1
  for bad in (float('nan'),-1,2):
   try:loads.set_swim_activity(temp,'swim',fins_fraction=bad)
   except ValueError:pass
   else:raise AssertionError('invalid fraction accepted')
 finally:loads.gather=old
print('ALL PASS: equipment separation, partial sessions, active kick drills, missing HR, and metadata validation')
