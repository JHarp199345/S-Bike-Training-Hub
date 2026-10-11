import asyncio
import copy
import json
import os
import pathlib
import sys
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import event_directory as directory
import coach
import mapserver

class DirectoryTests(unittest.TestCase):
    def fixture(self):
        return {'races':[{'race':{'race_id':12,'name':'Example race','url':'https://example.org/listing','external_race_url':'https://example.org/race','timezone':'America/Los_Angeles','address':{'city':'Sampletown','state':'CA'},'events':[{'event_id':1,'name':'5K','event_type':'running_race','distance':'5K','start_time':'11/01/2026 08:00'},{'event_id':2,'name':'10K','event_type':'running_race','start_time':'11/01/2026 09:00'}]}}]}
    def test_categories_dates_links(self):
        events=directory.normalize(self.fixture(),'2026-10-10','2027-10-10')
        self.assertEqual(len(events),2)
        self.assertNotEqual(events[0]['source_id'],events[1]['source_id'])
        self.assertEqual(events[0]['date'],'2026-11-01')
        self.assertEqual(events[0]['time'],'08:00')
        self.assertEqual(events[0]['website'],'https://example.org/race')
        self.assertEqual(directory.normalize(self.fixture(),'2026-11-02','2027-01-01'),[])
    def test_setup_gate_no_network(self):
        with patch.dict(os.environ,{},clear=True),patch.object(directory.urllib.request,'urlopen') as request:
            self.assertEqual(directory.search({})['status'],'setup_required')
            request.assert_not_called()
    def test_bounded_request_and_cache(self):
        directory._cache.clear()
        response=MagicMock();response.read.return_value=json.dumps(self.fixture()).encode();response.__enter__.return_value=response
        with patch.dict(os.environ,{'HUB_RUNSIGNUP_API_REG':'test','HUB_RUNSIGNUP_API_REG_SECRET':'secret'}),patch.object(directory.urllib.request,'urlopen',return_value=response) as request:
            result=directory.search({'start':'2026-10-10','end':'2027-01-01','name':'Example','sport':'run'})
            self.assertEqual(len(result['events']),2)
            directory.search({'start':'2026-10-10','end':'2027-01-01','name':'Example','sport':'run'})
            self.assertEqual(request.call_count,1)
            url=request.call_args.args[0].full_url
            self.assertIn('results_per_page=30',url)
            self.assertNotIn('secret',url)
            with self.assertRaises(ValueError):directory.search({'start':'2026-10-10','end':'2028-10-10'})
    def test_schedule_preserves_program_and_distinguishes_categories(self):
        data={'plans':{'2026-10-10':{'sessions':[{'sport':'swim'}]}},'program_goal':{'goal':'Original goal'},'events':[]}
        before=copy.deepcopy(data)
        for event in directory.normalize(self.fixture(),'2026-10-10','2027-10-10'):
            coach.add_event(data,event['date'],event['name'],sport=event['sport'],metadata=event)
        self.assertEqual(data['plans'],before['plans']);self.assertEqual(data['program_goal'],before['program_goal'])
        self.assertEqual(len(data['events']),2)
        event=directory.normalize(self.fixture(),'2026-10-10','2027-10-10')[0]
        coach.add_event(data,event['date'],event['name'],sport=event['sport'],metadata=event)
        self.assertEqual(len(data['events']),2)
        self.assertEqual(directory.metadata({'website':'javascript:alert(1)','organizer_artwork':'https://example.org/image','artwork_permission':False}),{})
        self.assertIsNone(directory.safe_url('http://[bad'))
        with self.assertRaises(ValueError):coach.add_event(data,'2026-99-01','Bad date')
        self.assertEqual(coach.add_event(data,'2026-11-02','Lifting meet',sport='gym')['sport'],'gym')
    def test_route_without_athlete_storage(self):
        with patch.dict(os.environ,{},clear=True):
            status,_,body,_=asyncio.run(mapserver.handle(None,b'GET','/api/coach/event-directory?name=Example',b'','localhost'))
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['status'],'setup_required')

if __name__=='__main__':unittest.main()
