"""Multi-step planning scenarios through the real API, with synthetic athlete data."""
import asyncio, copy, json, pathlib, sys, tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach, mapserver, program_builder, program_drafts, mcp_server

TODAY='2026-10-02'
FIELDS={'start':TODAY,'horizon_days':42,'goal':'Synthetic cycling development','sport':'general','hours':4,
        'priorities':{'ride':'improve','swim':'maintain','gym':'maintain','run':'pause'},'assessment':'existing','starter_enabled':True,'starter_equipment':'basic'}

async def main():
 with tempfile.TemporaryDirectory() as tmp:
  base=pathlib.Path(tmp);(base/'rides').mkdir();(base/'activities').mkdir()
  d=coach.load(base/'coach.json');d['checkins']['2026-10-01']={'legs':3,'journal':'Synthetic history'}
  coach.set_sessions(d,'2026-10-03',[{'sport':'swim','minutes':25,'name':'Retained workout'}]);coach.save(d)
  bridge=SimpleNamespace(csv_path=str(base/'rides/demo.csv'),workouts=[],profile={'ftp':150})
  async def api(path='/api/coach/program-builder',body=None):
   p=path.split('?')[0]
   code,_,raw,_=await mapserver.coach_api(bridge,b'POST' if body is not None else b'GET',path,p,json.dumps(body or {}).encode())
   return code,json.loads(raw)
  async def preview(fields=None):
   code,out=await api(body={**(fields or FIELDS),'action':'preview'});assert code==200,out
   return out
  with patch.object(coach,'today',return_value=TODAY),patch.object(mapserver,'load_state',return_value={}):
   before=(base/'coach.json').read_bytes();review=await preview();assert (base/'coach.json').read_bytes()==before
   # Server applies the stored prescription, not a fresh build or edited client payload.
   with patch.object(program_builder,'propose',side_effect=AssertionError('Apply must not rebuild')):
    code,saved=await api(body={'action':'accept','draft_id':review['draft']['id'],'hours':99});assert code==200,saved
   assert saved['application']['proposal_hash']==review['draft']['proposal_hash']
   persisted=coach.load(base/'coach.json');assert persisted['checkins']==d['checkins']
   assert persisted['plans']['2026-10-03']==d['plans']['2026-10-03']
   selected=next(c for c in review['starter']['candidates'] if c['level']==review['starter']['selected'])
   for date,p in review['starter']['plans'].items():
    if date!='2026-10-03':assert persisted['plans'][date]==p
   before=(base/'coach.json').read_bytes();code,retry=await api(body={'action':'accept','draft_id':review['draft']['id']})
   assert code==200 and retry['application']['already_applied'];assert (base/'coach.json').read_bytes()==before
   code,readback=await api();assert readback['last_application']['proposal_hash']==review['draft']['proposal_hash']
   # Intervening check-in, calendar edit, activity import and profile/library changes reject the draft.
   for kind in ('checkin','calendar','activity','profile','workouts'):
    proposal=await preview()
    if kind in ('checkin','calendar'):
     state=coach.load(base/'coach.json')
     if kind=='checkin':state['checkins'][TODAY]={'legs':8}
     else:coach.set_sessions(state,'2026-10-04',[{'sport':'ride','minutes':12,'name':'Edited'}])
     coach.save(state)
    elif kind=='activity':(base/'activities/new.fit').write_bytes(b'synthetic input fingerprint')
    elif kind=='profile':bridge.profile['ftp']=160
    else:bridge.workouts.append({'id':'new','name':'New workout'})
    before=(base/'coach.json').read_bytes();code,rejected=await api(body={'action':'accept','draft_id':proposal['draft']['id']})
    assert code==409 and rejected['code']=='draft_conflict',(kind,rejected)
    assert (base/'coach.json').read_bytes()==before
   proposal=await preview()
   with patch.object(program_drafts.time,'time',return_value=__import__('time').time()+program_drafts.TTL_SECONDS+1):
    code,rejected=await api(body={'action':'accept','draft_id':proposal['draft']['id']});assert code==409 and 'expired' in rejected['error']
   code,_=await api(body={'action':'accept',**FIELDS});assert code==400
   # Missing anchors do not become invented weights.
   missing=await preview({**FIELDS,'start':'2026-11-14','starter_equipment':'barbell'})
   code,result=await api(body={'action':'accept','draft_id':missing['draft']['id']});assert code==400 and 'recent set' in result['error']
   # Near event is taper-only; current running hold remains in force.
   late=await preview({**FIELDS,'sport':'run','target':'2026-10-05'})
   assert all(p['stage']=='taper' for p in late['phases']) and late['running_hold']
   assert not any(s['sport']=='run' for w in late['weeks'] for s in w['slots'])
   # Read a saved week and investigate score meaning without changing athlete records.
   before=(base/'coach.json').read_bytes()
   code,cal=await api('/api/coach/calendar?date=2026-10-02&days=7');assert code==200 and len(cal['calendar'])==7
   assert cal['calendar'][1]['sessions'][0]['prescription']['name']=='Retained workout'
   assert cal['running_gate']['status']!='open_for_review'
   code,evidence=await api('/api/coach/reading-evidence?date=2026-10-02&metric=cardio_conditioning')
   assert code==200 and '42' in evidence['formula'] and evidence['unknown']
   assert 'not a direct measurement' in evidence['definition'] and len(evidence['source']['sha256'])==64
   assert (base/'coach.json').read_bytes()==before
   code,_=await api('/api/coach/calendar?date=2026-10-02&days=15');assert code==400
   code,_=await api('/api/coach/reading-evidence?metric=made_up');assert code==400
   # Multi-step reported-cost interpretation: recovery, taper, build, localized and delayed symptoms.
   import progression
   state=coach.load(base/'coach.json')
   event={'effort':'too_easy','context':{'phase':'recovery','purpose':'recovery','why':'Recovery week'}}
   assert progression.feedback(state,event)['decision']=='purpose_met'
   event['context']['phase']='taper';assert progression.feedback(state,event)['decision']=='purpose_met'
   event['context']={'phase':'build','purpose':'aerobic','why':'Development'}
   assert progression.feedback(state,event)['decision']=='progression_candidate'
   event['symptoms']=[{'location':'shoulder','side':'left','severity':2,'regions':['shoulders']}]
   assert progression.feedback(state,event)['decision']=='regression_candidate'
   state['training_feedback']={'2026-10-01:0':{**event,'date':'2026-10-01'}};coach.save(state)
   code,cal=await api('/api/coach/calendar?days=1');assert code==200 and cal['active_symptoms'][0]['location']=='shoulder'
   event['symptoms']=[];event['heart_rate_issue']=True;assert progression.feedback(state,event)['decision']=='regression_candidate'
   # Capacity demand scenarios do not alter athlete state or grant clearance.
   before=(base/'coach.json').read_bytes()
   code,cap=await api('/api/coach/capacity-review',{'demands':[{'sport':'run','distance_m':5000,'duration_min':25}]})
   assert code==200 and cap['mode']=='capacity' and cap['demands'][0]['confidence']=='provisional',(code,cap)
   assert len(cap['tolerance_trends'])==4 and (base/'coach.json').read_bytes()==before
   code,cap=await api('/api/coach/capacity-review',{'demands':[{'sport':'run','duration_min':-1}]})
   assert code==400 and (base/'coach.json').read_bytes()==before
   code,cap=await api('/api/coach/capacity-followup',{'date':TODAY,'session_index':0,'recovery':'good'})
   assert code==400 and (base/'coach.json').read_bytes()==before
   # Tool contracts advertise the new workflow and conservative storage side effects.
   tools={t['name']:t for t in mcp_server.handle({'id':1,'method':'tools/list'})['tools']}
   assert tools['apply_program']['inputSchema']['required']==['draft_id']
   assert not tools['preview_program']['annotations']['readOnlyHint']
   assert tools['get_training_calendar']['annotations']['readOnlyHint']
 print('PASS exact draft, state conflicts, retry, expiry, history, weights, taper/run hold, calendar/evidence, contextual reports')
if __name__=='__main__':asyncio.run(main())
