import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio,unittest,json
from types import SimpleNamespace
from unittest.mock import patch
import mapserver
class GameAPITest(unittest.TestCase):
 def test_free_views_and_pack_parent_headers(self):
  for url in ['/ride','/ride/game?embedded=1&scene=game','/ride/map?embedded=1']:
   r=asyncio.run(mapserver.handle(SimpleNamespace(),b'GET',url,b'','localhost'))
   self.assertEqual(r[0],200);self.assertEqual(r[3].get('Cross-Origin-Embedder-Policy'),'require-corp')
 def test_preview_and_approval_are_explicit(self):
  with patch('pack_install.inspect',return_value={'installed':False}) as inspect:
   r=asyncio.run(mapserver.handle(SimpleNamespace(),b'POST','/api/modes/import',b'example zip','localhost'))
   self.assertEqual(r[0],200);self.assertFalse(inspect.call_args.kwargs['approve'])
   asyncio.run(mapserver.handle(SimpleNamespace(),b'POST','/api/modes/import?approve=1&replace=1',b'example zip','localhost'))
   self.assertTrue(inspect.call_args.kwargs['approve']);self.assertTrue(inspect.call_args.kwargs['replace'])
if __name__=='__main__':unittest.main()
