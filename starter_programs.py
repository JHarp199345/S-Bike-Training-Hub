"""Editable starter prescriptions, capped at 84 days; forecasts reuse the hub's models."""
import copy
import datetime as dt
import training_block as T
import strength_calibration as C

LEVELS={'easy':.65,'moderate':.85,'higher':1.0}
SOURCE_LINKS=[{'title':'Physical Activity Guidelines: gradual progression','url':'https://www.cdc.gov/physical-activity/media/pdfs/Physical_Activity_Guidelines_2nd_edition.pdf'}, {'title':'ACSM resistance training for health','url':'https://acsm.org/science-spotlight-acsm-releases-new-position-stand-on-resistance-training/'}]

def workout(sport,minutes,week,level,experience,equipment,d,anchors=None,recovery=False):
    m=max(10,int(minutes)); sets=1 if week==0 else 2 if level!='higher' or week<4 else 3
    note='Provisional starter dose. Advance only after the weekly review confirms tolerable load and recovery; otherwise repeat or reduce.'
    s={'sport':sport,'minutes':m,'name':{'ride':'Easy endurance ride','swim':'Basic swim technique','run':'Easy run / walk','gym':'Basic full-body strength'}[sport], 'tier':'easy','note':note,'starter':True,'provisional':week>0}
    if sport=='ride':
        steps=[{'minutes':5,'pct':50,'rpm':80},{'minutes':m-10,'pct':60 if level=='easy' else 65,'rpm':80},{'minutes':5,'pct':45,'rpm':80}]
        s.update(cadence=[70,90],bike_plan={'power_steps':steps,'basis':'Basic steady endurance steps; FTP must be calibrated.'},steps=[f"{x['minutes']} min at {x['pct']}% FTP, comfortable cadence (70–90 rpm)" for x in steps])
    elif sport=='swim':
        # Time includes wall rests. Distances are deliberately small, never inferred from an unknown CSS.
        s['steps']=['5 min easy freestyle with rests as needed','4 × 25 m relaxed freestyle; rest 20–30 seconds at the wall','4 × 25 m alternating easy freestyle and a comfortable technique drill; rest 20–30 seconds',f'Repeat easy 25–50 m lengths with 20–30 seconds rest until {m-5} minutes elapsed; stop earlier if technique deteriorates','Last 5 min: relaxed lengths / cool-down; no paddles required']
        s['swim_plan']={'stroke_mix':{'free':100},'work_mix':{'swim':80,'drill_swim':20},'why':'Basic freestyle consistency and technique; duration includes rests. No hard sets or required butterfly.'}
    elif sport=='run':
        s['steps']=['5 min comfortable walking',f'{m-10} min: alternate 1 min easy running and 2 min walking; conversational effort','5 min walking cool-down']
        s['note']+=' Running requires a fresh readiness review before every exposure; no speed work or automatic shortening of recovery.'
    else:
        sets=min(sets,max(1,int((m-7)/12)))
        import lifting
        bar=equipment=='barbell'
        choices=[('BB squat' if bar else 'Chair squat','barbell' if bar else 'bodyweight','Squat to a comfortable depth; use a light load with at least 3 repetitions in reserve.'),('BB bench press' if bar else 'Incline push-up','barbell' if bar else 'bodyweight','Controlled press; use safeties / a spotter for the bench.'),('BB row' if bar else 'Resistance-band row','barbell' if bar else 'band','Keep the torso stable and pull smoothly.'),('Glute bridge','bodyweight','Lift hips smoothly; stop at a comfortable height.'),('Dead bug','bodyweight','Alternate arm and leg reaches without arching the lower back.')]
        lifts=[]
        for name,kind,how in choices:
            if lifting.excluded(d,name,kind):continue
            anchor=(anchors or {}).get(name)
            weight,basis=C.prescribe(anchor,level,week,recovery) if anchor else (None,None)
            lifts.append({'name':name,'kind':kind,'sets':sets,'reps':8,'weight':weight,'unit':anchor['unit'] if anchor else 'lb','regions':C.SHARES[name],'style':'build','how':how,'equipment':equipment,'rest_seconds':90,'calibration_basis':basis})
        if not lifts:
            raise ValueError('Your lifting rules exclude the starter exercises. Build a custom lifting session instead.')
        s['lifts']=lifts
        s['steps']=['5 min easy mobility and practice repetitions']+[f"{x['name']}: {sets} × 8{(' at '+str(x['weight'])+' '+x['unit']) if x['weight'] is not None else ''}, rest 90 seconds. {x['how']}" for x in lifts]+['2 × 20 seconds comfortable toe-reach with soft knees, without forcing the stretch']
        s['note']+=' Enter your actual working weights and review regional exercise scoring before relying on the lifting load forecast.'
    return s

