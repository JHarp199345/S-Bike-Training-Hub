"""Editable starter prescriptions, capped at 84 days; forecasts reuse the hub's models."""
import collections
import copy
import datetime as dt
import training_block as T
import strength_calibration as C

LEVELS={'easy':.65,'moderate':.85,'higher':1.0}
SOURCE_LINKS=[{'title':'Physical Activity Guidelines: gradual progression','url':'https://www.cdc.gov/physical-activity/media/pdfs/Physical_Activity_Guidelines_2nd_edition.pdf'}, {'title':'ACSM resistance training for health','url':'https://acsm.org/science-spotlight-acsm-releases-new-position-stand-on-resistance-training/'}]
# Share of the athlete's available weekly time: where the program starts, and where the peak weeks land.
# The peak never exceeds the time they said they have; consolidation and taper weeks drop below the line.
VOLUME={'easy':(.45,.80),'moderate':(.50,.90),'higher':(.55,.95)}
STAGE_PURPOSE={'assessment':'Optional test week: baselines and technique','base':'Foundation: easy, repeatable sessions',
               'build':'Development: longer sessions and one quality day per sport','specific':'Peak: race-specific sessions and bricks',
               'taper':'Final preparation: less volume, sharp openers','recovery':'Recovery: reduced load','race_week':'Race week: openers, rest, race'}
CAPS={'ride':150,'swim':60,'run':75,'gym':45}
FLOOR={'ride':15,'swim':15,'run':15,'gym':20}
ROLE_WEIGHT={'race_pace':1.5,'quality':1.25,'easy':.85,'opener':.7,'test':1.0}
OPENER_CAP={'ride':35,'swim':30,'run':25,'gym':25}
LONG_WEIGHT={'ride':2.0,'run':1.4,'swim':1.2,'gym':.8}

# Lifting split (the athlete's preference): which movement groups each session trains. Splits rotate focuses;
# full body trains everything each time. Exercises: (barbell name, basic name, basic kind, how).
LIFT_SPLITS = {'full_body':['full'],'upper_lower':['lower','upper'],'push_pull':['push','pull'],
               'push_pull_legs':['push','pull','legs'],'lower_push_pull':['lower','upper_push','upper_pull'],
               'four_way':['knee','hip','upper_push','upper_pull']}
LIFT_GROUPS = {'full':['knee','upper_push','upper_pull','hip'],'lower':['knee','hip','knee2','hip2'],'upper':['upper_push','upper_pull','push2','pull2'],
               'push':['knee','upper_push','push2'],'pull':['hip','upper_pull','pull2'],'legs':['knee','hip','knee2','hip2'],
               'knee':['knee','knee2'],'hip':['hip','hip2'],'upper_push':['upper_push','push2'],'upper_pull':['upper_pull','pull2']}
LIFT_MOVES = {'knee':('BB squat','Chair squat','bodyweight','Squat to a comfortable depth; use a light load with at least 3 repetitions in reserve.'),
              'knee2':('Split squat','Split squat','bodyweight','Rear foot on the floor, controlled depth; hold support if needed.'),
              'hip':('Glute bridge','Glute bridge','bodyweight','Lift hips smoothly; stop at a comfortable height.'),
              'hip2':('BB Romanian deadlift','Single-leg hip hinge','bodyweight','Hinge at the hips with a long spine; stop where the hamstrings tighten.'),
              'upper_push':('BB bench press','Incline push-up','bodyweight','Controlled press; use safeties / a spotter for the bench.'),
              'push2':('BB overhead press','Pike push-up','bodyweight','Press overhead without arching the lower back.'),
              'upper_pull':('BB row','Resistance-band row','band','Keep the torso stable and pull smoothly.'),
              'pull2':('Band pull-apart','Band pull-apart','band','Arms straight, squeeze the shoulder blades, slow return.')}
LIFT_LEGS = {'full','lower','push','pull','legs','knee','hip'}
LIFT_NAMES = {'full':'full-body','lower':'lower body','upper':'upper body','push':'push (squat + press)','pull':'pull (hinge + row)',
              'legs':'legs','knee':'knee-dominant','hip':'hip-dominant','upper_push':'upper push','upper_pull':'upper pull'}


