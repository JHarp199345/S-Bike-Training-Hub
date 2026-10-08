# paused feature: HUB_RECOVERY_LEARNING (recovery-curve learning is paused for research review; run with HUB_RECOVERY_LEARNING=1)
"""Running time-scale calibration: identifiable evidence, bounded learning, normal MCP/API persistence."""
import asyncio
import copy
import datetime as dt
import json
import math
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import coach, damage, mapserver, recovery_calibration as R, training_block as B

TODAY = '2026-10-06'


def fixture(base, clean_day=6):
    d=coach.load(base/'coach.json')
    dates=[(dt.date(2026,9,20)+dt.timedelta(days=i)).isoformat() for i in range(17)]
    doses=[200]+[0]*16
    for n in range(1,clean_day):d['checkins'][dates[n]]={'feet':6,'legs':5}
    for n in (clean_day,clean_day+1):d['checkins'][dates[n]]={'feet':2,'legs':2,'hops':10}
    days=[{'date':x,'sports':{'run':{'impact':doses[i]}}} for i,x in enumerate(dates)]
    def load(data):
        rem=damage.remodeling_response(dates,doses,block=100,recovery_curve=(data.get('running_recovery_calibration') or {}).get('profile'))
        return {'days':copy.deepcopy(days),'activities':[{'id':'run-1','sport':'run','date':dates[0],'impact':200,'minutes':40}],
                'systems':{'impact':{'tissue':{'remodeling':rem}}}}
    return d, load


