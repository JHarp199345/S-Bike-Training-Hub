"""Composition, volume and HR time stay descriptive with honest source coverage."""
import sys,pathlib,copy
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import swim_analysis as A,swim_workouts as W
from test_swim_timing import TEXT
p=W.parse({'main':TEXT},distance_unit='yd');m=A.recipe_mix(p)
assert {x['stroke']:x['percent'] for x in m['parts']}=={'fly':15,'free':75,'back':10}
assert round(m['total_m'],1)==1828.8
# Count distance, not strokes; drills with zero strokes still have distance.
a={'sport':'swim','start':1000,'minutes':10,'distance_m':100,'pool_length_m':25,'swim_lengths':[{'length_type':1,'swim_stroke':0,'total_strokes':12},{'length_type':1,'swim_stroke':4,'total_strokes':0},{'length_type':0,'swim_stroke':0}], 'session':{'total_timer_time':600,'avg_heart_rate':130},'records':[]}
before=copy.deepcopy(a);watch=A.watch_mix(a)
assert {x['stroke']:x['percent'] for x in watch['parts']}=={'free':25,'drill':25,'unknown':50}
assert a==before
r=A.response(a);assert r['hr_time_bpm_min']==1300 and r['avg_hr']==130 and r['duration_minutes']==10
assert A.response({**a,'minutes':20,'session':{'total_timer_time':1200,'avg_heart_rate':130}})['hr_time_bpm_min']==2600 # volume alone doubles it
# Unclassified watch laps never inherit planned stroke labels.
assert A.watch_mix({'distance_m':400,'laps':[{'total_distance':400}]})['parts'][0]['stroke']=='unknown'
assert A.watch_mix({'distance_m':50,'pool_length_m':25,'swim_lengths':a['swim_lengths']*3})['distance_mismatch']
assert A.response({'minutes':10,'records':[]})['hr_time_bpm_min'] is None
sampled=A.response({'minutes':10,'records':[{'t':1000,'hr':100},{'t':1010,'hr':140},{'t':1300,'hr':200}]})
assert sampled['avg_hr']==120 and sampled['hr_time_bpm_min']==20 and sampled['hr_minutes']==.17
assert sampled['hr_coverage_percent']==1.7 # no extrapolation over missing 290 seconds
assert A.response({'minutes':float('nan'),'session':{}})['duration_minutes']==0
rows=[{'sport':'swim','id':str(i),'date':f'2026-10-{i:02}','start':'06:00','swim_analysis':A.profile(a)} for i in range(1,17)]
h=A.history(rows,{'activity_workouts':{'3':{'recipe':p}}},'14')
assert len(h)==14 and h[-1]['activity_id']=='14' and h[0]['activity_id']=='1' and h[2]['described_mix']
assert A.history(rows,{},'missing')==[]
print('PASS distance stroke proportions, unknown/drill coverage, independent volume/HR, sparse gaps, no future history')
out=A.dashboard(rows,{'phase_profiles':[{'id':'base','label':'Base','start':'2026-10-01','end':'2026-10-12'}]},'2026-10-09')
assert len(out['rows'])==9 and out['history_start']=='2026-10-01' and out['phases'][0]['end']=='2026-10-12'
assert all(r['date']<='2026-10-09' for r in out['rows'])
print('PASS full dashboard history excludes future swims and retains saved phase boundaries')
# Plan intent is supplied only by a captured association; never inferred from watch drill mode.
planned=W.parse({'main':'300 butterfly drill\n2200 FS'},distance_unit='yd')
state={'swim_timing_baselines':{'14':{'recipe':planned}},'activity_workouts':{'14':{'recipe':p}}}
original=copy.deepcopy(state)
row=A.history_rows(rows,state)[13]
assert row['planned_mix']['total_m']==2286
assert {x['stroke']:x['percent'] for x in row['planned_mix']['parts']}=={'fly':12,'free':88}
assert row['planned_mix']['work_parts'][0]=={'stroke':'fly','work':'drill','distance_m':274.32}
assert row['described_mix']['total_m']==1828.8
assert row['watch_mix']==A.profile(a)['watch_mix']
assert A.history_rows(rows,state)[0]['planned_mix'] is None
assert state==original
print('PASS captured plan/work kinds are separate from performed description and original watch classification')

assert row['written_mix']['parts']==row['described_mix']['parts']
assert row['written_mix']['work_parts']==row['described_mix']['work_parts']
assert row['written_basis']=='Recorded workout breakdown'
plan_only=A.history_rows(rows,{'swim_timing_baselines':state['swim_timing_baselines']})[13]
assert plan_only['written_mix']['total_m']==2286
assert plan_only['written_basis']=='Saved planned workout'
assert A.history_rows(rows,{})[0]['written_mix'] is None
print('PASS unified written history uses recorded breakdowns or captured plans without changing source records')
