import sys,pathlib,copy
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,session_explanations as E,progression,lifting
from unittest.mock import patch
D='2026-10-03'
d={'plans':{},'checkins':{}}
import phaseblend
phaseblend.save(d,{'start':D,'days':28,'profile':'recovery','kind':'recovery','purpose':'Keep training easy'},D)
coach.set_sessions(d,D,[{'sport':'test','minutes':25,'name':'Test'},{'sport':'gym','name':'Arms','minutes':30,'lifts':[{'name':'Cable curl','kind':'cable','sets':2,'reps':8,'weight':20,'unit':'lb','regions':{'biceps':100}}]}]);d['plans'][D]['test']='ftp'
ctx=E.describe(d,D,0);assert ctx['test']['id']=='ftp' and '+10 W' in ctx['test']['how']
before=copy.deepcopy(d['plans']);a=E.update(d,D,0,'Set bike targets during this check week.',ctx['context_token']);assert a['changed']
assert not E.update(d,D,0,'Set bike targets during this check week.',ctx['context_token'])['changed']
assert d['plans'][D]['sessions'][0]['minutes']==25 and d['plans'][D]['sessions'][1]==before[D]['sessions'][1]
coach.set_sessions(d,'2026-10-04',[{'sport':'swim','name':'Easy swim','minutes':40}]);assert E.describe(d,D,0)['needs_review']
assert len(E.review(d,D))==1
try:E.update(d,D,0,'Stale text',ctx['context_token']);raise AssertionError('stale context accepted')
except ValueError:pass
for key,(title,_,_) in E.TEST_PURPOSES.items():
 d['plans'][D]['test']=key;out=E.guide(d,D,{'name':title,'sport':'run' if 'run' in key else 'swim' if key=='css' else 'test'});assert out and out['purpose'] and out['how'] and out['after']
d['plans'][D]['test']='ftp'
lifting.log(d,D,[{}],5,8)
for effort in ('as_intended','too_easy','too_hard'):
 report=progression.report(d,D,1,{'effort':effort},{},D)
 assert report['sport']=='gym' and report['actual_minutes']==30 and report['effort']==effort
try:progression.report(d,D,0,{'effort':'as_intended'},{},D);raise AssertionError('unfinished test accepted')
except ValueError:pass
print('PASS test catalog, explanation freshness/idempotency, dose preservation and lifting reports without watch data')
