"""Explicit neutral scenario assumptions. Never written into measured load history."""
import copy
import lifting

RATES={'bike':{'engine':.6,'impact':0,'muscle':.1},'swim':{'engine':.6,'impact':0,'muscle':.05},'gym':{'engine':.3,'impact':0,'muscle':None},'run':{'engine':.6,'impact':2,'muscle':.5}}

def scenario(load):
 s=copy.deepcopy(load or {});notes=[]
 s['planning_priors']={'dose_per_minute':RATES}
 notes.append('Missing sport dose: provisional easy-effort rates (cardio 0.6 points/min; gym 0.3); not measured population means.')
 for k in ('engine','impact','muscle'):
  x=s.setdefault('systems',{}).setdefault(k,{})
  for field in ('fitness','fatigue'):
   if x.get(field) is None:x[field]=0;notes.append(k+' '+field+': neutral zero starting backlog / conditioning; unmeasured.')
  for field,val in {'form':0,'acwr':None,'last7':0,'prev7':0,'usual_week':150 if k=='engine' else 80}.items():x.setdefault(field,val)
 s.setdefault('history_days',0);s.setdefault('days',[])
 remodel=s['systems']['impact'].setdefault('tissue',{}).setdefault('remodeling',{})
 if remodel.get('score') is None:
  remodel.update(score=0,reference_points=40,threshold_blocks=1.5,projection=[])
  notes.append('Running backlog: neutral zero, not clearance; existing real running gate remains authoritative.')
 swim=s.setdefault('swim_recovery',{})
 for key,val in {'score':0,'recent':0,'history_component':0,'reference_units':1000,'threshold_blocks':1.5}.items():
  if swim.get(key) is None:swim[key]=val;notes.append('Swim '+key+': provisional starting reference, replaced by personal data.')
 for key,name in lifting.regions().items():
  s.setdefault('lifting',{}).setdefault('regions',{}).setdefault(key,{'name':name,'blocks':0,'reference':lifting.DEFAULT_REF})
 s['planning_priors']['swim_units_per_minute']=1000/90
 return s,notes
