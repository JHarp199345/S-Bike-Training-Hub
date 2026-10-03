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
  lifts=S.workout('gym',30,3,'moderate','new','barbell',{})['lifts']
  self.assertIn('BB bench press',[x['name'] for x in lifts]);self.assertTrue(all(x['weight'] is None for x in lifts))
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
  w=S.workout('gym',30,2,'moderate','new','barbell',{}, {'BB bench press':anchor})
  bench=next(x for x in w['lifts'] if x['name']=='BB bench press')
  self.assertEqual(bench['weight'],75);self.assertTrue(bench['regions'])
if __name__=='__main__':unittest.main()