def workout(sport,minutes,week,level,experience,equipment,d,anchors=None,recovery=False,stage='base',role='easy',run_open=True,lift_focus='full'):
    m=max(10,int(minutes)); sets=1 if week==0 else 2 if level!='higher' or week<4 else 3
    note='Provisional starter dose. Advance only after the weekly review confirms tolerable load and recovery; otherwise repeat or reduce.'
    s={'sport':sport,'minutes':m,'name':{'ride':'Easy endurance ride','swim':'Basic swim technique','run':'Easy run / walk','gym':'Basic full-body strength'}[sport], 'tier':'easy','note':note,'starter':True,'provisional':week>0}
    if sport=='ride':
        steps,name,tier=ride_steps(m,level,role)
        s.update(name=name,tier=tier,cadence=[70,95],bike_plan={'power_steps':steps,'basis':'Power targets from your FTP; calibrate it in the test week.'},
                 steps=[f"{x['minutes']} min at {x['pct']}% FTP{(' · '+x['label']) if x.get('label') else ''}" for x in steps])
    elif sport=='swim' and role!='easy':
        s.update(name={'long':'Steady endurance swim','quality':'Swim: steady 100s','race_pace':'Swim: race-pace 50s and sighting',
                       'opener':'Swim openers','test':'Swim test: timed 400 m'}.get(role,'Swim'),tier='moderate' if role in ('quality','race_pace','test') else 'easy')
        main={'long':f'{m-10} min continuous or 100–200 m repeats at an easy, steady pace; 15–20 s rest between repeats',
              'quality':f'{max(1,(m-12)//3)} × 100 m steady (comfortably hard), 20–30 s rest; easy 50 between rounds',
              'race_pace':f'{max(4,(m-14)//2)} × 50 m at race effort, 20 s rest; every 4th length lift your eyes to sight forward (open-water practice)',
              'opener':'4 × 50 m at race effort with full recovery; everything else easy',
              'test':'After the warm-up: 400 m steady-hard (time it), 5 min easy, 200 m steady-hard (time it). The two times give your swim pace (CSS).'}.get(role)
        s['steps']=['5 min easy freestyle with rests as needed',main,'5 min easy cool-down']
        s['swim_plan']={'stroke_mix':{'free':100},'work_mix':{'swim':85,'drill_swim':15},'why':STAGE_PURPOSE.get(stage,'')}
    elif sport=='swim':
        # Time includes wall rests. Distances are deliberately small, never inferred from an unknown CSS.
        s['steps']=['5 min easy freestyle with rests as needed','4 × 25 m relaxed freestyle; rest 20–30 seconds at the wall','4 × 25 m alternating easy freestyle and a comfortable technique drill; rest 20–30 seconds',f'Repeat easy 25–50 m lengths with 20–30 seconds rest until {m-5} minutes elapsed; stop earlier if technique deteriorates','Last 5 min: relaxed lengths / cool-down; no paddles required']
        s['swim_plan']={'stroke_mix':{'free':100},'work_mix':{'swim':80,'drill_swim':20},'why':'Basic freestyle consistency and technique; duration includes rests. No hard sets or required butterfly.'}
    elif sport=='run':
        names={'easy':'Easy run / walk','long':'Longer easy run','quality':'Steady run with strides','race_pace':'Race-pace run',
               'brick':'Brick run (straight off the bike)','opener':'Run openers','test':'Easy run + hop test'}
        if role=='easy' and week>=4 and run_open:names['easy']='Easy run'
        s.update(name=names.get(role,'Easy run / walk'),tier='moderate' if role in ('quality','race_pace','brick') else 'easy')
        main={'easy':f'{m-10} min: alternate 1 min easy running and 2 min walking; conversational effort' if week<4 or not run_open else f'{m-10} min easy continuous running; walk breaks whenever you want',
              'long':f'{m-10} min easy continuous running at conversation pace; walk breaks are fine',
              'quality':f'{m-14} min steady running, then 4 × 20 s relaxed strides with full walk-back recovery',
              'race_pace':f'3 × {max(3,(m-14)//4)} min at goal race effort with 2 min easy jogging between',
              'brick':f'{max(8,m-4)} min: find your running legs, then settle at goal race effort; this is practice for the transition',
              'opener':'10 min easy, 3 × 20 s at race effort, easy to finish',
              'test':f'{m-10} min easy running, then the single-leg hop test (record pain-free hops on each leg)'}.get(role)
        s['steps']=(['Start running within 2 minutes of finishing the ride',main,'3 min walking'] if role=='brick' else
                    ['5 min comfortable walking',main,'5 min walking cool-down'])
        s['note']+=' Running requires a fresh readiness review before every exposure; no speed work or automatic shortening of recovery.'
    else:
        focus=lift_focus if lift_focus in LIFT_GROUPS else 'full'
        if focus!='full':s['name']=f"Strength: {LIFT_NAMES[focus]}"
        if stage in ('taper','specific') or role=='opener':
            sets=1
            s['name']='Strength maintenance (light)'+(f": {LIFT_NAMES[focus]}" if focus!='full' else '')
        sets=min(sets,max(1,int((m-7)/12)))
        import lifting
        bar=equipment=='barbell'
        choices=[]
        for g in LIFT_GROUPS[focus]:
            heavy,basic,kind,how=LIFT_MOVES[g]
            barbell=bar and heavy.startswith('BB ')
            choices.append((heavy if barbell else basic,'barbell' if barbell else kind,how))
        choices.append(('Dead bug','bodyweight','Alternate arm and leg reaches without arching the lower back.'))
        lifts=[]
        for name,kind,how in choices:
            if lifting.excluded(d,name,kind):continue
            anchor=(anchors or {}).get(name)
            weight,basis=C.prescribe(anchor,level,week,recovery) if anchor else (None,None)
            lifts.append({'name':name,'kind':kind,'sets':sets,'reps':8,'weight':weight,'unit':anchor['unit'] if anchor else 'lb','regions':C.SHARES[name],'style':'build','how':how,'equipment':equipment,'rest_seconds':90,'calibration_basis':basis})
        if not lifts:
            raise ValueError('Your lifting rules exclude the starter exercises. Build a custom lifting session instead.')
        # the same shape as any planned lift (seconds, tempo, per side, scored), so checking it off works
        norm=lifting.clean(d,lifts,draft=True)
        for n,raw in zip(norm,lifts):n.update(rest_seconds=raw['rest_seconds'],calibration_basis=raw['calibration_basis'])
        s['lifts']=lifts=norm
        s['steps']=['5 min easy mobility and practice repetitions']+[f"{x['name']}: {sets} × 8{(' at '+str(x['weight'])+' '+x['unit']) if x['weight'] is not None else ''}, rest 90 seconds. {x['how']}" for x in lifts]+['2 × 20 seconds comfortable toe-reach with soft knees, without forcing the stretch']
        s['note']+=' Enter your actual working weights and review regional exercise scoring before relying on the lifting load forecast.'
    return s


