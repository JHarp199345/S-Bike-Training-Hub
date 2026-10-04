"""Plain-language session purpose and reusable test guides. Never changes a training dose."""
import copy
import datetime as dt
import hashlib
import json

TEST_PURPOSES = {
 'ftp': ('FTP ramp test', 'Find a working cycling power estimate so future rides use targets that fit you.', 'Record the result and how the test felt. It updates cycling targets; it does not clear other recovery holds.'),
 'big_gear': ('Big-gear test', 'Check how much power your legs can hold while pedaling slowly.', 'Record your best three-minute power and how your legs felt. This helps set strength-focused bike targets.'),
 'diagnostic': ('Morning diagnostic', 'Compare your heart-rate response with your own usual morning readings.', 'Record heart rate and how you feel. One unusual reading is a reason to review, not a diagnosis.'),
 'css': ('Swim CSS test', 'Estimate a steady swim pace from two timed swims.', 'Record both times. The Hub uses them to set swim paces.'),
 'benchmark_run': ('Benchmark run', 'Compare an easy run with earlier runs on the same route.', 'Report effort and discomfort, then check in over the next two mornings. A good time alone does not prove recovery.'),
 'run_calibration': ('Running calibration', 'Learn how much easy running you can carry and recover from.', 'Record the run and any reason for stopping early. Check in during the eight-day running pause; day nine reviews your block.'),
}


def sessions(plan):
 import training_block
 return training_block.sessions(plan or {})


def guide(d, date, s):
 import calibration
 plan=d.get('plans',{}).get(date) or {}
 key=s.get('test')
 if not key:
  name=(s.get('name') or '').lower()
  key=next((k for k,t in calibration.TESTS.items() if t['name'].lower() in name),None)
 if not key and plan.get('test'):
  candidate=plan['test']; expected=calibration.TESTS.get(candidate,{}).get('sport')
  if s.get('sport')==expected or (s.get('sport')=='test' and expected in ('test','ride')):key=candidate
 if key not in TEST_PURPOSES:return None
 title,purpose,after=TEST_PURPOSES[key]
 return {'id':key,'title':title,'purpose':purpose,'how':calibration.TESTS[key]['how'],'after':after,
         'caution':'Start only when the current plan and recovery checks allow it. Stop for pain, dizziness, or loss of control.',
         'image':'/web/sports/morning-diagnostic-sunrise.jpg' if key=='diagnostic' else '/web/sports/phase-foundation.jpg' if key=='css' else '/web/sports/community-road-run.jpg' if key in ('benchmark_run','run_calibration') else '/web/sports/test-assessment.jpg'}


def describe(d,date,index,s=None):
 plan=d.get('plans',{}).get(date) or {};ss=sessions(plan)
 s=copy.deepcopy(s if s is not None else ss[index])
 phase=next((p for p in d.get('phase_profiles',[]) if p['start']<=date<p['end']),{})
 nearby=[]
 day=dt.date.fromisoformat(date)
 for offset in range(-2,4):
  when=(day+dt.timedelta(days=offset)).isoformat()
  for i,x in enumerate(sessions(d.get('plans',{}).get(when))):
   if when==date and i==index:continue
   nearby.append({'date':when,'name':x.get('name') or x['sport'],'sport':x['sport'],'minutes':x.get('minutes'), 'note':x.get('note'), 'steps':x.get('steps'), 'lifts':x.get('lifts')})
 dose={k:v for k,v in s.items() if k not in ('explanation','completion','missed','missed_reason','swim_outlook','coaching_context')}
 basis={'session':dose,'phase':{k:phase.get(k) for k in ('id','label','kind','purpose','modes')},'nearby':nearby,'test':plan.get('test')}
 token=hashlib.sha256(json.dumps(basis,sort_keys=True,default=str).encode()).hexdigest()[:24]
 test=guide(d,date,s)
 roles={'swim':'Keep your swim practice steady and work on smooth strokes.', 'ride':'Practice steady pedaling and build cycling endurance.',
        'gym':'Train strength and control with the planned lifts.', 'run':'Build running practice within your current load and readiness limits.',
        'rest':'Give your body time to recover before the next training.', 'walk':'Keep moving gently without adding a run.'}
 text=test['purpose'] if test else roles.get(s['sport'],'Follow the saved workout for this day.')
 if s.get('note'):text=s['note']
 if s.get('swim_plan',{}).get('why'):text=s['swim_plan']['why']
 stored=s.get('coaching_context') or {}; stale=bool(stored and stored.get('context_token')!=token)
 if stored.get('text') and not stale:text=stored['text']
 next_work=next((x for x in nearby if x['date']>=date and x['sport']!='rest'),None)
 return {'text':text,'phase':phase.get('label'),'phase_purpose':phase.get('purpose'),
         'next_workout':next_work,'nearby':[{k:x.get(k) for k in ('date','name','sport','minutes')} for x in nearby],
         'context_token':token,'needs_review':stale,'source':'assistant' if stored and not stale else 'saved_plan', 'test':test}


def update(d,date,index,text,token):
 ss=(d.get('plans',{}).get(date) or {}).get('sessions')
 if not ss or isinstance(index,bool) or not isinstance(index,int) or not 0<=index<len(ss):raise ValueError('Choose a saved session index')
 if not isinstance(text,str) or not text.strip() or len(text)>600:raise ValueError('Give a short explanation, 1–600 characters')
 context=describe(d,date,index,ss[index])
 if token!=context['context_token']:raise ValueError('Plan context changed. Read the calendar again before updating the explanation.')
 value={'text':text.strip(),'context_token':token}
 changed=ss[index].get('coaching_context')!=value
 if changed:ss[index]['coaching_context']=value
 return {'changed':changed,'explanation':describe(d,date,index,ss[index])}


def review(d,today,days=7):
 out=[]
 for offset in range(days):
  date=(dt.date.fromisoformat(today)+dt.timedelta(days=offset)).isoformat()
  for i,s in enumerate(sessions(d.get('plans',{}).get(date))):
   context=describe(d,date,i,s)
   if context['needs_review']:out.append({'date':date,'session_index':i,'name':s.get('name'),'explanation':context})
 return out