def main():
 with tempfile.TemporaryDirectory() as temp:
    base=pathlib.Path(temp);(base/'rides').mkdir();(base/'profile.json').write_text(json.dumps({'weight_kg':75,'ftp':180}))
    d,load=fixture(base);state=load(d)
    result=R.review(d,state,base,TODAY);c=result['candidate']
    assert result['status']=='review_candidate' and c['direction']=='faster' and .8<=c['time_scale']<1
    assert c['reference_points_held_fixed']==100 and result['validation']['accuracy'] is None
    assert not (base/'coach.json').exists() and 'running_recovery_calibration' not in d
    unknown=copy.deepcopy(d);unknown['checkins']={};assert R.review(unknown,state,base,TODAY)['candidate'] is None
    good=copy.deepcopy(d);good['checkins']={k:{'feet':1,'legs':1} for k in d['checkins']};assert R.review(good,state,base,TODAY)['candidate'] is None
    one=copy.deepcopy(d);one['checkins'].pop('2026-09-27');assert R.review(one,state,base,TODAY)['candidate'] is None
    missing=copy.deepcopy(d)
    for x in missing['checkins'].values():x.pop('feet')
    assert R.review(missing,state,base,TODAY)['candidate'] is None
    slow,slowload=fixture(base,clean_day=15);assert R.review(slow,slowload(slow),base,TODAY)['candidate']['direction']=='slower'
    old=R.review(d,state,base,'2026-11-02');assert not old['episodes']
    change=copy.deepcopy(d);change['capacity_adjustments']=[{'date':'2026-09-23','target':'running_block'}]
    assert R.review(change,state,base,TODAY)['episodes'][0]['status']=='confounded'
    gym=copy.deepcopy(state);gym['activities'].append({'date':'2026-09-24','sport':'gym','impact':0,'muscle':5})
    assert R.review(d,gym,base,TODAY)['candidate'] is None
    interrupted=copy.deepcopy(state);interrupted['days'][4]['sports']['run']['impact']=100
    assert all(r['id']!='2026-09-20' or r['status']!='eligible' for r in R.episodes(d,interrupted,TODAY))
    poor=copy.deepcopy(d);poor['checkins'][TODAY]={'feet':6,'legs':2};assert R.review(poor,state,base,TODAY)['status']=='blocked'
    mature=copy.deepcopy(d);mature['running_recovery_calibration']={'learned_report_days':[(dt.date(2026,7,1)+dt.timedelta(days=i)).isoformat() for i in range(42)]}
    mc=R.review(mature,state,base,TODAY)['candidate'];assert abs(mc['time_scale']-1)<=.02001 and mc['max_step_fraction']==.02
    # Legacy outputs are unchanged until a fitted profile is applied. Active learning
    # replaces session-by-session report adjustments with the one pooled profile.
    a=damage.remodeling_response(['2026-09-20']+[f'2026-09-{i:02d}' for i in range(21,30)],[200]+[0]*9,block=100)
    b=damage.remodeling_response(['2026-09-20']+[f'2026-09-{i:02d}' for i in range(21,30)],[200]+[0]*9,block=100,recovery_curve={'time_scale':.8})
    assert math.isclose(b['plateau_days'],a['plateau_days']*.8) and math.isclose(b['descent_days'],a['descent_days']*.8) and b['tail_days']==96
    assert a['reference_points']==b['reference_points'] and [x['dose'] for x in a['history']]==[x['dose'] for x in b['history']]
    for bad in (float('nan'),False,.1,3):
        try:R.parameters({'time_scale':bad});raise AssertionError('invalid scale accepted')
        except ValueError:pass
    coach.save(d);original=copy.deepcopy(d)
    preview=R.preview(d,state,base,TODAY);token=preview['draft']['id']
    assert d==original
    stale=copy.deepcopy(d);stale['checkins'][TODAY]={'feet':1,'legs':1}
    try:R.apply(stale,state,base,TODAY,token,True);raise AssertionError('stale draft accepted')
    except ValueError:pass
    try:R.apply(d,state,base,TODAY,token,False);raise AssertionError('unapproved draft accepted')
    except ValueError:pass
    receipt=R.apply(d,state,base,TODAY,token,True)
    assert d['plans']==original['plans'] and d['checkins']==original['checkins']
    assert R.apply(d,load(d),base,TODAY,token,True)['already_applied']
    assert R.review(d,load(d),base,TODAY)['candidate'] is None
    assert len(d['running_recovery_calibration']['history'])==1
    # Fit cannot erase protected prerequisites, even where modeled load is low.
    protected=copy.deepcopy(d);protected['run_progression']={}
    import recovery
    assert not recovery.status(protected,load(protected)['systems']['impact']['tissue']['remodeling'],TODAY)['run_eligible']
    # Calendar's new run uses the same learned plateau and decline parameters.
    current=load(d);current['days']=current['days'][-1:]
    current['days'][0].update(engine={'load':0},impact={'load':0},muscle={'load':0})
    current['systems'].update(engine={'fitness':10,'fatigue':10,'form':0,'acwr':None,'last7':0,'prev7':0,'last':0,'needed':0},muscle={'fitness':1,'fatigue':1,'form':0,'acwr':None,'last7':0,'prev7':0,'last':0,'needed':0})
    current['systems']['impact'].update(fitness=1,fatigue=1)
    current['profile']={'weight_kg':75,'hr_rest':60,'hr_max':180,'ftp':180}
    d['plans']['2026-10-07']={'sessions':[{'sport':'run','minutes':20,'name':'Synthetic easy run','steps':[]}]}
    forecasts=B.projected_loads(d,dt.date.fromisoformat(TODAY),['2026-10-07','2026-10-08'],current,{},[])
    assert forecasts['2026-10-07']['metrics'] and forecasts['2026-10-08']['metrics']
    # A real stdio MCP client uses the normal API. Only scratch athlete files mutate.
    fresh,loader=fixture(base);coach.save(fresh)
    bridge=SimpleNamespace(csv_path=str(base/'rides/test.csv'),profile={'ftp':180},workouts=[])
    class Handler(BaseHTTPRequestHandler):
        def request(self):
            code,typ,body,_=asyncio.run(mapserver.coach_api(bridge,self.command.encode(),self.path,self.path.split('?')[0],self.rfile.read(int(self.headers.get('Content-Length',0)))))
            self.send_response(code);self.send_header('Content-Type',typ);self.end_headers();self.wfile.write(body)
        do_GET=request;do_POST=request
        def log_message(self,*args):pass
    with patch.object(coach,'today',return_value=TODAY),patch.object(mapserver,'load_state',side_effect=lambda _:loader(coach.load(base/'coach.json'))):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        proc=subprocess.Popen([sys.executable,str(pathlib.Path(R.__file__).parent/'mcp_server.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,env={**os.environ,'S29_HUB_URL':f'http://127.0.0.1:{server.server_port}'})
        def call(name,args):
            proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})+'\n');proc.stdin.flush();r=json.loads(proc.stdout.readline());assert not r['result'].get('isError'),r
            return json.loads(r['result']['content'][0]['text'])
        try:
            assert call('get_running_recovery_review',{})['candidate']
            draft=call('preview_running_recovery_curve',{})
            assert 'running_recovery_calibration' not in coach.load(base/'coach.json')
            saved=call('apply_running_recovery_curve',{'draft_id':draft['draft']['id'],'approved':True})
            assert saved['application']['after']['time_scale']<1
            assert call('apply_running_recovery_curve',{'draft_id':draft['draft']['id'],'approved':True})['application']['already_applied']
            assert call('get_running_recovery_review',{})['new_episodes']==0
        finally:proc.terminate();proc.wait();server.shutdown()
    print('PASS recovery fitting: faster/slower/unknown/confounded evidence, 42-day window, maturity bounds, no repeated learning, unchanged doses/gates, stale/approval/retry checks, actual MCP → normal API')

if __name__=='__main__':main()
