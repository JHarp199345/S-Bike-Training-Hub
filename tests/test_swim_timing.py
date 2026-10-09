"""Targets, coarse watch blocks, optional recall and unbiased comparisons."""
import copy,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import swim_workouts as sw,swim_timing as st
TEXT='''300 Butterfly Drill 10 to 15 minutes
100 FS Drill 2 minutes
400 FS 6 to 8 minutes
100 FS Drill 2 minutes
400 FS 6 to 8 minutes
100 FS Drill 2 minutes
400 FS 6 to 8 minutes
200 Back Stroke 5 minutes'''
p=sw.parse({'main':TEXT},pool_length=25)
assert p['valid'] and p['total_distance']==2000 and (p['completion_goal_minutes'],p['completion_expected_minutes'])==(39,50),p
assert len(st.blocks(p))==7 and len(st.blocks(p)[0]['sets'])==2
assert sw.validate_recipe({'fields':{'main':TEXT},'unit':'yd'})['sets'][0]['expected_seconds']==900
for bad in ['400 FS 8 to 6 minutes','400 FS 0 to 8 minutes']:
 assert not sw.parse({'main':bad})['valid'],bad
assert sw.parse({'main':'4 x 50 FS rest 20 seconds'})['sets'][0]['goal_seconds'] is None
assert sw.parse({'main':'4 x 50 FS @ 1:00'})['sets'][0]['goal_seconds'] is None
assert sw.parse({'main':'4 x 50 FS 4 to 5 minutes'})['completion_goal_minutes']==4 # whole line, not each rep
laps=[{'total_distance':yd*.9144,'total_timer_time':seconds,'swim_stroke':stroke} for yd,seconds,stroke in [(400,960,4),(400,420,0),(100,130,4),(400,390,0),(100,120,4),(400,500,0),(200,300,1)]]
a={'id':'test','start':1791536400,'sport':'swim','distance_m':1828.8,'pool_length_m':22.86,'laps':laps,'minutes':47}
x=st.compare(p,a);assert not x['issues'] and len(x['rows'])==7,x
assert x['rows'][0]['goal_seconds']==720 and x['rows'][0]['expected_seconds']==1020 and x['rows'][0]['actual_seconds']==960 and x['rows'][0]['combined']
assert x['rows'][0]['signature'] is None
assert [x['rows'][i]['grade']['status'] for i in [0,3,5]]==['As or better than expected','As or better than expected','Slower than expected']
assert x['actual_seconds']==2820 and x['grade']['seconds_vs_expected']==180
# No drill separator is required for ordinary set boundaries.
q=sw.parse({'main':'400 FS 6 to 8 minutes\n400 FS 6 to 8 minutes'},pool_length=25)
b={**a,'distance_m':731.52,'laps':[],'swim_lengths':[{'length_type':1,'swim_stroke':0,'total_timer_time':25} for _ in range(32)]}
y=st.compare(q,b);assert len(y['rows'])==2 and all(r['actual_seconds']==400 for r in y['rows']),y
# If a watch lap spans two regular sets, keep it combined.
b={**b,'swim_lengths':[],'laps':[{'total_distance':731.52,'total_timer_time':800,'swim_stroke':0}]}
y=st.compare(q,b);assert len(y['rows'])==1 and y['rows'][0]['combined'] and y['rows'][0]['actual_seconds']==800
# Never split unidentified times or shift repeated sets after missing distance.
assert all(r['actual_seconds'] is None for r in st.compare(p,{**a,'distance_m':1500})['rows'])
assert st.compare(p,{**a,'laps':[]})['grade'] is None
bad=copy.deepcopy(a);bad['laps'][1]['swim_stroke']=1
assert st.compare(p,bad)['rows'][1]['needs_review'] and st.compare(p,bad)['grade'] is None
before=st.compare(p,a);d={};st.capture(d,a['id'],p,'2026-10-09',0);changed=copy.deepcopy(p);changed['sets'][0]['goal_seconds']=1
st.capture(d,a['id'],changed,'2026-10-09',0);assert d['swim_timing_baselines']['test']['recipe']==p
saved=st.save_splits(d,a,p,[{'set_index':0,'seconds':800},{'set_index':1,'seconds':130}])
assert saved[0]['actual_seconds']==800 and saved[0]['grade']['seconds_to_goal']==200
assert st.compare(p,a)==before and st.reported_splits(d,a,p)[2]['actual_seconds'] is None
prior=copy.deepcopy(d)
for invalid in [[{'set_index':2,'seconds':100}],[{'set_index':0,'seconds':float('nan')}],[{'set_index':0,'seconds':0}],[{'set_index':True,'seconds':100}]]:
 try:st.save_splits(d,a,p,invalid)
 except ValueError:pass
 else:raise AssertionError(invalid)
 assert d==prior
untimed=sw.parse({'main':'400 FS'},pool_length=25)
for n,t in enumerate([420,450,480]):
 st.remember(d,{**a,'id':f'past{n}','start':a['start']-86400*(n+1),'distance_m':365.76,'laps':[{'total_distance':365.76,'total_timer_time':t,'swim_stroke':0}]},untimed)
 if n<2:assert not st.suggestions(untimed,d)
suggestion=st.suggestions(untimed,d)[0];assert suggestion['performances']==3 and suggestion['recent_best_seconds']==420 and suggestion['expected_seconds']==450
assert not st.suggestions(sw.parse({'main':'400 Butterfly'},pool_length=25),d)
assert not st.suggestions(sw.parse({'main':'400 FS'},pool_length=50),d)
print('PASS swim goal/expected ranges, unbiased alignment, combined drills, missing data, immutable baseline, optional athlete splits and history drafts')
