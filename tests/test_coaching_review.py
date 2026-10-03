"""Forecast sequence and reviewed capacity scenarios using synthetic records only."""
import asyncio,copy,datetime as dt,json,pathlib,sys,tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import coach,coaching_review as C,lifting,mapserver,program_drafts,training_block as B,mcp_server
TODAY='2026-10-14'


def forecasts(d, dates, metric, expected):
    for date in dates:
        d.setdefault('load_forecasts',{})[date]=[{'saved_at':date+'T07:00:00','forecast':{'metrics':[{'key':metric,'after':expected}]}}]


def run_fixture(base):
    d=coach.load(base/'coach.json');dates=['2026-10-01','2026-10-05','2026-10-09']
    for date in dates:
        for n in (1,2):d['checkins'][(dt.date.fromisoformat(date)+dt.timedelta(days=n)).isoformat()]={'feet':2,'legs':2}
        d.setdefault('training_feedback',{})[date+':0']={'date':date,'sport':'run','effort':'too_easy','context':{'phase':'build'},'symptoms':[]}
    forecasts(d,dates,'run_mechanical',2.6)
    load={'activities':[{'sport':'run','date':x} for x in dates], 'systems':{'impact':{'tissue':{'remodeling':{'phase':'decline','reference_points':100,'score':1.3,'projection':[]}}}},'days':[{'date':(dt.date(2026,10,1)+dt.timedelta(days=i)).isoformat(),'sports':{'run':{'impact':30 if i in (0,4,8) else 0}}} for i in range(14)]}
    return d,load


def lift_fixture(base):
    d=coach.load(base/'coach.json');dates=['2026-10-01','2026-10-05','2026-10-09']
    exercise={'name':'Hip thrust machine A','kind':'machine','weight':110,'unit':'lb','sets':1,'reps':5,'tempo':'3-3-3','regions':{'glutes':100}}
    for date in dates:
        lifting.set_session(d,date,[exercise]);lifting.log(d,date,[{}],4,8)
        lifting.followup(d,date,{'glutes':1},today=dt.date.fromisoformat(date)+dt.timedelta(days=3))
    forecasts(d,dates,'lift_glutes',2.0)
    return d,{'lifting':lifting.model(d,dt.date.fromisoformat(TODAY))}


def projection(d,start,end,*args):
    # A whole-sequence conflict: the Saturday brick also compromises the later openers.
    out=[]
    for n in range(14):
        date=(dt.date.fromisoformat(TODAY)+dt.timedelta(days=n)).isoformat()
        sessions=B.sessions(d.get('plans',{}).get(date) or {})
        run=any(s['sport']=='run' for s in sessions)
        dose=sum(s.get('minutes',0) for p in d['plans'].values() for s in B.sessions(p) if s.get('sport')=='run')
        value=2.63 if run and dose>30 else .8
        out.append({'date':date,'metrics':[{'key':'run_mechanical','before':.7,'after':value,'limit':1.5,'session_dose':.1,'unit':'blocks'},{'key':'cardio_fatigue','before':5,'after':5,'limit':None}]})
    return {x['date']:x for x in out}


