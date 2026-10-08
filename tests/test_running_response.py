"""Selected response integration and normal API persistence, using scratch data."""
import asyncio,copy,datetime as dt,json,pathlib,sys,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,loads,mapserver,running_response,training_block,recovery

def fixture():
    start=dt.date(2026,1,1);today='2026-02-06';days=[]
    for i in range(37):
        day=(start+dt.timedelta(days=i)).isoformat();dose=100 if i in (0,1,2,15,35) else 0
        days.append({'date':day,'sports':{'run':{'impact':dose,'minutes':30,'muscle':10,'engine':0}} if dose else {},
            **{k:{'load':dose if k=='impact' else 0,'fatigue':0,'fitness':0,'ratio':0} for k in loads.SYSTEMS}})
    c={date:{'legs':n,'feet':n,'hops':10} for date,n in [('2026-01-20',6),('2026-01-21',5),('2026-01-22',4),('2026-01-23',3),('2026-01-24',2),('2026-01-25',2),('2026-02-05',2)]}
    d={'checkins':c,'plans':{},'weekly':{}}
    systems={k:{'form':0,'tuned':False,'acwr':None,'last7':0,'prev7':0,'usual_week':100,'fitness':0,'fatigue':0} for k in loads.SYSTEMS}
    systems['impact']['tissue']={'remodeling':{'score':100,'threshold_blocks':1.5,'reference_points':100,'walking':[],'history':[]},'event':{'score':10}}
    load={'days':days,'activities':[],'systems':systems,'headline':{'mechanical':{'ratio':66,'remodeling_blocks':100,'block_limit':1.5}},'lifting':{'regions':{}},'sports_last7':{},'history_days':37,'swim_recovery':{'score':0,'threshold_blocks':1.5},'profile':{'ftp':180}}
    return d,load,today

