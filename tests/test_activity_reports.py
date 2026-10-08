"""Completed observations and imported feedback preserve the existing workout/model."""
import sys, pathlib, copy, math
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import activity_reports as R, progression, coach
length=lambda stroke,n,t,kind=1:dict(swim_stroke=stroke,total_strokes=n,total_timer_time=t,length_type=kind)
a={'id':'swim','sport':'swim','source':'watch','start':1791306000,'minutes':10,'distance_m':100,'pool_length_m':25,'session':{'total_calories':0},'swim_lengths':[length(0,10,20),length(0,20,30),length(1,5,40),length(4,0,60),length(0,0,20),length(0,10,20,0)],'records':[]}
before=copy.deepcopy(a);r=R.build(a,{'engine':20,'impact':0,'muscle':2});assert a==before
s=r['swim'];assert s['swolf_avg']==round(125/3,2) and s['swolf_best']==30
assert s['distance_per_stroke_avg_m']==round(75/35,2) and s['distance_per_stroke_best_m']==5
assert s['by_stroke']['freestyle']['swolf_avg']==40 and s['excluded_lengths']==2
assert r['calories_kcal']==0 and r['avg_hr'] is None and r['load']['impact']==0
assert R.swim_metrics({'swim_lengths':a['swim_lengths']})['swolf_avg'] is None
assert R.number(float('nan')) is None and R.number(True) is None
# Energy rates use the primary estimate and actual timer, not the watch total or rounded minutes.
assert r['energy_rate']['kcal_per_min']==0 and r['energy_rate']['source']=='watch'
energy_activity={**a,'minutes':11,'session':{'total_timer_time':600,'total_calories':300}}
primary=R.build(energy_activity,{'energy_kcal':200,'energy_source':'motion'})
assert primary['energy_rate']=={'kcal_per_min':20,'metabolic_power_w':1394.67,'energy_kcal':200,'source':'motion','duration_basis':'Recorded timer'}
assert primary['calories_kcal']==300 # keep the separate watch observation
assert R.build(energy_activity,{'energy_kcal':None})['energy_rate'] is None # unknown primary stays unknown
assert R.build({**a,'minutes':0,'session':{'total_calories':300}})['energy_rate'] is None
assert R.build({**a,'minutes':float('nan'),'session':{}})['energy_rate'] is None
run={**a,'id':'run','sport':'run','session':{'total_timer_time':600,'avg_cadence':80,'total_cycles':800,'avg_step_length':800},'distance_m':2000}
r=R.build(run,{'steps':1600,'drift_pct':0});assert r['run']['pace_per_km_seconds']==300 and r['run']['cadence_steps_min']==160 and r['run']['step_length_m']==.8
# Unplanned imported feedback uses a stable activity identity, never creates prescriptions.
d={'plans':{},'training_feedback':{},'events':[]};saved=copy.deepcopy(d['plans']);done={'2026-10-06':[{'sport':'run','minutes':10,'activity_id':'run'}]}
e=progression.report(d,'2026-10-06',0,{'activity_id':'run','effort':'as_intended','rpe':6,'symptoms':[{'location':'achilles','side':'left','severity':2}]},done,'2026-10-06')
assert e['session_index'] is None and e['activity_id']=='run' and d['plans']==saved
assert 'activity:run' in d['training_feedback']
e=progression.report(d,'2026-10-06',0,{'activity_id':'run','effort':'as_intended'},done,'2026-10-06');assert e['symptoms'][0]['severity']==2 # not silently resolved
assert len(d['training_feedback'])==1 and len(d['feedback_edits'])==1
# A matched imported report uses existing scheduled report key instead of duplication.
d={'plans':{'2026-10-06':{'sessions':[{'sport':'run','name':'Easy run','minutes':10}]}},'events':[]};saved=copy.deepcopy(d['plans'])
e=progression.report(d,'2026-10-06',0,{'activity_id':'run','effort':'as_intended'},done,'2026-10-06');assert e['session_index']==0 and list(d['training_feedback'])==['2026-10-06:0'] and d['plans']==saved
for fields in [{'activity_id':'missing','effort':'as_intended'},{'activity_id':'run','effort':'as_intended','rpe':11},{'activity_id':'run','effort':'as_intended','heart_rate_issue':'false'}]:
 try:progression.report(d,'2026-10-06',0,fields,done,'2026-10-06');raise AssertionError('Invalid report accepted')
 except ValueError:pass
print('PASS swim metric coverage, stroke separation, unknowns, run units, unplanned/matched feedback identity, symptom retention and validation')