async def main():
 with tempfile.TemporaryDirectory() as temp:
    base=pathlib.Path(temp);(base/'rides').mkdir();(base/'profile.json').write_text(json.dumps({'ftp':150,'weight_kg':75}))
    d,load=run_fixture(base)
    candidate=C.capacity_candidates(d,load,TODAY)['candidates'][0]
    assert candidate['status']=='review_candidate' and candidate['suggested_reference']==110
    protected=copy.deepcopy(load);protected['run_progression']={'stage':'protected recovery'};protected['systems']['impact']['tissue']['remodeling']['phase']='plateau'
    assert C.capacity_candidates(d,protected,TODAY)['candidates'][0]['status']=='blocked'
    race=copy.deepcopy(d);race['training_feedback']={};race['events']=[{'date':'2026-10-09','sport':'run','kind':'race'}]
    assert C.capacity_candidates(race,load,TODAY)['candidates'][0]['status']=='more_evidence_needed'
    bad=copy.deepcopy(d);bad['checkins']['2026-10-10']['feet']=7
    assert C.capacity_candidates(bad,load,TODAY)['candidates'][0]['status']=='more_evidence_needed'
    symptom=copy.deepcopy(d);symptom['training_feedback']['2026-10-09:0']['symptoms']=[{'severity':2,'location':'achilles','side':'left','regions':['calves']}]
    assert C.capacity_candidates(symptom,load,TODAY)['candidates'][0]['status']=='blocked'
    missing=copy.deepcopy(d);missing['load_forecasts']={}
    assert not C.capacity_candidates(missing,load,TODAY)['candidates'][0]['observations']
    recovery=copy.deepcopy(d)
    for x in recovery['training_feedback'].values():x['context']['phase']='recovery'
    assert not C.capacity_candidates(recovery,load,TODAY)['candidates'][0]['observations']
    current_poor=copy.deepcopy(d);current_poor['checkins'][TODAY]={'feet':7,'legs':2}
    assert C.capacity_candidates(current_poor,load,TODAY)['candidates'][0]['status']=='blocked'
    hops=copy.deepcopy(d);hops['checkins']['2026-10-10']['hops']=2
    assert C.capacity_candidates(hops,load,TODAY)['candidates'][0]['status']=='more_evidence_needed'
    negative=copy.deepcopy(d)
    for date,records in negative['load_forecasts'].items():records[0]['forecast']['metrics'][0]['after']=.5
    for checkin in negative['checkins'].values():checkin['feet']=7
    decrease=C.capacity_candidates(negative,load,TODAY)['candidates'][0]
    assert decrease['direction']=='decrease' and decrease['suggested_reference']==90
    # A running review recalculates the model while keeping historical doses and protected preferences.
    coach.save(d);revision=program_drafts.revision(d,base,{},[],TODAY)
    original=copy.deepcopy(d)
    with patch.object(B,'running_gate',return_value={'status':'open_for_review','reasons':[]}):
        reviewed=C.preview(d,load,{},[],TODAY,base,revision,{'kind':'capacity','target':'running_block'})
    C.apply(d,base,revision,TODAY,reviewed['draft_id'],True)
    assert d['load_forecasts']==original['load_forecasts'] and load['systems']['impact']['tissue']['remodeling']['reference_points']==100
    adjusted=C.with_capacity(d,load,TODAY,base);assert adjusted['systems']['impact']['tissue']['remodeling']['reference_points']==110
    d=original
    # A completed benchmark is graded without silently recording a capacity increase.
    bm=copy.deepcopy(d);bm['plans']['2026-10-01']={'test':'benchmark_run'}
    bm.setdefault('benchmarks',{}).setdefault('runs',{})['2026-10-01']={'rpe':3,'pain':False}
    benchmark_load=copy.deepcopy(load);benchmark_load['activities'][0].update(impact=200,km=3.22,minutes=32,avg_hr=140,descent_m=5)
    with patch.object(mapserver,'load_state',return_value=benchmark_load),patch.object(coach,'today',return_value=TODAY):
        mapserver.calibration_view(bm,base/'rides')
    assert not bm.get('calibration',{}).get('block') and bm['benchmarks']['runs']['2026-10-01']['result']=='review_candidate'
    # Lifting responds to delayed regional reports, not a heavier strength estimate alone.
    d,load=lift_fixture(base);before=copy.deepcopy(d);coach.save(d)
    assert C.capacity_candidates(d,load,TODAY)['candidates'][1]['status']=='review_candidate'
    poor=copy.deepcopy(d)
    for f in poor['lifting']['followups'].values():f['regions']['glutes']=8
    for date in poor['load_forecasts']:poor['load_forecasts'][date][0]['forecast']['metrics'][0]['after']=.2
    reduction=C.capacity_candidates(poor,{'lifting':lifting.model(poor,dt.date.fromisoformat(TODAY))},TODAY)['candidates'][1]
    assert reduction['direction']=='decrease' and reduction['suggested_reference']<reduction['reference']
    newer=copy.deepcopy(d);newer['lifting']['followups']={}
    assert C.capacity_candidates(newer,load,TODAY)['candidates'][1]['status']=='more_evidence_needed'
    state_revision=program_drafts.revision(d,base,{},[],TODAY)
    preview=C.preview(d,load,{},[],TODAY,base,state_revision,{'kind':'capacity','target':'lift_glutes'})
    assert d==before and preview['record']['reference']>preview['record']['before']
    try:C.apply(d,base,state_revision,TODAY,preview['draft_id'],False);raise AssertionError('approval bypass')
    except ValueError:pass
    result=C.apply(d,base,state_revision,TODAY,preview['draft_id'],True)
    assert result['kind']=='capacity' and d['lifting']==before['lifting'] and d['load_forecasts']==before['load_forecasts']
    model=lifting.model(d,dt.date.fromisoformat(TODAY));assert model['regions']['glutes']['reference_from'].startswith('reviewed')
    assert C.capacity_candidates(d,{'lifting':model},TODAY)['candidates'][1]['status']=='more_evidence_needed'
    assert C.apply(d,base,'changed',TODAY,preview['draft_id'],True)['already_applied']
    # Stale state and expiry require a fresh review.
    coach.save(before);d=copy.deepcopy(before);preview=C.preview(d,load,{},[],TODAY,base,state_revision,{'kind':'capacity','target':'lift_glutes'})
    try:C.apply(d,base,'changed',TODAY,preview['draft_id'],True);raise AssertionError('stale bypass')
    except program_drafts.Conflict:pass
    with patch.object(C.time,'time',return_value=__import__('time').time()+program_drafts.TTL_SECONDS+1):
        try:C.apply(d,base,state_revision,TODAY,preview['draft_id'],True);raise AssertionError('expiry bypass')
        except program_drafts.Conflict:pass
    # Whole-sequence forecast review, unknowns, exact calendar application and completed-day protection.
    d=coach.load(base/'coach.json');d['plans']={}
    for n in (1,3,8):coach.set_sessions(d,(dt.date.fromisoformat(TODAY)+dt.timedelta(days=n)).isoformat(),[{'sport':'run','minutes':20,'name':'Opener' if n==8 else 'Peak run'}])
    with patch.object(B,'projected_loads',side_effect=projection),patch.object(B,'running_gate',return_value={'status':'open_for_review','reasons':[]}):
        out=C.outlook(d,{}, {},[],TODAY);assert all(s['status']=='conflict' for s in out['sessions'])
        revision=program_drafts.revision(d,base,{},[],TODAY)
        changes=[{'date':x['date'],'sessions':[{'sport':'run','minutes':10,'name':'Reduced run'}]} for x in out['sessions']]
        review=C.preview(d,{}, {},[],TODAY,base,revision,{'kind':'calendar','changes':changes})
        assert not review['violations'] and all(s['status']=='within_projected_limits' for s in review['after']['sessions'])
        old=copy.deepcopy(d);C.apply(d,base,revision,TODAY,review['draft_id'],True)
        # A change can't introduce a pattern that breaks a training rule: a hard ride the day after leg lifting.
        legs=(dt.date.fromisoformat(TODAY)+dt.timedelta(days=5)).isoformat();after_legs=(dt.date.fromisoformat(TODAY)+dt.timedelta(days=6)).isoformat()
        rules_d=copy.deepcopy(d);coach.set_sessions(rules_d,legs,[{'sport':'gym','minutes':40,'name':'Strength: lower body'}])
        rules_d['plans'][legs]['sessions'][0]['lift_focus']='lower'
        bad=C.preview(rules_d,{}, {},[],TODAY,base,program_drafts.revision(rules_d,base,{},[],TODAY),
                      {'kind':'calendar','changes':[{'date':after_legs,'sessions':[{'sport':'ride','minutes':45,'name':'Tempo ride','tier':'moderate'}]}]})
        assert any('hard_after_legs' in v for v in bad['violations']),bad['violations']
        fine=C.preview(rules_d,{}, {},[],TODAY,base,program_drafts.revision(rules_d,base,{},[],TODAY),
                       {'kind':'calendar','changes':[{'date':after_legs,'sessions':[{'sport':'ride','minutes':45,'name':'Easy endurance ride','tier':'easy'}]}]})
        assert not any('training rule' in v for v in fine['violations']),fine['violations']
        assert all(B.sessions(d['plans'][x['date']])[0]['minutes']==10 for x in out['sessions']) and old.get('capacity_adjustments')==d.get('capacity_adjustments')
        try:C.preview(d,{}, {changes[0]['date']:[{'sport':'run'}]},[],TODAY,base,revision,{'kind':'calendar','changes':changes});raise AssertionError('completed rewrite')
        except ValueError:pass
        assert [o['date'] for o in review['original']]==[c['date'] for c in changes] and review['original'][0]['sessions']
        # A hold from recent load alone blocks only runs before its projected clear date; later runs face their forecast.
        load_hold={'status':'hold','reasons':['mechanical running load 2.60 blocks exceeds the 1.5-block planning limit'],'model_days':5}
        with patch.object(B,'running_gate',return_value=load_hold):
            review=C.preview(d,{}, {},[],TODAY,base,revision,{'kind':'calendar','changes':changes})
            late=[c['date'] for c in changes if c['date']>=(dt.date.fromisoformat(TODAY)+dt.timedelta(days=5)).isoformat()]
            assert any('hold' in v for v in review['violations']) and late and not any(v.startswith(late[0]) and 'hold' in v for v in review['violations'])
        with patch.object(B,'running_gate',return_value={'status':'hold','reasons':['hopping still pulls'],'model_days':1}):
            review=C.preview(d,{}, {},[],TODAY,base,revision,{'kind':'calendar','changes':changes})
            assert all(any(v.startswith(c['date']) and 'hold' in v for v in review['violations']) for c in changes)
        with patch.object(B,'running_gate',return_value={'status':'hold','reasons':['Mechanical hold']}):
            review=C.preview(d,{}, {},[],TODAY,base,revision,{'kind':'calendar','changes':changes});assert review['violations']
            try:C.apply(d,base,revision,TODAY,review['draft_id'],True);raise AssertionError('hold bypass')
            except ValueError:pass
    # Real HTTP handler and tool contracts.
    coach.save(d);bridge=SimpleNamespace(csv_path=base/'rides/demo.csv',profile={},workouts=[])
    with patch.object(coach,'today',return_value=TODAY),patch.object(mapserver,'load_state',return_value={}):
        unchanged=(base/'coach.json').read_bytes()
        code,_,raw,_=await mapserver.coach_api(bridge,b'GET','/api/coach/coaching-review','/api/coach/coaching-review',b'')
        assert code==200,json.loads(raw)
        assert (base/'coach.json').read_bytes()==unchanged
        code,_,raw,_=await mapserver.coach_api(bridge,b'POST','/api/coach/test','/api/coach/test',json.dumps({'test':'benchmark_run','date':TODAY}).encode())
        assert code==400 and 'hold' in json.loads(raw)['error']
    tools={t['name']:t for t in mcp_server.handle({'id':1,'method':'tools/list'})['tools']}
    assert len(tools)==66 and tools['get_coaching_review']['annotations']['readOnlyHint']
    assert not tools['preview_coaching_change']['annotations']['readOnlyHint']
    assert tools['apply_coaching_change']['inputSchema']['required']==['draft_id','approved']
 print('PASS whole-sequence review, exact edits, holds, delayed capacity evidence, race limits, approval, conflict, expiry and preserved doses')
if __name__=='__main__':asyncio.run(main())