class ResponseTests(unittest.TestCase):
    def test_rates_and_mix_use_closed_complete_windows(self):
        d,L,t=fixture();windows=running_response.workload_context(L,t)['windows']
        three=windows[1];self.assertEqual(three['end'],'2026-02-05')
        self.assertEqual(three['domains']['impact']['points_per_day'],33.333)
        self.assertEqual(three['domains']['impact']['sport_share_percent'],{'run':100})
        L['days'][-2]['sports']['run']['engine']=None
        three=running_response.workload_context(L,t)['windows'][1]
        self.assertFalse(three['complete'])
        self.assertIsNone(three['domains']['engine']['points_per_day'])
        self.assertEqual(three['domains']['impact']['points_per_day'],33.333)
        L['days']=[r for r in L['days'] if r['date']!='2026-02-04']
        self.assertIsNone(running_response.workload_context(L,t)['windows'][1]['domains']['impact']['points_per_day'])
    def test_calibration_read_cannot_refit_retired_blocks(self):
        import calibration
        d,L,t=fixture();L['running_response']=running_response.review(d,L,'.',t)['preview']
        L['calibration_estimates']={'block':{'value':1.5},'ftp':{'value':180}}
        L['activities']=[{'date':'2026-02-05','sport':'run'}]
        d['plans']={'2026-02-05':{'test':'benchmark_run'},'2026-01-20':{'test':'run_calibration'}}
        before=copy.deepcopy(d)
        with patch.object(mapserver,'load_state',return_value=L), \
             patch.object(calibration,'block_test',side_effect=AssertionError('retired block grading')), \
             patch.object(calibration,'match_runs',side_effect=AssertionError('retired calibration matching')), \
             patch.object(calibration,'run_calibration',side_effect=AssertionError('retired block refit')), \
             patch.object(calibration,'benchmark_expectation',side_effect=AssertionError('retired block expectation')), \
             patch.object(calibration,'due',return_value=[]) as due, \
             patch.object(calibration,'calibration_runs',return_value=[]), \
             patch.object(calibration,'next_test_week',return_value=None), \
             patch.object(coach,'save',side_effect=AssertionError('read mutated data')):
            result=mapserver.calibration_view(d,pathlib.Path('/tmp/response-test/activities'))
        self.assertNotIn('error',result)
        self.assertEqual(result['capacities'],{'ftp':{'value':180}})
        self.assertIsNone(result['benchmark'])
        due.assert_called_once_with({'ftp':{'value':180}},running_cleared=False)
        self.assertEqual(d,before)
    def test_report_order_and_decay(self):
        d,L,today=fixture();r=running_response.review(d,L,'.',today)
        self.assertEqual(r['candidate']['report_days_used'],6) # excludes immediate same-day run report
        x=r['preview'];self.assertEqual(x['legs']['rating'],2);self.assertEqual(x['feet']['rating'],2)
        self.assertGreater(x['estimate']['high'],x['estimate']['low'])
        self.assertIsNone(x['personal_band']);self.assertIsNone(x['clearance_date'])
        self.assertTrue(all(a['estimate_high']>=b['estimate_high'] for a,b in zip(x['projection'],x['projection'][1:])))
    def test_old_curve_cannot_hold_active_model(self):
        d,L,t=fixture();L['running_response']=running_response.review(d,L,'.',t)['preview']
        gate=training_block.running_gate(d,L,{'feet':2,'legs':2})
        self.assertEqual(gate['status'],'open_for_review');self.assertIsNone(gate['blocks']);self.assertIsNone(gate['model_days'])
        self.assertEqual(training_block.running_gate(d,L,{'feet':9})['status'],'hold')
        self.assertEqual(training_block.running_gate(d,L,{'legs':9})['status'],'hold')
        self.assertEqual(loads.readiness(L,{'feet':9})['running']['verdict'],'rest')
    def test_protected_checks_and_personal_wait_survive(self):
        d,L,t=fixture();d['run_progression']={'minimum_run_days':3}
        L['running_response']=running_response.review(d,L,'.',t)['preview']
        x=recovery.status(d,running_response.progression_input(L),t)
        self.assertFalse(x['run_eligible']);self.assertTrue(any('Personal minimum' in r for r in x['run_reasons']))
        self.assertFalse(any('Mechanical running load' in r for r in x['run_reasons']))
        self.assertEqual(training_block.running_gate(d,L,{'feet':2,'legs':2})['status'],'hold')
    def test_actual_api_preview_apply_stale_and_idempotent(self):
        d,L,t=fixture();base=pathlib.Path(tempfile.mkdtemp());(base/'rides').mkdir();d['_path']=str(base/'coach.json');coach.save(d)
        bridge=SimpleNamespace(csv_path=str(base/'rides'/'ride_test.csv'),workouts=[],profile={'ftp':180})
        def load_state(_):
            data=coach.load(base/'coach.json');out=copy.deepcopy(L);out['running_response']=running_response.state(data,out,t);return out
        async def call(fields=None):
            code,_,body,_=await mapserver.coach_api(bridge,b'GET' if fields is None else b'POST','/api/coach/running-response','/api/coach/running-response',json.dumps(fields or {}).encode())
            return code,json.loads(body)
        with patch.object(coach,'today',return_value=t),patch.object(mapserver,'load_state',side_effect=load_state):
            code,p=asyncio.run(call({'action':'preview'}));self.assertEqual(code,200);token=p['draft']['id']
            code,_=asyncio.run(call({'action':'apply','draft_id':token,'approved':False}));self.assertEqual(code,400)
            code,a=asyncio.run(call({'action':'apply','draft_id':token,'approved':True}));self.assertEqual(code,200);self.assertTrue(a['response']['active'])
            code,a=asyncio.run(call({'action':'apply','draft_id':token,'approved':True}));self.assertEqual(code,200);self.assertTrue(a['application']['already_applied'])
            saved=coach.load(base/'coach.json');self.assertEqual(saved['checkins'],d['checkins']);self.assertEqual(saved['plans'],d['plans'])
            profile=copy.deepcopy(saved['running_response_model'])
            current=load_state(base)['running_response']
            fields={'action':'feedback','context_token':current['context_token'],'direction':'too_high'}
            code,reply=asyncio.run(call(fields));self.assertEqual(code,200);self.assertTrue(reply['saved'])
            code,reply=asyncio.run(call(fields));self.assertEqual(code,200)
            saved=coach.load(base/'coach.json')
            self.assertEqual(len(saved['running_response_feedback']),1)
            self.assertEqual(saved['running_response_model'],profile)
            self.assertEqual(saved['checkins'],d['checkins']);self.assertEqual(saved['plans'],d['plans'])
            code,_=asyncio.run(call({**fields,'context_token':'stale'}));self.assertEqual(code,400)
            code,p=asyncio.run(call({'action':'preview'}));self.assertEqual(code,200)
            saved['checkins'][t]={'feet':8};coach.save(saved)
            code,_=asyncio.run(call({'action':'apply','draft_id':p['draft']['id'],'approved':True}));self.assertEqual(code,409)
            code,_=asyncio.run(call({'action':'preview','tau':1}));self.assertEqual(code,400)
    def test_forecast_uses_distinct_response_units(self):
        d,L,t=fixture();L['running_response']=running_response.review(d,L,'.',t)['preview']
        dates=[t,(dt.date.fromisoformat(t)+dt.timedelta(days=1)).isoformat()]
        out=training_block.projected_loads(d,t,dates,L)
        daily=out.values() if isinstance(out,dict) else out
        for row in daily:
            metrics=row['metrics_by_key'];self.assertIn('run_response',metrics);self.assertNotIn('run_mechanical',metrics);self.assertIsNone(metrics['run_response']['limit'])
        history=training_block.recorded_load_history(L,t)
        self.assertTrue(any(m['key']=='run_response' for r in history for m in r['metrics']))
        self.assertFalse(any(m['key']=='run_mechanical' for r in history for m in r['metrics']))
        import planning_evidence
        reading=planning_evidence.explain(d,L,{},[],t,t,'run_response')
        self.assertEqual(reading['source']['file'],'running_response.py')
        self.assertNotIn('run_tail_days',reading['constants'])

if __name__=='__main__':unittest.main()
