import sys,copy,datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import coach,training_block,lifting
now=coach.today()
d={'plans':{now:{'sessions':[{'sport':'gym','minutes':30,'name':'Strength','lifts':[{'name':'Example','sets':2,'reps':10,'weight':20,'unit':'lb','kind':'strain','regions':{'quads':1},'scored':True}], 'steps':[]},{'sport':'ride','minutes':30,'name':'Easy ride','steps':[]}]}},'checkins':{}}
original=copy.deepcopy(d['plans'][now]['sessions'][0])
coach.session_action(d,now,0,'skip')
s=d['plans'][now]['sessions'];assert len(s)==2 and s[1]['name']=='Easy ride';assert s[0]['sport']=='rest' and s[0]['minutes']==0 and not s[0].get('lifts')
coach.session_action(d,now,0,'restore');assert d['plans'][now]['sessions'][0]==original
coach.session_action(d,now,0,'delete');assert len(d['plans'][now]['sessions'])==1;assert d['removed_workouts'][0]['session']==original
for action in ['delete','skip']:
 c=copy.deepcopy(d);c['training_feedback']={now+':0':{'effort':'as_intended'}}
 try:coach.session_action(c,now,0,action)
 except ValueError:pass
 else:raise AssertionError('actual report must be protected')
ls=lifting.clean({'plans':{},'checkins':{}},[{'name':'New exercise','sets':8,'reps':10,'section':'warmup','block':'Block 1','block_repeats':4}],draft=True)
assert ls[0]['section']=='warmup' and ls[0]['block']=='Block 1' and ls[0]['sets']==8
print('PASS skip keeps indices, zero-dose placeholder, restore, delete archive, actual-report protection, section/block metadata')
