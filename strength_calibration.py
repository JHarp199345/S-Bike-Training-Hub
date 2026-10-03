"""Submaximal reported-set anchors, using the hub's existing Epley estimate."""
import math
import lifting

EXERCISES=('BB squat','BB bench press','BB row')
SHARES={
 'BB squat':{'quads':35,'glutes':30,'hamstrings':15,'adductors':10,'lower_back':10},
 'BB bench press':{'pecs':50,'triceps':30,'shoulders':20},
 'BB row':{'lats':40,'scapula':20,'biceps':20,'lower_back':20},
 'Chair squat':{'quads':35,'glutes':30,'hamstrings':15,'adductors':10,'lower_back':10},
 'Incline push-up':{'pecs':45,'triceps':25,'shoulders':15,'abs':15},
 'Resistance-band row':{'lats':40,'scapula':30,'biceps':30},
 'Glute bridge':{'glutes':60,'hamstrings':30,'lower_back':10},
 'Dead bug':{'abs':70,'obliques':20,'hip_flexors':10}}

def anchors(raw):
 if not isinstance(raw,list) or len(raw)>30:raise ValueError('Give at most 30 reported lifting sets')
 out={}
 for x in raw:
  if not isinstance(x,dict):raise ValueError('Each reported set must be an exercise record')
  name=x.get('name');unit=x.get('unit','lb')
  if name not in EXERCISES or unit not in lifting.KG:raise ValueError('Choose a starter lift and lb or kg')
  weight=x.get('weight');reps=x.get('reps');rir=x.get('rir',2)
  if isinstance(weight,bool) or not isinstance(weight,(int,float)) or not math.isfinite(weight) or not 0<weight<=1000:raise ValueError('Reported weight must be positive and at most 1000')
  if isinstance(reps,bool) or not isinstance(reps,int) or not 3<=reps<=15:raise ValueError('Use a reported set of 3–15 repetitions')
  if isinstance(rir,bool) or not isinstance(rir,int) or not 0<=rir<=5:raise ValueError('Repetitions in reserve is 0–5')
  kg=weight*lifting.KG[unit];out[name]={**x,'unit':unit,'rir':rir,'e1rm_kg':lifting.one_rm(kg,reps,rir),'method':'Epley from reported submaximal set; approximate, exercise-specific'}
 return out

def prescribe(anchor,level,week,recovery=False):
 # Deliberately below strength-specialist loads. No predicted increase to an estimated max.
 pct={'easy':.50,'moderate':.55,'higher':.60}[level]
 if recovery or week==0:pct=.45
 unit=anchor['unit'];step=2.5 if unit=='lb' else 1
 weight=anchor['e1rm_kg']*pct/lifting.KG[unit]
 weight=min(anchor['weight'],max(step,math.floor(weight/step)*step))
 return weight,{'estimated_max':round(anchor['e1rm_kg']/lifting.KG[unit],1),'unit':unit,'fraction':pct,'reported_set':anchor,'note':'Round down to available equipment; reduce further to keep 3+ reps in reserve. No automatic estimated-max growth.'}