def build(d,proposal,profile=None,load=None,done=None,workouts=None,today=None):
    """Compare three doses from an identical baseline. No mutation or predicted symptom clearance."""
    d=copy.deepcopy(d)
    profile=profile or {}; start=dt.date.fromisoformat(proposal['start']); end=min(dt.date.fromisoformat(proposal['end']),start+dt.timedelta(days=84))
    anchor=dt.date.fromisoformat(today) if today else start
    if start<anchor:raise ValueError('Starter workouts begin today or later')
    equipment=proposal.get('starter_equipment','basic')
    if equipment not in ('basic','barbell'):raise ValueError('Starter equipment is basic or barbell')
    level=proposal.get('starter_level','easy')
    if level not in LEVELS:raise ValueError('Starter load is easy, moderate or higher')
    experience=profile.get('experience') or {}; loaded=profile.get('start_state')=='loaded'
    readiness={}
    if (load or {}).get('systems'):
        import loads
        readiness=loads.readiness(load,d.get('checkins',{}).get(anchor.isoformat()) or {})
    anchors=C.anchors(proposal.get('strength_anchors') or [])
    assumptions=[]
    if proposal.get('neutral_forecast',True):
        import starter_priors
        load,assumptions=starter_priors.scenario(load)
    candidates=[]
    for name,factor in LEVELS.items():
        plans={};journey=[]
        for w,week in enumerate(proposal['weeks']):
            slots=[x for x in week['slots'] if start.isoformat()<=x['date']<end.isoformat() and x['sport']!='rest' and x.get('source')!='scheduled']
            # Fixed ceilings and small optional increases; every fourth week consolidates.
            growth=1+.05*(w-w//4); consolidate=.8 if w%4==3 else 1
            count=max(1,len(slots)); available=proposal['hours']*60*factor
            weekly=0
            for slot in slots:
                sp=slot['sport']; ex=experience.get({'ride':'bike','gym':'lift'}.get(sp,sp),'new')
                base={'ride':25,'swim':20,'run':20,'gym':30}[sp]*(1.25 if ex=='regular' else 1)
                minutes=min(base*factor*growth*consolidate,available/count)
                decision=(readiness.get('swimming') or {}).get('verdict','go') if sp=='swim' else readiness.get('verdict','go') if sp=='ride' else 'go'
                if w==0 and decision=='rest':continue
                if w==0 and decision=='easy':minutes*=.75
                if loaded:minutes*=.75
                phase=next(p for p in proposal['phases'] if p['start']<=slot['date']<p['end'])
                if phase.get('stage',phase['kind']) in ('assessment','recovery','taper'):minutes=min(minutes,base*.7)
                if minutes<(20 if sp=='gym' else 10):continue # do not exceed the budget by imposing a minimum session
                session=workout(sp,int(minutes),w,name,ex,equipment,d,anchors,phase.get('stage') in ('recovery','taper','assessment'))
                if sp=='gym' and w==0 and proposal.get('assessment')=='week':
                    session['name']='Strength calibration / familiarization'
                    session['steps'].insert(0,'Practice technique, then record one comfortable 6–10 rep set per lift with 2–3 reps left. No true maximum or forced repetitions. Use the result to review the remaining draft.')
                plans.setdefault(slot['date'],{'sessions':[]})['sessions'].append(session);weekly+=session['minutes']
            journey.append({'week':w+1,'start':week['start'],'minutes':weekly,'purpose':'Review / consolidate' if w%4==3 else 'Baseline and technique' if w==0 else 'Conditional endurance development','provisional':w>0})
        scratch=copy.deepcopy(d);scratch.setdefault('plans',{})
        for date,plan in plans.items():
            if not T.sessions(scratch['plans'].get(date) or {}):scratch['plans'][date]=plan
        scratch['phase_profiles']=copy.deepcopy(proposal['phases'])
        import lifting
        for lift,anchor_ in anchors.items():lifting.state(scratch)['strength'][lifting.key(lift)]={'e1rm_kg':anchor_['e1rm_kg'],'source':'Reported calibration set'}
        dates=[(start+dt.timedelta(days=i)).isoformat() for i in range((end-start).days)]
        projection=T.projected_loads(scratch,anchor,dates,load,done,workouts)
        effective={date:{'sessions':copy.deepcopy(T.sessions(plan)),'retained':date not in plans} for date,plan in scratch['plans'].items() if start.isoformat()<=date<end.isoformat()}
        for w in journey:
            w['added_minutes']=w['minutes']
            w['minutes']=sum(s.get('minutes',0) for date,p in effective.items() if w['start']<=date<(dt.date.fromisoformat(w['start'])+dt.timedelta(days=7)).isoformat() for s in p['sessions'])
        first=projection.get(dates[0],{}).get('metrics_by_key',{}) if dates else {}
        last=projection.get(dates[-1],{}).get('metrics_by_key',{}) if dates else {}
        summary=[{'key':key,'name':r['name'],'unit':r['unit'],'start':first.get(key,{}).get('before'),'end':r['after'],'expected':r['expected']} for key,r in last.items() if key in ('cardio_conditioning','cardio_fatigue','muscle_fatigue','run_mechanical','swim_recovery','strength')]
        flags=[{'date':date,'metric':r['name'],'after':r['after'],'limit':r['limit']} for date,f in projection.items() for r in f['metrics'] if r.get('over_limit')]
        candidates.append({'level':name,'plans':plans,'display_plans':effective,'journey':journey,'projection':projection,'summary':summary,'limit_flags':flags,'unknown_metrics':[r['name'] for r in summary if r['end'] is None],'total_minutes':sum(w['minutes'] for w in journey),'added_minutes':sum(w['added_minutes'] for w in journey)})
    selected=next(c for c in candidates if c['level']==level)
    return {'forecast_date':anchor.isoformat(),'selected':level,'detail_end':end.isoformat(),'max_detail_days':84,'plans':selected['plans'],'display_plans':selected['display_plans'],'candidates':candidates,'strength_anchors':anchors,'assumptions':assumptions,'sources':SOURCE_LINKS,'notice':'Starter details cover at most 12 weeks; later macro phases remain open for programming. Higher load means more proposed work, not better results. Forecasts use recorded baselines first, with explicit provisional defaults for missing readings when enabled. Unknown working weights remain unestimated. Conditioning is a modeled training-load trend, not a promised performance gain. Weekly review can repeat, reduce or replace every workout. Load-limit flags require review before training.'}
