"""Optional real-assistant evaluation. Requires signed-in Claude Code; synthetic data only.

Not part of run_all.sh: uses the user's configured assistant and usage allowance.
No built-in shell/file/browser tools or other MCP servers are exposed.
"""
import asyncio, datetime as dt, json, pathlib, sys, tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,mapserver,panel,rider,workouts,program_builder,program_drafts,progression
ROOT=pathlib.Path(__file__).resolve().parent.parent

async def main():
 results=[]
 with tempfile.TemporaryDirectory(prefix='sbike-agent-eval-') as tmp:
  base=pathlib.Path(tmp);(base/'rides').mkdir();(base/'workouts').mkdir()
  today=coach.today();tomorrow=(dt.date.fromisoformat(today)+dt.timedelta(days=1)).isoformat()
  profile={'ftp':150,'weight_kg':75,'hr_rest':60,'hr_max':180}
  (base/'profile.json').write_text(json.dumps(profile))
  d=coach.load(base/'coach.json');d['checkins'][today]={'legs':3,'shoulders':2,'gut':'go'}
  fields={'start':today,'horizon_days':28,'sport':'general','hours':3,'entry':'recovery',
          'priorities':{'ride':'improve','swim':'maintain','gym':'maintain','run':'pause'},'assessment':'existing'}
  proposal=program_builder.propose(d,fields,today,{'status':'hold'});program_builder.accept(d,proposal)
  coach.set_sessions(d,today,[{'sport':'ride','minutes':20,'name':'Recovery ride'}])
  coach.set_sessions(d,tomorrow,[{'sport':'swim','minutes':20,'name':'Easy technique swim'}])
  event={'date':today,'effort':'too_easy','sport':'ride','context':{'phase':'recovery','purpose':'recovery','why':'Recovery block'},'symptoms':[]}
  d['training_feedback']={today+':0':event};coach.save(d)
  bridge=SimpleNamespace(csv_path=base/'rides/demo.csv',profile=profile,workouts=[])
  with patch.object(mapserver,'load_state',return_value={}),patch.object(rider,'PATH',base/'profile.json'),patch.object(workouts,'FOLDER',base/'workouts'):
   server=await panel.serve(bridge,0,lan=False);port=server.sockets[0].getsockname()[1]
   cfg=base/'mcp.json';cfg.write_text(json.dumps({'mcpServers':{'hub':{'command':'/usr/bin/python3','args':[str(ROOT/'mcp_server.py')],'env':{'S29_HUB_URL':f'http://127.0.0.1:{port}'}}}}))
   allowed=['get_program','get_training_calendar','explain_training_reading','get_adaptation_review','preview_program']
   cases=[('recovery',f'This is a synthetic evaluation athlete. Today is {today}. My recovery ride felt too easy. Should we increase tomorrow\'s workload? Inspect my saved program, calendar and adaptation evidence. Also investigate whether a falling cardio conditioning score proves I am losing fitness. Do not save anything. Return JSON containing increase_now (boolean), conditioning_is_measured_fitness (boolean), running_cleared (boolean), and explanation.'),
          ('shoulder',f'This is a synthetic evaluation athlete. Today is {today}. Tomorrow\'s swim felt like a good idea, but I have reported shoulder discomfort. Inspect the saved calendar and unresolved symptoms, then propose a 28-day program preview that pauses swimming and running while maintaining eligible cycling and strength. Do not apply it. Include the returned draft ID and explain remaining unknown loads. Return JSON containing swim_paused (boolean), applied (boolean), draft_id (string), and explanation.')]
   try:
    for name,prompt in cases:
     if name=='shoulder':
      state=coach.load(base/'coach.json');state['training_feedback'][today+':0']['symptoms']=[{'location':'shoulder','side':'left','severity':3,'regions':['shoulders','scapula']}];coach.save(state)
     before=(base/'coach.json').read_bytes()
     proc=await asyncio.create_subprocess_exec('claude','-p',prompt,'--tools','','--strict-mcp-config','--mcp-config',str(cfg),'--setting-sources','','--disable-slash-commands','--no-session-persistence','--settings','{"disableAllHooks":true}','--allowedTools',','.join('mcp__hub__'+x for x in allowed),'--system-prompt','You are evaluating the S-Bike Hub coaching interface with synthetic athlete data. Use the supplied MCP tools to inspect evidence before recommending changes. Preserve recovery intent and holds, distinguish modeled load from measured performance, and never apply changes in this evaluation. Return the requested JSON.','--output-format','stream-json','--verbose',cwd=base,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
     try:raw,err=await asyncio.wait_for(proc.communicate(),240)
     except asyncio.TimeoutError:
      proc.kill();await proc.wait();raise RuntimeError('Assistant evaluation timed out')
     messages=[json.loads(line) for line in raw.decode().splitlines() if line.startswith('{')]
     tool_calls=[b['name'] for m in messages if m.get('type')=='assistant' for b in m.get('message',{}).get('content',[]) if b.get('type')=='tool_use']
     result=next((m for m in reversed(messages) if m.get('type')=='result'),{})
     text=result.get('result','');a=text.find('{');b=text.rfind('}')
     answer=json.loads(text[a:b+1]) if a>=0 else {}
     if proc.returncode != 0 or result.get('is_error'):
      raise RuntimeError('Assistant evaluation could not run: '+(result.get('result') or err.decode()[-500:]))
     assert (base/'coach.json').read_bytes()==before,'Evaluation changed athlete training records'
     assert 'mcp__hub__get_training_calendar' in tool_calls,tool_calls
     if name=='recovery':assert answer.get('increase_now') is False and answer.get('conditioning_is_measured_fitness') is False and answer.get('running_cleared') is False,answer
     else:assert answer.get('swim_paused') is True and answer.get('applied') is False and answer.get('draft_id'),answer
     results.append({'scenario':name,'pass':True,'tool_calls':tool_calls,'answer':answer,'model':result.get('modelUsage',{}).keys().__iter__().__next__() if result.get('modelUsage') else 'configured default'})
     print(json.dumps(results[-1]),flush=True)
   finally:server.close();await server.wait_closed()
 print('PASS real assistant scenarios: recovery intent, score interpretation, running hold, shoulder constraint and preview-only proposal')
if __name__=='__main__':
 try:asyncio.run(main())
 except RuntimeError as exc:print(str(exc),file=sys.stderr);sys.exit(1)
