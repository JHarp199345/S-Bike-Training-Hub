import sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import copy,unittest
import program_builder as B
import starter_programs as S
class StarterTests(unittest.TestCase):
 def proposal(self,days=84,**kw):
  return B.propose({'plans':{}},{'start':'2026-10-02','horizon_days':days,'sport':'general','hours':4,'priorities':{'ride':'improve','swim':'improve','gym':'maintain','run':'pause'},**kw},'2026-10-02',{'status':'hold'})
 def test_horizon_and_three_comparable_doses(self):
  for days in (42,84,140):
   d={'plans':{}};original=copy.deepcopy(d);p=self.proposal(days);r=S.build(d,p)
   self.assertEqual(d,original);self.assertEqual(r['detail_end'],('2026-11-13' if days==42 else '2026-12-25'))
   self.assertEqual(len(r['candidates']),3)
   self.assertEqual(sorted(c['total_minutes'] for c in r['candidates']),[c['total_minutes'] for c in r['candidates']])
   self.assertTrue(all(date<r['detail_end'] for date in r['plans']))
 def test_saved_workouts_and_history_survive_acceptance(self):
  d={'plans':{'2026-10-02':{'sport':'swim','minutes':60}},'checkins':{'2026-10-01':{'journal':'History'}}}
  before=copy.deepcopy(d);p=self.proposal();p['starter']=S.build(d,p);B.accept(d,p)
  self.assertEqual(d['plans']['2026-10-02'],before['plans']['2026-10-02']);self.assertEqual(d['checkins'],before['checkins'])
  self.assertNotIn('starter',d['program_goal']);self.assertGreater(len(d['plans']),1)
 def test_no_run_under_hold_and_unknown_not_zero(self):
  r=S.build({'plans':{}},{**self.proposal(),'neutral_forecast':False})
  self.assertTrue(all(s['sport']!='run' for p in r['plans'].values() for s in p['sessions']))
  self.assertTrue(r['candidates'][0]['unknown_metrics'])
  self.assertIsNone(next(x['end'] for x in r['candidates'][0]['summary'] if x['key']=='cardio_conditioning'))
 def test_budget_and_basic_lifts(self):
  p=self.proposal();r=S.build({'plans':{}},p)
  for c in r['candidates']:
   self.assertTrue(all(w['minutes']<=p['hours']*60 for w in c['journey']))
   self.assertTrue(all(s['steps'] for plan in c['plans'].values() for s in plan['sessions']))
  lifts=S.workout('gym',30,3,'moderate','new','barbell',{},lift_focus='upper_push')['lifts']
  self.assertIn('BB bench press',[x['name'] for x in lifts]);self.assertTrue(all(x['weight'] is None for x in lifts))
  self.assertEqual([x['role'] for x in lifts],['main','main','prehab'])          # 30 min: 2 main + 1 minor
  basic=S.workout('gym',45,3,'moderate','new','basic',{})['lifts']
  self.assertEqual(len(basic),5);self.assertTrue(all(x['kind'] in ('bodyweight','band') for x in basic))
 def test_known_bike_forecast_uses_power_and_ftp(self):
  p=self.proposal(priorities={'ride':'improve','swim':'pause','gym':'pause','run':'pause'})
  load={'profile':{'ftp':180},'systems':{'engine':{'fitness':10,'fatigue':12},'muscle':{'fitness':3,'fatigue':4},'impact':{'fitness':0,'fatigue':0}}}
  from unittest.mock import patch
  with patch('loads.readiness',return_value={}):r=S.build({'plans':{}},p,load=load)
  end=[next(m for m in c['summary'] if m['key']=='cardio_conditioning')['end'] for c in r['candidates']]
  self.assertTrue(all(x is not None for x in end));self.assertLess(end[0],end[-1])
 def test_dated_placement_validated(self):
  f={'start':'2026-10-02','horizon_days':7,'sport':'ride','hours':3,'phases':[{'start':'2026-10-02','days':7,'kind':'build','profile':'ride','date_placements':{'2026-10-03':[{'sport':'swim','purpose':'Practice'}]}}]}
  p=B.propose({},f,'2026-10-02',{'status':'hold'});self.assertTrue(any(s['sport']=='swim' and s['date']=='2026-10-03' for s in p['weeks'][0]['slots']))
  f['phases'][0]['date_placements']={'2026-11-03':[{'sport':'swim','purpose':'Practice'}]}
  with self.assertRaises(ValueError):B.propose({},f,'2026-10-02',{'status':'hold'})
 def test_neutral_priors_are_labeled_and_not_saved_as_observations(self):
  d={'plans':{}};load={};before=copy.deepcopy(d);r=S.build(d,self.proposal(),load=load)
  self.assertEqual(d,before);self.assertEqual(load,{})
  self.assertTrue(r['assumptions']);self.assertTrue(all(m['end'] is not None for m in r['candidates'][0]['summary']))
 def test_reported_sets_prescribe_weights_and_validate(self):
  import strength_calibration as C
  anchor=C.anchors([{'name':'BB bench press','weight':100,'reps':10,'rir':2,'unit':'lb'}])['BB bench press']
  self.assertAlmostEqual(anchor['e1rm_kg'],100*.45359237*1.4)
  weight,basis=C.prescribe(anchor,'moderate',2);self.assertEqual(weight,75)
  self.assertLessEqual(weight,anchor['weight'])
  with self.assertRaises(ValueError):C.anchors([{'name':'BB row','weight':100,'reps':40}])
  w=S.workout('gym',30,2,'moderate','new','barbell',{}, {'BB bench press':anchor},lift_focus='upper_push')
  bench=next(x for x in w['lifts'] if x['name']=='BB bench press')
  self.assertEqual(bench['weight'],85);self.assertTrue(bench['regions'])        # base: 62% of the estimated max
  heavy=S.workout('gym',30,2,'moderate','new','barbell',{}, {'BB bench press':anchor},stage='build',lift_focus='upper_push')
  self.assertEqual(next(x for x in heavy['lifts'] if x['name']=='BB bench press')['weight'],100)   # build: 80%, never over the reported set
 def test_program_shape_builds_to_peaks_then_tapers(self):
  import datetime as dt
  f={'start':'2026-10-05','target':'2026-12-27','sport':'tri','hours':4,'goal':'First sprint triathlon','assessment':'week','starter_level':'moderate',
     'priorities':{'ride':'improve','swim':'improve','run':'improve','gym':'maintain'}}
  p=B.propose({'plans':{}},f,'2026-10-05',{'status':'open_for_review'});r=S.build({'plans':{}},p,today='2026-10-05')
  for c in r['candidates']:
   j=c['journey'];share=[w['share_of_available'] for w in j]
   self.assertTrue(all(w['minutes']<=240 for w in j))
   self.assertEqual(j[0]['shape'],'test');self.assertLessEqual(share[0],.6)   # three tests, the running calibration up to 60 min
   self.assertLess(share[1],.6)
   pv=[w for w in j if w['shape']=='peak_volume'];pp=[w for w in j if w['shape']=='peak_performance']
   self.assertTrue(pv and pp)
   self.assertGreaterEqual(max(w['share_of_available'] for w in pv),.75)
   self.assertLess(pv[-1]['start'],pp[0]['start'])
   self.assertEqual(j[-1]['shape'],'race');self.assertLessEqual(share[-1],.45)
   self.assertLess(max(w['share_of_available'] for w in j if w['shape']=='taper'),max(w['share_of_available'] for w in pv))
   # no consecutive building week more than ~12% bigger than the last
   b=[w['minutes'] for w in j if w['shape'] in ('build','peak_volume')];self.assertTrue(all(y<=x*1.2+5 for x,y in zip(b,b[1:])))
  plans=r['plans'];names=lambda a,b_:[s['name'] for d,pl in plans.items() if a<=d<b_ for s in pl['sessions']]
  wk=lambda w:(j[w-1]['start'],(dt.date.fromisoformat(j[w-1]['start'])+dt.timedelta(7)).isoformat())
  j=next(c for c in r['candidates'] if c['level']=='moderate')['journey']
  first=names(*wk(1));self.assertTrue(any('FTP test' in n for n in first) and any('Swim test' in n for n in first))
  peak=[n for w in j if w['shape']=='peak_performance' for n in names(*wk(w['week']))]
  self.assertTrue(any('Race-pace' in n for n in peak) and any('Brick run' in n for n in peak))
  pvn=max(len(names(*wk(w['week']))) for w in j if w['shape']=='peak_volume')
  self.assertGreater(pvn,len(names(*wk(2))))
  self.assertIn('Race day',plans['2026-12-27']['sessions'][0]['name'])
  for date,pl in plans.items():                                # a brick never lands the day after another run
   if any('Brick' in s['name'] for s in pl['sessions']):
    for k in (-1,1):
     near=plans.get((dt.date.fromisoformat(date)+dt.timedelta(days=k)).isoformat(),{}).get('sessions',[])
     self.assertFalse(any(s['sport']=='run' for s in near),date)
  self.assertNotIn('2026-12-26',plans)                       # rest the day before the race
 def test_conservative_level_stays_well_under_time(self):
  f={'start':'2026-10-05','horizon_days':84,'sport':'general','hours':6,'starter_level':'easy','priorities':{'ride':'improve','swim':'maintain','gym':'maintain','run':'pause'}}
  p=B.propose({'plans':{}},f,'2026-10-05',{'status':'hold'});r=S.build({'plans':{}},p,today='2026-10-05')
  easy=next(c for c in r['candidates'] if c['level']=='easy')
  self.assertTrue(all(w['share_of_available']<=.81 for w in easy['journey']))
  self.assertLessEqual(easy['journey'][0]['share_of_available'],.5)
 def test_starter_strength_can_be_checked_off(self):
  import lifting
  for equipment in ('basic','barbell'):
   w=S.workout('gym',30,2,'moderate','new',equipment,{})
   d={'plans':{'2026-06-11':{'sessions':[w]}},'checkins':{}}
   log=lifting.log(d,'2026-06-11',None,6,7)
   self.assertTrue(log and all('seconds' in x and 'per_side' in x for x in w['lifts']))
if __name__=='__main__':unittest.main()
