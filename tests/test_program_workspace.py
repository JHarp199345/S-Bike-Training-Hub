import sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import copy,unittest
import program_builder as B
class WorkspaceTests(unittest.TestCase):
 def fields(self,**kw):
  return dict(start='2026-10-10',target=None,horizon_days=84,sport='ride',hours=7,entry='build',assessment='existing',focus='ride',priorities={'ride':'improve','swim':'maintain','gym':'pause','run':'pause'},**kw)
 def test_ongoing_is_not_an_event_and_only_selected_sports(self):
  original={'plans':{},'phase_profiles':[]};before=copy.deepcopy(original)
  r=B.propose(original,self.fields(),'2026-10-10',{'status':'hold'})
  self.assertEqual(original,before);self.assertIsNone(r['target']);self.assertEqual(r['end'],'2027-01-02')
  self.assertFalse(any(p['stage'] in ('specific','taper') for p in r['phases']))
  self.assertTrue(all(s['sport'] in ('ride','swim','rest') for w in r['weeks'] for s in w['slots']))
 def test_revision_retains_past_and_all_workout_history(self):
  d={'phase_profiles':[{'id':'2026-10-02','start':'2026-10-02','end':'2026-11-02','days':31,'weeks':4.43,'kind':'recovery','profile':'recovery','label':'Recovery','modes':{s:'maintain' for s in B.P.SPORTS},'weights':{}}], 'program_goal':{'goal':'Old'},'plans':{'2026-10-11':{'sport':'gym','minutes':30}},'checkins':{'2026-10-09':{'journal':'Comfortable'}}}
  prior=copy.deepcopy(d);r=B.propose(d,self.fields(),'2026-10-10',{'status':'hold'});B.accept(d,r)
  self.assertEqual(d['phase_profiles'][0]['end'],'2026-10-10');self.assertEqual(d['plans'],prior['plans']);self.assertEqual(d['checkins'],prior['checkins'])
  self.assertEqual(d['program_history'][0]['goal'],prior['program_goal']);self.assertTrue(r['changes']['conflicts'])
 def test_manual_multisession_and_hold(self):
  f=self.fields();f['horizon_days']=7;f['phases']=[{'start':f['start'],'days':7,'kind':'build','stage':'build','profile':'ride','modes':f['priorities'],'weekly_pattern':[[{'sport':'swim','purpose':'Technique'},{'sport':'run','purpose':'Held'}]]*7}]
  r=B.propose({},f,'2026-10-10',{'status':'hold'});self.assertEqual(len(r['weeks'][0]['slots']),14);self.assertFalse(any(s['sport']=='run' for s in r['weeks'][0]['slots']))
 def test_rest_days_and_first_sport(self):
  f=self.fields(schedule_options={'available_days':[0,1,2,3,4,5,6],'rest_days':[0,6],'first_sport':'swim','allow_doubles':True})
  r=B.propose({},f,'2026-10-10',{'status':'hold'});slots=r['weeks'][0]['slots'];self.assertEqual(next(x for x in slots if x['sport']!='rest')['sport'],'swim')
  import datetime as dt
  self.assertTrue(all(x['sport']=='rest' for w in r['weeks'] for x in w['slots'] if dt.date.fromisoformat(x['date']).weekday() in (0,6)))
 def test_validation_is_atomic(self):
  d={'phase_profiles':[]};before=copy.deepcopy(d);f=self.fields();f['phases']=[{'start':f['start'],'days':84,'kind':'build','color':'bad','profile':'ride'}]
  with self.assertRaises(ValueError):B.propose(d,f,'2026-10-10',{'status':'hold'})
  self.assertEqual(d,before)
if __name__=='__main__':unittest.main()
