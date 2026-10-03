import asyncio,copy,json,pathlib,sys,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,journal_album,mapserver
class AlbumTests(unittest.TestCase):
 def test_immutable_context_and_complete_month_index(self):
  d={'checkins':{'2024-02-03':{'journal':'Old entry'}},'plans':{'2026-10-02':{'sport':'swim','minutes':45}},'program_goal':{'goal':'5K'},'phase_profiles':[]}
  snapshot=journal_album.capture(d,'2026-10-02',{'headline':{'mechanical':{'remodeling_blocks':12.0}}})
  e=journal_album.append(d,'2026-10-02',{'journal':'New entry'},snapshot,request_id='a')
  d['plans']['2026-10-02']['minutes']=60;d['program_goal']['goal']='Changed'
  self.assertEqual(e['snapshot']['planned_workouts']['minutes'],45)
  self.assertEqual(e['snapshot']['program_goal']['goal'],'5K')
  self.assertEqual([x['month'] for x in journal_album.view(d)['months']],['2026-10','2024-02'])
  self.assertIsNone(journal_album.view(d)['entries'][-1]['snapshot'])
 def test_identical_reports_are_not_duplicate_revisions(self):
  d={'checkins':{},'plans':{}}
  c={'journal':'Same report','legs':4}
  e=journal_album.append(d,'2026-10-02',c,{'readings':{'value':1}},previous=copy.deepcopy(c),request_id='first')
  self.assertEqual(len(d['journal_entries']),1)
  again=journal_album.append(d,'2026-10-02',copy.deepcopy(c),{'readings':{'value':9}},request_id='another')
  self.assertIs(again,e);self.assertEqual(len(d['journal_entries']),1)
  self.assertEqual(e['snapshot']['readings']['value'],1)
  journal_album.append(d,'2026-10-02',{**c,'legs':5},{},previous=c,request_id='changed')
  self.assertEqual(len(d['journal_entries']),2)
 def test_report_survives_derived_failure_and_retry_does_not_duplicate(self):
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    base=pathlib.Path(tmp);(base/'rides').mkdir();d=coach.load(base/'coach.json');d['checkins']['2026-10-02']={'journal':'Earlier report'};coach.save(d)
    bridge=SimpleNamespace(csv_path=str(base/'rides'/'test.csv'),workouts=[],profile={'ftp':180})
    request={'date':'2026-10-02','legs':4,'journal':'Actual new report','request_id':'retry-test'}
    with patch.object(mapserver,'load_state',side_effect=RuntimeError('Derived calculation unavailable')):
     code,_,body,_=await mapserver.coach_api(bridge,b'POST','/api/coach/checkin','/api/coach/checkin',json.dumps(request).encode())
     result=json.loads(body);self.assertEqual(code,200);self.assertTrue(result['saved']);self.assertTrue(result['warning'])
     saved=coach.load(base/'coach.json');self.assertEqual(saved['checkins']['2026-10-02']['journal'],'Actual new report');self.assertEqual(len(saved['journal_entries']),2)
     code,_,_,_=await mapserver.coach_api(bridge,b'POST','/api/coach/checkin','/api/coach/checkin',json.dumps(request).encode())
     self.assertEqual(code,200);self.assertEqual(len(coach.load(base/'coach.json')['journal_entries']),2)
     request['request_id']='fast-save';request['defer_refresh']=True
     code,_,body,_=await mapserver.coach_api(bridge,b'POST','/api/coach/checkin','/api/coach/checkin',json.dumps(request).encode())
     self.assertEqual(code,200);self.assertTrue(json.loads(body)['refresh_pending'])
     self.assertEqual(coach.load(base/'coach.json')['checkins']['2026-10-02']['journal'],'Actual new report')
     before=(base/'coach.json').read_bytes()
     request['legs']=99;request['request_id']='invalid'
     code,_,_,_=await mapserver.coach_api(bridge,b'POST','/api/coach/checkin','/api/coach/checkin',json.dumps(request).encode())
     self.assertEqual(code,400);self.assertEqual((base/'coach.json').read_bytes(),before)
  asyncio.run(run())
if __name__=='__main__':unittest.main()