def ride_steps(m,level,role):
    """Power steps (minutes at % FTP) for a ride of m minutes in this role."""
    wu,cd=(10,5) if m>=40 else (5,5)
    main=m-wu-cd
    easy=60 if level=='easy' else 65
    def reps(n,on,off,pct,label):
        n=max(1,min(n,main//(on+off)))
        out=[]
        for i in range(n):
            out.append({'minutes':on,'pct':pct,'rpm':88,'label':label})
            if i<n-1 or main-n*(on+off)>0:out.append({'minutes':off,'pct':55,'rpm':85,'label':'easy'})
        rest=main-sum(x['minutes'] for x in out)
        if rest>0:out.append({'minutes':rest,'pct':easy,'rpm':85})
        return out
    if role=='quality':body,name,tier=reps(3,8,4,88,'sweet spot'),'Sweet-spot intervals','moderate'
    elif role=='race_pace':body,name,tier=reps(3,10,3,93,'race pace'),'Race-pace intervals','hard'
    elif role=='opener':body,name,tier=reps(3,1,3,105,'opener'),'Openers: short race-pace touches','moderate'
    elif role=='test':body,name,tier=[{'minutes':main,'pct':easy,'rpm':85,'label':'or the FTP ramp test on the Ride page'}],'FTP test (optional ramp test)','hard'
    elif role=='long':body,name,tier=[{'minutes':main,'pct':easy+3,'rpm':85}],'Long endurance ride','easy'
    else:body,name,tier=[{'minutes':main,'pct':easy,'rpm':85}],'Easy endurance ride','easy'
    return [{'minutes':wu,'pct':50,'rpm':85,'label':'warm-up'}]+body+[{'minutes':cd,'pct':45,'rpm':85,'label':'cool-down'}],name,tier


def week_stage(week):
    """The phase covering most of the week's days (a taper starting midweek makes it a taper week)."""
    days=collections.Counter(x.get('stage') for x in week.get('slots',[]) if x.get('stage'))
    if days:
        return days.most_common(1)[0][0]
    return (week.get('phase') or {}).get('stage') or (week.get('phase') or {}).get('kind') or 'base'


def week_fractions(weeks,level,target=None):
    """(share of available time, stage, shape) per week. Two different peaks:
      peak volume       the last development weeks: the most hours, mostly aerobic
      peak performance  event preparation: a little less volume, race-specific intensity
    before them the optional test week is light and the foundation builds from the starting share (every fourth
    building week consolidates, no week more than ~12% over the last); after them a taper, and race week light."""
    lo,hi=VOLUME[level]
    stages=[week_stage(w) for w in weeks]
    ramp=[i for i,s in enumerate(stages) if s in ('base','build')]
    last_build=ramp[-1] if ramp else 0
    span=max(1,len(ramp)-1)
    out=[];k=0;prev=None
    for i,stage in enumerate(stages):
        end=(dt.date.fromisoformat(weeks[i]['start'])+dt.timedelta(days=7)).isoformat()
        shape='build'
        if target and weeks[i]['start']<=target<end:
            f,stage,shape=.40,'race_week','race'
        elif stage=='assessment':f,shape=max(.35,lo-.10),'test'
        elif stage=='recovery':f,shape=lo,'recovery'
        elif stage=='taper':f,shape=.65*hi,'taper'
        elif stage=='specific':f,shape=.90*hi,'peak_performance'
        else:
            f=lo+(hi-lo)*min(1,k/span)
            if k%4==3 and i!=last_build:f,shape=f*.8,'consolidation'
            else:
                if prev:f=min(f,prev*1.12)
                prev=f
                if f>=.95*hi:shape='peak_volume'
            k+=1
        out.append((round(min(f,hi),3),stage,shape))
    return out

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
    target=proposal.get('target')
    tri=proposal.get('sport')=='tri'
    for name,factor in LEVELS.items():
        plans={};journey=[]
        fractions=week_fractions(proposal['weeks'],name,target)
        for w,week in enumerate(proposal['weeks']):
            slots=[x for x in week['slots'] if start.isoformat()<=x['date']<end.isoformat() and x['sport']!='rest' and x.get('source')!='scheduled']
            frac,stage,shape=fractions[w]
            if stage=='race_week' and target:
                # the day before the race is rest; two days before, openers; nothing after the race in this week
                before=(dt.date.fromisoformat(target)-dt.timedelta(days=1)).isoformat()
                slots=[x for x in slots if x['date']<target and x['date']!=before and x['sport']!='gym']
            budget=proposal['hours']*60*frac*(.75 if loaded else 1)
            plan_slots=[]
            for slot in slots:
                sp=slot['sport'];ex=experience.get({'ride':'bike','gym':'lift'}.get(sp,sp),'new')
                decision=(readiness.get('swimming') or {}).get('verdict','go') if sp=='swim' else readiness.get('verdict','go') if sp=='ride' else 'go'
                if w==0 and decision=='rest':continue
                plan_slots.append({'slot':slot,'sport':sp,'ex':ex,'scale':.75 if w==0 and decision=='easy' else 1})
            # roles: one long session (the goal sport's endurance day), a quality day per endurance sport once the
            # foundation is laid, race-pace work and a brick at the peak, openers in the taper
            endurance=[p for p in plan_slots if p['sport']!='gym']
            longest=None
            if endurance and stage not in ('assessment','race_week'):
                pref=[p for p in endurance if p['sport']==('ride' if tri or proposal.get('sport') in ('tri','general') else proposal.get('sport'))]
                longest=(pref or endurance)[-1]
            seen=set()
            # no hard ride or run the day after a leg-lifting session (shared legs); swims are unaffected
            leg_days={(dt.date.fromisoformat(p['slot']['date'])+dt.timedelta(days=1)).isoformat() for p in plan_slots
                      if p['sport']=='gym' and p['slot'].get('lift_focus','full') in LIFT_LEGS}
            leg_days|={(dt.date.fromisoformat(k)+dt.timedelta(days=1)).isoformat() for k,v in plans.items()    # last week's Sunday
                       if any(x['sport']=='gym' and x.get('lift_focus','full') in LIFT_LEGS for x in v['sessions'])}
            for k,p in enumerate(plan_slots):
                sp=p['sport'];role='easy'
                after_legs=sp in ('ride','run') and p['slot']['date'] in leg_days
                later=any(q['sport']==sp and q['slot']['date'] not in leg_days for q in plan_slots[k+1:])
                hard_ok=not after_legs or not later          # wait for a later fresh day when there is one
                if stage=='assessment':role='test' if sp not in seen and sp!='gym' else 'easy'
                elif stage in ('taper','race_week'):role='opener' if sp not in seen else 'easy'
                elif p is longest:role='long'
                elif stage=='specific' and sp not in seen and sp!='gym' and hard_ok:role='race_pace'
                elif stage=='build' and shape!='consolidation' and sp not in seen and sp!='gym' and hard_ok:role='quality'
                if sp!='gym' and (role!='easy' or stage in ('assessment','taper','race_week') or hard_ok):seen.add(sp)
                p['role']=role
            weights=[LONG_WEIGHT[p['sport']] if p['role']=='long' else 1.0 if p['sport']=='gym' else ROLE_WEIGHT.get(p['role'],1.0)
                     for p in plan_slots]
            total=sum(weights) or 1
            brick=tri and stage=='specific' and longest is not None and longest['sport']=='ride' and not proposal.get('running_hold')
            if brick:
                budget_brick=min(20,max(10,.08*budget));budget-=budget_brick
                # the brick is the week's race-effort run: any other run stays easy, and never the day before it
                bday=dt.date.fromisoformat(longest['slot']['date'])
                wk0=dt.date.fromisoformat(week['start'])
                for p in plan_slots:
                    if p['sport']=='run':
                        p['role']='easy'
                        if abs((dt.date.fromisoformat(p['slot']['date'])-bday).days)<=1:
                            # move it to the least busy day at least two days from the brick, else drop it
                            busy=collections.Counter(q['slot']['date'] for q in plan_slots)
                            free=[(wk0+dt.timedelta(days=k)).isoformat() for k in range(7)
                                  if abs(k-(bday-wk0).days)>=2 and start.isoformat()<=(wk0+dt.timedelta(days=k)).isoformat()<end.isoformat()]
                            if free:p['slot']=dict(p['slot'],date=min(free,key=lambda x:(busy[x],x)))
                            else:p['drop']=True
                keep_idx=[i for i,p in enumerate(plan_slots) if not p.get('drop')]
                plan_slots=[plan_slots[i] for i in keep_idx];weights=[weights[i] for i in keep_idx];total=sum(weights) or 1
            # share the budget by weight; a session that would fall under its floor is dropped and its share goes
            # to the others (never over a cap, never over the week's budget)
            keep=list(range(len(plan_slots)));mins={}
            for _ in range(len(plan_slots)+1):
                left=budget-sum(mins.get(i,0) for i in range(len(plan_slots)) if i not in keep)
                tw=sum(weights[i] for i in keep) or 1
                mins={i:min(CAPS[plan_slots[i]['sport']],OPENER_CAP[plan_slots[i]['sport']] if plan_slots[i]['role']=='opener' else 999,
                            25 if stage in ('taper','race_week') and plan_slots[i]['sport']=='gym' else 999,
                            left*weights[i]/tw)*plan_slots[i]['scale'] for i in keep}
                low=[i for i in keep if mins[i]<FLOOR[plan_slots[i]['sport']]]
                if not low:break
                keep.remove(min(low,key=lambda i:weights[i]))
                mins={}
            weekly=0
            for i,p in enumerate(plan_slots):
                if i not in keep:continue
                sp=p['sport'];minutes=mins[i]
                rec=stage in ('recovery','taper','assessment','race_week') or shape=='consolidation'
                session=workout(sp,int(minutes),w,name,p['ex'],equipment,d,anchors,rec,stage,p['role'],not proposal.get('running_hold'),
                                p['slot'].get('lift_focus','full'))
                session['shape']=shape
                if sp=='gym':session['lift_focus']=p['slot'].get('lift_focus','full')
                if sp=='gym' and w==0 and proposal.get('assessment')=='week':
                    session['name']='Strength calibration / familiarization'
                    session['steps'].insert(0,'Practice technique, then record one comfortable 6–10 rep set per lift with 2–3 reps left. No true maximum or forced repetitions. Use the result to review the remaining draft.')
                plans.setdefault(p['slot']['date'],{'sessions':[]})['sessions'].append(session);weekly+=session['minutes']
                if brick and p is longest:
                    run=workout('run',int(budget_brick),w,name,experience.get('run','new'),equipment,d,anchors,False,stage,'brick',True)
                    run['shape']=shape
                    plans[p['slot']['date']]['sessions'].append(run);weekly+=run['minutes']
            if stage=='race_week' and target and start.isoformat()<=target<=end.isoformat():
                plans.setdefault(target,{'sessions':[]})['sessions'].append({'sport':'other','minutes':0,'name':f"Race day: {proposal.get('goal') or 'your event'}",
                    'tier':'race','shape':'race','steps':['Easy 10–15 min warm-up you have practiced','Race your plan: start controlled, finish strong','Record how it went in the check-in'],
                    'note':'The goal of the whole program.','starter':True,'provisional':False})
            journey.append({'week':w+1,'start':week['start'],'minutes':weekly,'budget_minutes':round(proposal['hours']*60*frac),
                            'share_of_available':round(weekly/(proposal['hours']*60),2),'stage':stage,'shape':shape,
                            'purpose':'Consolidation: an easier week to absorb the work' if shape=='consolidation' else
                                      'Peak volume: the most hours, mostly aerobic' if shape=='peak_volume' else STAGE_PURPOSE.get(stage,'Training'),
                            'provisional':w>0})
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
