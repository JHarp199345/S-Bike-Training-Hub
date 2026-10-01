"""Meaningful safeguards for tentative progression and prospective forecast records."""
import copy,datetime as dt,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import bodymap,coach,damage,lifting,recovery,training_block as B


def rejects(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Unsafe input was accepted')


def main():
    first=dt.date(2026,1,1)
    dates=[(first+dt.timedelta(days=i)).isoformat() for i in range(24)]
    doses=[100,100,100]+[0]*21
    before=damage.remodeling_response(dates[:19],doses[:19],block=100)
    d={'plans':{},'checkins':{}}
    for index,kind in [(17,'strength'),(18,'balance')]:
        fields={'test_date':dates[index],'kind':kind,'name':'Comfortable '+kind,'controlled':True,
                'gritted':False,'symptoms':0,'after_ok':True,'followup_date':dates[index+1],'next_day_ok':True}
        recovery.record_check(d,fields,dates[index+1])
    rejects(lambda:recovery.approve_decline(d,before,dates[18]))
    rejects(lambda:recovery.record_check(d,{**fields,'test_date':dates[20],'followup_date':dates[20]},dates[20]))
    original=damage.remodeling_response(dates[:21],doses[:21],block=100)
    assert recovery.status(d,original,dates[20])['review_eligible']
    d['checkins'][dates[20]]={'legs':8}
    assert not recovery.status(d,original,dates[20])['review_eligible']
    rejects(lambda:recovery.approve_decline(d,original,dates[20]))
    d['checkins'].clear()
    approved=recovery.approve_decline(d,original,dates[20])
    changed=damage.remodeling_response(dates[:22],doses[:22],block=100,reviews=d['run_progression']['reviews'])
    assert changed['history'][20]['score']==original['score']
    assert changed['score']<original['score'] and changed['phase']=='decline'
    assert not recovery.status(d,changed,dates[21])['run_eligible']
    # No approval, or one inside the protected part, cannot shorten the curve.
    premature=damage.remodeling_response(dates[:22],doses[:22],block=100,reviews=[{'date':dates[10],'action':'begin_decline'}])
    assert premature['score']==original['score']
    reversed_checkin=copy.deepcopy(d)
    recovery.observe_checkin(reversed_checkin,dates[22],{'legs':8})
    assert reversed_checkin['run_progression']['reviews'][-1]['action']=='restore_plateau'
    bad={**fields,'test_date':dates[22],'followup_date':None,'next_day_ok':None,'symptoms':2}
    recovery.record_check(d,bad,dates[22])
    assert d['run_progression']['reviews'][-1]['action']=='restore_plateau'
    restored=damage.remodeling_response(dates,doses,block=100,reviews=d['run_progression']['reviews'])
    assert restored['history'][22]['score']==original['score']
    assert restored['history'][22]['dose']==0 and not recovery.status(d,restored,dates[23])['run_eligible']
    grit={**fields,'test_date':dates[23],'gritted':True,'followup_date':None,'next_day_ok':None}
    entry=recovery.record_check(d,grit,dates[23]);assert not recovery.successful(entry,dates[23])
    # Shared activity sources are visible; they are not silently added to sport scores.
    body=bodymap.build(0,.9,0,lift={'shoulders':.9})
    shoulder=body['regions']['shoulders']
    assert shoulder['shared'] and shoulder['level']==.6 and shoulder['overlap_index']==1.2
    assert bodymap.overlap_advice(body,'swim') and not bodymap.overlap_advice(body,'run')
    # Actual planned lifting determines legs; upper-body work must not inherit gym average leg cost.
    base={'systems':{},'activities':[{'date':dates[0],'sport':'gym','minutes':30,'engine':30,'impact':0,'muscle':100}],
          'swim_recovery':{},'days':[],'profile':{'ftp':180}}
    bench={'name':'Bench press','kind':'barbell','sets':3,'reps':10,'weight':100,'regions':{'pecs':50,'shoulders':25,'triceps':25}}
    plan={'plans':{dates[1]:{'sessions':[{'sport':'gym','minutes':30,'name':'Upper body','lifts':[bench]}]}},'checkins':{}}
    # Empty systems are supported without inventing recorded fitness.
    out=B.projected_loads(plan,dates[0],[dates[1]],base)
    assert out[dates[1]]['sessions'][0]['doses']['muscle']==0
    leg={**bench,'name':'Leg extension','regions':{'quads':100}}
    plan['plans'][dates[1]]['sessions'][0]['lifts']=[leg]
    out=B.projected_loads(plan,dates[0],[dates[1]],base)
    cleaned=lifting.clean(copy.deepcopy(plan),[leg],draft=True)
    expected=lifting.points(plan,cleaned[0])[0]
    assert abs(out[dates[1]]['sessions'][0]['doses']['muscle']-expected)<.01
    plan['plans'][dates[1]]['sessions'][0].pop('lifts')
    assert B.projected_loads(plan,dates[0],[dates[1]],base)[dates[1]]['sessions'][0]['doses']['muscle'] is None
    # The torque formula is identical to integrating recorded seconds, and reacts to cadence.
    steps=[{'minutes':1,'watts':150}]
    _,p90,_=B.planned_bike_dose({'cadence':[90,90]},steps,180)
    assert abs(p90-.2)<1e-9
    import loads
    assert abs(p90-loads.bike_muscle([{'w':150,'rpm':90}]*60))<1e-9
    assert B.planned_bike_dose({'cadence':[60,60]},steps,180)[1]>p90*2
    coach.set_sessions(plan,dates[2],[{'sport':'ride','minutes':30,'focus':'cadence','cadence':[70,90]}])
    assert plan['plans'][dates[2]]['sessions'][0]['cadence']==[70,90]
    # Structured template stages survive saving and drive cardio + leg estimates.
    import programming
    template=programming.fill_bike(programming.BIKE[1],180,'returning')
    coach.set_sessions(plan,dates[2],[{'sport':'ride','minutes':template['minutes'],'bike_plan':template['bike_plan']}])
    session=plan['plans'][dates[2]]['sessions'][0]
    projected=B.projected_loads(plan,dates[0],[dates[2]],base,workouts=[])[dates[2]]['sessions'][0]['doses']
    direct=B.planned_bike_dose(session,template['bike_plan']['power_steps'],180)
    assert abs(projected['muscle']-direct[1])<.01 and projected['engine']==direct[0]
    rejects(lambda:coach.set_sessions(plan,dates[2],[{'sport':'ride','minutes':1,'bike_plan':{'power_steps':[{'minutes':2,'watts':100}]}}]))
    # Saved predictions survive later recalculation; no retrospective baseline for completed work.
    f={'load_outlooks':[{'date':dates[2],'sessions':[{'sport':'ride','completed':False}],
                        'metrics':[{'key':'cardio_fatigue','name':'Cardio fatigue','unit':'daily load','after':8}]}]}
    snap={};recovery.save_forecasts(snap,f,now=dates[1]+'T08:00:00')
    f['load_outlooks'][0]['metrics'][0]['after']=9
    recovery.save_forecasts(snap,f,now=dates[1]+'T09:00:00')
    assert snap['load_forecasts'][dates[2]][0]['forecast']['metrics'][0]['after']==8
    assert len(snap['load_forecasts'][dates[2]])==2
    assert not recovery.save_forecasts({},f,{dates[2]:[{'sport':'bike'}]},now=dates[2]+'T09:00:00')
    actual={'systems':{'engine':{'fatigue':10}},'days':[]}
    comparison=recovery.comparisons(snap,actual,dates[2])[0]['metrics'][0]
    assert comparison['actual']==10 and comparison['expected']==9 and comparison['difference']==1
    print('PASS protected plateau, reviewed transition, reversal, regional overlap, planned doses and immutable forecasts')

if __name__=='__main__':main()
