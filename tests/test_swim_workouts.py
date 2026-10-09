"""Reviewed swim parsing and save protection in scratch storage."""
import sys, pathlib, tempfile, copy, json, asyncio
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import swim_workouts as sw, workout_imports as wi, coach, mapserver, mcp_server
TEXT='''● WARM-UP 400 yds
200 Free / 200 Back easy
Alternate strokes, loosen up
● PRE-SET / DRILL 300 yds
6×50 Kick w/ board @ 1:10
Tight, compact kick from the hips
● MAIN SET A 800 yds
8×100 Choice @ 2:15
Moderate effort, hold consistent pace
● MAIN SET B 400 yds
4×100 choice moderate @ 2:00
Moderate effort — build aerobic base
● COOL-DOWN 200 yds
200 easy choice swim
Very easy — bring heart rate down
TOTAL: 2,100 yds'''
fields=sw.split_sections(TEXT);p=sw.parse(fields)
assert p['valid'] and p['total_distance']==2100 and len(p['sets'])==6 and p['sendoff_minutes']==33,p
assert [s['section'] for s in p['sets']]==['warmup','warmup','main','main','main','cooldown']
assert p['sets'][2]['work']=='kick' and p['sets'][2]['equipment']==['board']
assert p['sets'][3]['stroke']=='choice' and p['sets'][3]['sendoff_seconds']==135
assert not p['all_sendoffs'] and not sw.snapshot(p).get('stroke_mix')
assert sw.parse({'main':'4 x 50 free rest 20 seconds'},distance_unit='m')['sets'][0]['rest_seconds']==20
assert not sw.parse({'main':'4 x 50 free @ 1:00 rest 20 seconds'})['valid']
assert not sw.parse({'main':'4 x 50 free @ 1:7'})['valid']
assert not sw.parse({'main':'4 x 50 free @ 1:00 /100'})['valid']
assert not sw.parse({'main':'4 x 50 free\nTOTAL: 300 yd'})['valid']
assert not sw.parse({'main':'Main set A 250 yds\n4 x 50 free'})['valid']
assert sw.parse({'main':'4 x 50 free'},2)['total_distance']==400
assert sw.parse({'main':'100 m free'},distance_unit='yd')['total_distance_m']==100
assert sw.parse({'main':'50 free'},pool_length=33)['warnings']
for kwargs in [{'repeats':True},{'repeats':11},{'pool_length':float('nan')},{'fields':{'main':'x'*6001}}]:
 try:sw.parse(**({'fields':{'main':'50 free'}}|kwargs))
 except ValueError:pass
 else:raise AssertionError(kwargs)
recipe={'fields':fields,'repeats':1,'unit':'yd','pool_length':25}
req={'sport':'swim','name':'Reviewed swim','minutes':50,'swim_recipe':recipe}
async def main():
 with tempfile.TemporaryDirectory() as tmp:
  base=pathlib.Path(tmp);(base/'rides').mkdir();d=coach.load(base/'coach.json')
  coach.set_sessions(d,'2026-10-04',[{'sport':'ride','minutes':20,'name':'Past prescription'}]);coach.save(d);d=coach.load(base/'coach.json');before=copy.deepcopy(d)  # include the saved prescription audit
  candidate=sw.add(d,'2026-10-05',req);assert d==before
  assert candidate['plans']['2026-10-04']==before['plans']['2026-10-04']
  candidate=sw.add(candidate,'2026-10-05',dict(req,index=0,name='Edited swim'));assert len(candidate['plans']['2026-10-05']['sessions'])==1
  bridge=SimpleNamespace(csv_path=str(base/'rides'/'example.csv'),profile={'ftp':180})
  async def api(path,data=None):
   method=b'POST' if data is not None else b'GET'
   return await mapserver.coach_api(bridge,method,path,path,json.dumps(data).encode() if data is not None else b'')
  with patch.object(mapserver,'capture_program_forecast'),patch.object(mapserver,'done_by_day',return_value={}):
   code,_,body,_=await api('/api/coach/swim/preview',{'text':TEXT,'minutes':30});assert code==200 and not json.loads(body)['valid']
   code,_,body,_=await api('/api/coach/swim/preview',{'text':TEXT,'repeats':True});assert code==400,body
   import base64
   code,_,body,_=await api('/api/coach/workout-import',{'name':'swim.txt','data':base64.b64encode(TEXT.encode()).decode()});assert code==200,body
   doc=json.loads(body);ident=doc['id'];assert doc['status']=='unreviewed draft'
   assert coach.load(base/'coach.json')==before
   code,mime,body,_=await api('/api/coach/workout-import/'+ident+'/source');assert code==200 and body.decode()==TEXT and mime.startswith('text/plain')
   save=dict(req,date='2026-10-05',workout_import_id=ident)
   code,_,body,_=await api('/api/coach/session/add',save);assert code==400,body
   assert coach.load(base/'coach.json')==before
   code,_,body,_=await api('/api/coach/session/add',dict(save,source_reviewed=True));assert code==200,body
   saved=coach.load(base/'coach.json');session=saved['plans']['2026-10-05']['sessions'][0]
   assert session['swim_recipe']['total_distance']==2100 and session['workout_import_id']==ident
   assert saved['plans']['2026-10-04']==before['plans']['2026-10-04']
   code,_,body,_=await api('/api/coach/session/add',dict(save,source_reviewed=True,index=0,name='Edited once'));assert code==200,body
   assert len(coach.load(base/'coach.json')['plans']['2026-10-05']['sessions'])==1
   bad_before=(base/'coach.json').read_bytes()
   for bad in [dict(save,source_reviewed=True,minutes=30),dict(save,source_reviewed=True,sport='ride')]:
    code,_,body,_=await api('/api/coach/session/add',bad);assert code==400,body;assert (base/'coach.json').read_bytes()==bad_before
  with patch.object(mapserver,'done_by_day',return_value={'2026-10-05':[{'sport':'swim','minutes':50,'activity_id':'completed-test-swim'}]}):
   code,_,body,_=await api('/api/coach/session/add',dict(save,index=0,source_reviewed=True));assert code==400,body
  for ident in ['../coach.json','bad',True]:
   try:wi.get(base,ident)
   except ValueError:pass
   else:raise AssertionError('Invalid source ID accepted')
  def fake_call(path,body=None):return {'id':'a'*32,'pages':[{'page':1}],'image':'aW1hZ2U='} if '?visual' in path else {'id':'a'*32,'pages':[{'page':1}]}
  with patch.object(mcp_server,'call',side_effect=fake_call):
   response=mcp_server.t_workout_import({'import_id':'a'*32})
   assert [c['type'] for c in response.content]==['text','image']
   assert 'image' not in json.loads(response.content[0]['text'])
 print('PASS swim sections, send-offs, units, ambiguity, review gate, scratch save/edit, completed protection and MCP visual source')
if __name__=='__main__':asyncio.run(main())
