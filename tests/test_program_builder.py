import asyncio,copy,json,pathlib,sys,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,mapserver,program_builder as B
class BuilderTests(unittest.TestCase):
 def fields(self,**kw):return dict(start='2026-10-02',target='2027-01-17',goal='Demo 5K',sport='run',hours=4,focus='balanced',assessment='week',**kw)
 def test_complete_timeline_and_preserved_workouts(self):
  d={'plans':{'x':{'sessions':[{'sport':'swim','minutes':45}]}},'phase_profiles':[]};before=copy.deepcopy(d['plans'])
  r=B.propose(d,self.fields(),'2026-10-02',{'status':'hold'})
  self.assertEqual(r['phases'][0]['stage'],'assessment');self.assertEqual(r['phases'][1]['stage'],'recovery')
  self.assertEqual(r['phases'][-1]['end'],'2027-01-17')
  for a,b in zip(r['phases'],r['phases'][1:]):self.assertEqual(a['end'],b['start'])
  self.assertFalse(any(s['sport']=='run' for w in r['weeks'] for s in w['slots']))
  B.accept(d,r);self.assertEqual(d['plans'],before);self.assertEqual(len(d['phase_profiles']),len(r['phases']))
 def test_fresh_and_last_minute(self):
  r=B.propose({},self.fields(entry='build'),'2026-10-02',{'status':'open_for_review'})
  self.assertNotIn('recovery',[p['stage'] for p in r['phases']]);self.assertNotIn('base',[p['stage'] for p in r['phases']])
  f=self.fields();f['target']='2026-10-05';r=B.propose({},f,'2026-10-02',{'status':'hold'})
  self.assertEqual([p['stage'] for p in r['phases']],['taper'])
 def test_reviewed_program_preserves_calendar_and_respects_hold(self):
  f=self.fields();f['phases']=[{'start':'2026-10-02','days':84,'profile':'ride','kind':'base','review_criteria':['Review delayed leg response'], 'weekly_pattern':[{'sport':'run','purpose':'Conditional run'}]*7}, {'start':'2026-12-25','days':24,'profile':'ride','kind':'taper'}]
  d={'plans':{'2026-10-02':{'sessions':[{'sport':'swim','minutes':45,'name':'Existing swim'}]}}}
  r=B.propose(d,f,'2026-10-02',{'status':'hold'})
  self.assertEqual(r['weeks'][0]['slots'][0]['purpose'],'Existing swim')
  self.assertFalse(any(x['sport']=='run' for w in r['weeks'] for x in w['slots']))
  self.assertEqual(r['weeks'][-1]['slots'][-1]['date'],'2027-01-17')
  B.accept(d,r)
  self.assertEqual(d['phase_profiles'][0]['review_criteria'],['Review delayed leg response'])
  before=copy.deepcopy(d)
  f['phases'][1]['start']='2026-12-26'
  with self.assertRaises(ValueError):B.propose(d,f,'2026-10-02',{'status':'hold'})
  self.assertEqual(d,before)
 def test_saved_program_controls_template_phase_and_event_advice(self):
  import datetime as dt,programming
  d={'events':[{'kind':'race','sport':'run','name':'Demo 5K','date':'2027-01-17'}],
     'program_goal':{'target':'2027-01-17'},'phase_profiles':[
      {'id':'2026-10-02','start':'2026-10-02','end':'2026-11-02','kind':'recovery','label':'Recovery'},
      {'id':'2027-01-04','start':'2027-01-04','end':'2027-01-18','kind':'taper','label':'Final preparation'}]}
  self.assertEqual(programming.phase(d,dt.date(2026,10,15))['phase'],'recovery')
  text=' '.join(coach.upcoming(d,'2026-10-02',98)[0]['notes'])
  self.assertIn('2027-01-04',text);self.assertNotIn('3 days of taper',text);self.assertIn('not clearance',text)
 def test_api_preview_is_read_only(self):
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    base=pathlib.Path(tmp);(base/'rides').mkdir();d=coach.load(base/'coach.json');coach.save(d);before=(base/'coach.json').read_bytes()
    bridge=SimpleNamespace(csv_path=str(base/'rides'/'test.csv'),workouts=[],profile={'ftp':180})
    with patch.object(coach,'today',return_value='2026-10-02'),patch.object(mapserver,'load_state',return_value={}):
     for action in ('preview','accept'):
      code,_,body,_=await mapserver.coach_api(bridge,b'POST','/api/coach/program-builder','/api/coach/program-builder',json.dumps({**self.fields(),'action':action}).encode())
      self.assertEqual(code,200,body)
      if action=='preview':self.assertEqual((base/'coach.json').read_bytes(),before)
     self.assertTrue(coach.load(base/'coach.json')['program_macro_weeks'])
  asyncio.run(run())
if __name__=='__main__':unittest.main()
