"""Public version checks are offline-safe and never submit athlete data."""
import io,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import updates
with tempfile.TemporaryDirectory() as t:
 p=Path(t);local={'latest':'current','entries':[{'id':'current','date':'2026-10-03'}]};(p/'updates.json').write_text(json.dumps(local))
 for remote,want in [(local,False),({'latest':'next','entries':[{'id':'next','date':'2026-10-04','changes':['Fixed a control']},local['entries'][0]]},True),({'latest':'old','entries':[{'id':'old','date':'2026-10-02'}]},False)]:
  with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(remote).encode())) as fetch:
   result=updates.check(p);assert result['available']==want
   request=fetch.call_args.args[0];assert request.full_url==updates.URL and request.data is None
   assert (p/'updates.json').read_text()==json.dumps(local)
 with patch('urllib.request.urlopen',return_value=io.BytesIO(b'x'*131073)):
  try:updates.check(p);raise AssertionError('Oversized update accepted')
  except ValueError:pass
print('PASS public metadata checks: newer/current/older, no uploads, no installs and bounded download')
