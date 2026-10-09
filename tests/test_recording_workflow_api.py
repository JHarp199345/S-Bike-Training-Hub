"""Scratch HTTP + MCP test: imports, explicit linking, report parity and daily Hooper separation."""
import asyncio, datetime as dt, json, os, pathlib, subprocess, sys, tempfile, threading, types, urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/demo')]
import panel,coach,fitwrite
base=pathlib.Path(tempfile.mkdtemp());(base/'rides').mkdir();(base/'activities').mkdir()
date=coach.today();t=dt.datetime.fromisoformat(date+'T06:00').timestamp()
class Fake:
 profile={'ftp':180,'ftp_source':'test'};csv_path=base/'rides/ride_test.csv';workouts=[];args=types.SimpleNamespace(no_bike=True)
 def event(self,m):pass
loop=asyncio.new_event_loop();server=loop.run_until_complete(panel.serve(Fake(),18798,lan=False));server_thread=threading.Thread(target=loop.run_forever,daemon=True);server_thread.start()
url='http://127.0.0.1:18798'
def api(path,data=None):
 req=urllib.request.Request(url+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as r:return json.loads(r.read())
(base/'rides/ride_test.csv').write_text('time,power_w,cadence_rpm\n'+''.join(f'{dt.datetime.fromtimestamp(t+i).isoformat()},180,80\n' for i in range(600)))
d=coach.load(base/'coach.json');d['plans']={date:{'sessions':[{'sport':'ride','name':'Saved prescription','minutes':40,'target':100}]}};coach.save(d)
for n,(sport,code) in enumerate([('bike',2),('swim',5),('gym',10),('run',1),('walk',11),('other',13)]):
 w=fitwrite.Writer();start=t+n*3600
 for i in range(600):w.add('record',timestamp=start+i,heart_rate=140,cadence=70,power=20 if sport=='bike' else None,distance=i if sport!='gym' else 0)
 w.add('session',sport=code,start_time=start,timestamp=start+600,total_timer_time=600,total_distance=0 if sport=='gym' else 600,avg_heart_rate=140,max_heart_rate=150)
 req=urllib.request.Request(url+'/api/activities/upload?name='+sport+'.fit',data=w.bytes(),method='POST')
 with urllib.request.urlopen(req,timeout=30) as r:assert json.loads(r.read())['imported']==[sport+'.fit']
# Preview doesn't persist; save combines power/HR while retaining the scheduled targets.
req={'activity_id':'bike','mode':'scheduled','session_index':0,'target_activity_id':'ride_test','save':False}
before=(base/'coach.json').read_bytes();preview=api('/api/coach/recording-link',req);assert preview['measurements']['avg_power']==180 and preview['measurements']['avg_heart_rate']==140 and (base/'coach.json').read_bytes()==before
api('/api/coach/recording-link',{**req,'save':True})
for sport in ('swim','gym','run','walk','other'):api('/api/coach/recording-link',{'activity_id':sport,'mode':'new','save':True})
week=api('/api/coach/week?date='+date)['week'];day=next(x for x in week if x['date']==date)
assert len(day['done'])==6 and len({x['activity_id'] for x in day['done']})==6
assert day['sessions'][0]['completion']['activity_id']=='ride_test'
assert coach.load(base/'coach.json')['plans'][date]['sessions'][0]['minutes']==40
for ident in ('ride_test','swim','gym','run','walk','other'):
 report=api('/api/coach/activity-report?activity_id='+ident);assert report['feedback_supported'] and report['activity_id']==ident
 saved=api('/api/coach/session-report',{'date':date,'activity_id':ident,'effort':'as_intended','rpe':6,'note':'Scratch parity check'})
 assert saved['activity_id']==ident and api('/api/coach/activity-report?activity_id='+ident)['feedback']['rpe']==6
assert coach.load(base/'coach.json')['checkins']=={} # workout reports aren't daily Hooper reports
api('/api/coach/checkin',{'date':date,'gut':'easy','hooper_fatigue':2,'hooper_sleep':3,'hooper_stress':2,'hooper_soreness':3})
d=coach.load(base/'coach.json');assert len(d['training_feedback'])==6 and len(d['checkins'])==1 and d['checkins'][date]['hooper_index']==10
# The stdio client reads the same options and preview; no separate AI implementation.
msgs=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}}]
for i,name,args in [(2,'get_recording_link_choices',{'activity_id':'swim'}),(3,'link_workout_recording',{'activity_id':'swim','mode':'new','save':False}),(4,'get_activity_report',{'activity_id':'swim'})]:msgs.append({'jsonrpc':'2.0','id':i,'method':'tools/call','params':{'name':name,'arguments':args}})
r=subprocess.run([sys.executable,str(ROOT/'mcp_server.py')],input='\n'.join(map(json.dumps,msgs))+'\n',capture_output=True,text=True,env={**os.environ,'S29_HUB_URL':url},timeout=60)
answers=[json.loads(l) for l in r.stdout.splitlines()];assert len(answers)==4 and not any(x['result'].get('isError') for x in answers[1:]),answers
assert json.loads(answers[3]['result']['content'][0]['text'])['feedback']['rpe']==6
history=api('/api/coach/swim-history');assert len(history['rows'])==1 and history['rows'][0]['activity_id']=='swim' and history['as_of']==date
# Close on the owning loop: cross-thread close can race asyncio's waiters.
async def close_server():
 server.close()
 await server.wait_closed()
asyncio.run_coroutine_threadsafe(close_server(),loop).result(timeout=10)
loop.call_soon_threadsafe(loop.stop)
server_thread.join(timeout=10)
assert not server_thread.is_alive()
loop.close()
print('PASS HTTP upload/link/report parity for six sports, canonical counts, immutable prescription, independent daily Hooper and shared MCP operations')
