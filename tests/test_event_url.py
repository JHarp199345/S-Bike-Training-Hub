import asyncio
import copy
import json
import pathlib
import sys
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import event_url
import coach
import mapserver

FIXTURE='''<html><head><title>Example</title><script type="application/ld+json">{"@graph":[{"@type":"SportsEvent","name":"Lake Swim 2 km","startDate":"2027-04-03T09:00:00-07:00","description":"Open water swimming over 2 km","location":{"address":{"addressLocality":"Sample City"}},"image":"/logo.png"},{"@type":"Event","name":"Lake Swim 5 km","startDate":"2027-04-04","description":"Swim 5 km"}]}</script></head><body>Public event</body></html>'''
class URLTests(unittest.TestCase):
 def test_structured_multiple_candidates(self):
  result=event_url.parse_page(FIXTURE,'https://example.org/race')
  self.assertEqual(len(result['candidates']),2)
  first=result['candidates'][0]
  self.assertEqual((first['date'],first['time'],first['sport'],first['distance'],first['location']),('2027-04-03','09:00','swim','2 km','Sample City'))
  self.assertEqual(first['image_candidates'],['https://example.org/logo.png'])
 def test_missing_and_ambiguous_are_not_invented(self):
  result=event_url.parse_page('<title>Run Festival 5K and 10K</title>','https://example.org')
  event=result['candidates'][0]
  self.assertEqual(event['date'],'');self.assertEqual(event['distance'],'')
  self.assertEqual(event['distance_choices'],['5K','10K'])
  self.assertIn('date',event['missing'])
 def test_private_targets(self):
  for target in ['file:///etc/passwd','http://user:pass@example.org','http://example.org:8891']:
   with self.assertRaises(ValueError):event_url.public_target(target)
  for address in ['127.0.0.1','192.168.1.1','169.254.169.254','::1']:
   with patch.object(event_url.socket,'getaddrinfo',return_value=[(None,None,None,None,(address,80))]):
    with self.assertRaises(ValueError):event_url.public_target('http://example.org')
 def test_redirects_rechecked(self):
  response=MagicMock(status=302);response.getheader.return_value='http://127.0.0.1/secret'
  connection=MagicMock();connection.getresponse.return_value=response
  with patch.object(event_url,'public_target',side_effect=[(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit('https://example.org'),['93.184.216.34']),ValueError('Private target')]),patch.object(event_url,'PinnedHTTPS',return_value=connection):
   with self.assertRaises(ValueError):event_url.fetch_page('https://example.org')
  connection.close.assert_called_once()
 def test_preview_route_no_save(self):
  with patch.object(event_url,'fetch_page',return_value=(FIXTURE,'https://example.org/race')),patch.object(coach,'save') as save:
   status,_,body,_=asyncio.run(mapserver.handle(None,b'POST','/api/coach/event-url-preview',json.dumps({'url':'https://example.org/race'}).encode(),'localhost'))
  self.assertEqual(status,200);self.assertEqual(len(json.loads(body)['candidates']),2);save.assert_not_called()
 def test_approved_event_preserves_workout_data(self):
  data={'plans':{'2026-10-10':{'sessions':[{'sport':'swim','completion':{'minutes':40}},{'sport':'ride','minutes':30}]}},'program_goal':{'goal':'Existing goal'},'checkins':{'2026-10-10':{'fatigue':3}},'events':[]}
  before=copy.deepcopy(data)
  event=event_url.parse_page(FIXTURE,'https://example.org/race')['candidates'][0]
  coach.add_event(data,event['date'],event['name'],sport=event['sport'],metadata=event)
  for key in ('plans','program_goal','checkins'):self.assertEqual(data[key],before[key])
  self.assertEqual(len(data['events']),1)
  self.assertNotIn('organizer_artwork',data['events'][0])
if __name__=='__main__':unittest.main()
