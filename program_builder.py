"""Event-first phase proposals. Saves planning intent, never workout prescriptions or clearance."""
import copy
import datetime as dt
import math
import phaseblend as P

PURPOSE={
 'assessment':('Assessment week','Review baseline data and perform only readiness-appropriate assessments.','blue','swimming'),
 'recovery':('Recovery','Reduce accumulated fatigue while preserving eligible training.','teal','recovery'),
 'base':('Foundation','Establish repeatable training and assess tolerance.','blue','swimming'),
 'build':('Development','Develop the priority abilities with measured progression.','purple','cycling'),
 'specific':('Event preparation','Practice the demands of the goal when readiness permits.','orange','lifting'),
 'taper':('Final preparation','Ease accumulated fatigue and prepare for the event.','gold','running')}

def propose(d,fields,today,gate):
    import capacity_planning
    capacity_demands=capacity_planning.goals(fields.get('capacity_demands'))
    start=P.date(fields.get('start') or today)
    target=P.date(fields['target']) if fields.get('target') else start+dt.timedelta(days=int(fields.get('horizon_days',84)))
    span=(target-start).days
    if not 1<=span<=366:raise ValueError('Choose a target 1–366 days after the start')
    goal=str(fields.get('goal') or 'Training goal').strip()[:100]
    outcome=str(fields.get('outcome') or 'Finish comfortably')[:150]
    budget_mode=fields.get('budget_mode','availability')
    if budget_mode not in ('availability','starting_budget'):raise ValueError('Budget is availability or a reviewed starting budget')
    long_term_goal=str(fields.get('long_term_goal') or '')[:200]
    hours=fields.get('hours',4)
    if isinstance(hours,bool) or not isinstance(hours,(int,float)) or not math.isfinite(hours) or not 0<hours<=40:raise ValueError('Available time is more than 0 and at most 40 hours per week')
    sport=fields.get('sport','run')
    if sport not in (*P.SPORTS,'tri','general'):raise ValueError('Choose a recognized goal sport')
    focus=fields.get('focus','balanced')
    if focus not in P.PROFILES or focus=='recovery':raise ValueError('Choose a development emphasis')
    entry=fields.get('entry','auto')
    if entry not in ('auto','foundation','build','recovery'):raise ValueError('Choose a starting approach')
    # The running gate is a restriction on prescriptions, never a forecast clearance date.
    restricted=gate.get('status')!='open_for_review'
    needs_recovery=entry=='recovery' or (entry=='auto' and sport in ('run','tri') and restricted)
    assessment=fields.get('assessment','existing')
    if assessment not in ('week','existing'):raise ValueError('Assessment is week or existing')
    priorities=fields.get('priorities')
    if priorities is not None and (not isinstance(priorities,dict) or set(priorities)!=set(P.SPORTS) or any(x not in P.MODES for x in priorities.values())):raise ValueError('Choose Build, Maintain or Pause for each sport')
    if priorities and all(x=='pause' for x in priorities.values()):raise ValueError('Select at least one active sport')
    options=validate_options(fields.get('schedule_options') or {})
    assessment_days=min(7,span-7) if assessment=='week' and span>14 else 0
    kinds=[('assessment',assessment_days)] if assessment_days else []
    left=span
    taper=min(10,max(1,span//8))
    if not fields.get('target'):
        kinds=[]
        if assessment_days:kinds.append(('assessment',assessment_days))
        remaining=span-assessment_days
        if needs_recovery:
            n=min(28,remaining);kinds.append(('recovery',n));remaining-=n
        elif entry in ('auto','foundation') and remaining>7:
            n=min(21,remaining//3);kinds.append(('base',n));remaining-=n
        while remaining>0:
            n=min(42,remaining);kinds.append(('build',n));remaining-=n
    elif span<=14:kinds=[('taper',span)]
    else:
        work=span-taper-assessment_days
        if needs_recovery:
            n=min(28,max(7,work//3));n=min(n,work);kinds.append(('recovery',n));work-=n
        elif entry in ('auto','foundation'):
            n=min(28,max(7,work//4));n=min(n,work);kinds.append(('base',n));work-=n
        specific=min(21,work//3) if work>=21 else 0
        build=work-specific
        while build>0:
            n=min(56,build);kinds.append(('build',n));build-=n
        if specific:kinds.append(('specific',specific))
        kinds.append(('taper',taper))
    cursor=start;phases=[]
    for kind,n in kinds:
        name,why,color,art=PURPOSE[kind]
        mode={s:'improve' if focus in ('balanced',s) else 'maintain' for s in P.SPORTS}
        involved=('ride','swim','run') if sport=='tri' else (sport,)
        for s in involved:
            if s in mode:mode[s]='improve'
        if priorities is not None:mode=copy.deepcopy(priorities)
        if kind in ('recovery','taper','assessment'):
            mode={s:'pause' if mode[s]=='pause' else 'maintain' for s in P.SPORTS}
        phase={'id':cursor.isoformat(),'start':cursor.isoformat(),'end':(cursor+dt.timedelta(days=n)).isoformat(),
               'days':n,'weeks':round(n/7,2),'profile':'recovery' if kind=='recovery' else focus,
               'kind':'build' if kind=='specific' else 'base' if kind=='assessment' else kind,'modes':mode,'weights':{},'label':name,
               'purpose':why,'color':color,'art':art,'stage':kind}
        phases.append(phase);cursor+=dt.timedelta(days=n)
    # A coach can submit a reviewed, complete timeline through the same workflow.
    if 'phases' in fields:
        reviewed=fields['phases']
        if not isinstance(reviewed,list) or not 1<=len(reviewed)<=24:raise ValueError('Provide 1–24 reviewed phases')
        scratch={'phase_profiles':[]};cursor=start;phases=[]
        for raw in reviewed:
            if not isinstance(raw,dict) or date_start(raw)!=cursor:raise ValueError('Reviewed phases must be ordered and contiguous from the program start')
            phase=P.save(scratch,raw,today)
            phases.append(phase);cursor=P.date(phase['end'])
        if cursor not in (target,target+dt.timedelta(days=1)):raise ValueError('Reviewed phases must cover the target date')
    macro_end=max(target,P.date(phases[-1]['end']))
    changed=review_changes(d,phases,start,macro_end)
    event_target=target.isoformat() if fields.get('target') else None
    return {'planning_mode':'capacity','capacity_demands':capacity_demands,'goal':goal,'sport':sport,'outcome':outcome,'start':start.isoformat(),'target':event_target,'end':macro_end.isoformat(),'horizon_days':span,
            'hours':hours,'budget_mode':budget_mode,'long_term_goal':long_term_goal,'focus':focus,'entry':entry,'assessment':assessment,'priorities':priorities,'schedule_options':options,'changes':changed,'phases':phases,'weeks':macro_weeks(phases,start,macro_end,focus,sport,restricted,hours,d.get('plans'),options),'running_hold':restricted,
            'notice':'Phase dates are planning checkpoints, not clearance dates. Running restrictions remain in force across every phase. Sunday reviews can revise the remaining program. '+('Starting training time is reviewed weekly and may grow when forecasts, responses and availability support it.' if budget_mode=='starting_budget' else 'Available time is the most a week will use: the program starts well below it and builds toward it for the peak, as reviews and forecasts allow.')}

def date_start(phase):
    return P.date(phase.get('start'))


def accept(d,proposal):
    # All validation completes before replacing active intent. History and workouts survive.
    scratch=copy.deepcopy(d);scratch['phase_profiles']=[]
    cutoff=P.date(proposal['start'])
    for old in d.get('phase_profiles',[]):
        if P.date(old['start'])<cutoff:
            prior=copy.deepcopy(old)
            if P.date(prior['end'])>cutoff:
                prior['end']=cutoff.isoformat();prior['days']=(cutoff-P.date(prior['start'])).days;prior['weeks']=round(prior['days']/7,2)
            scratch['phase_profiles'].append(prior)
    for phase in proposal['phases']:
        P.save(scratch,phase,proposal['start'])
    history=copy.deepcopy(d.get('program_history',[]))
    if d.get('program_goal') or d.get('phase_profiles'):
        history.append({'replaced_from':proposal['start'],'goal':copy.deepcopy(d.get('program_goal')),'phases':copy.deepcopy(d.get('phase_profiles',[])),'weeks':copy.deepcopy(d.get('program_macro_weeks',[]))})
    d['program_history']=history[-20:]
    d['phase_profiles']=scratch['phase_profiles']
    d['program_goal']={k:v for k,v in proposal.items() if k not in ('phases','weeks','changes','starter','capacity_review')}
    if proposal.get('starter'):
        starter=proposal['starter']
        import lifting
        for lift,anchor in starter.get('strength_anchors',{}).items():lifting.state(d)['strength'][lifting.key(lift)]={'e1rm_kg':anchor['e1rm_kg'],'source':'Reported calibration set','date':proposal['start']}
        chosen=next(c for c in starter['candidates'] if c['level']==starter['selected'])
        snapshots=d.setdefault('program_forecast_history',[])
        snapshots.append({'forecast_date':starter['forecast_date'],'start':proposal['start'],'end':starter['detail_end'],'level':starter['selected'],'projection':copy.deepcopy(chosen['projection']),'notice':starter['notice']})
        d['program_forecast_history']=snapshots[-12:]
        for date,plan in proposal['starter']['plans'].items():
            import training_block
            if not training_block.sessions(d.setdefault('plans',{}).get(date) or {}):
                d['plans'][date]=copy.deepcopy(plan)
    d['program_macro_weeks']=copy.deepcopy(proposal['weeks'])
    return proposal


def validate_options(raw):
    if not isinstance(raw,dict):raise ValueError('Provide weekly scheduling preferences')
    first=raw.get('first_sport','auto')
    if first not in (*P.SPORTS,'auto'):raise ValueError('Choose a recognized first sport')
    available=raw.get('available_days',[0,1,2,3,4,5,6]);rest=raw.get('rest_days',[6])
    for days in (available,rest):
        if not isinstance(days,list) or any(isinstance(x,bool) or not isinstance(x,int) or x not in range(7) for x in days):raise ValueError('Choose weekdays Monday through Sunday')
    if not set(available)-set(rest):raise ValueError('Leave at least one available training day')
    import starter_programs
    split=raw.get('lift_split','full_body')
    if split not in starter_programs.LIFT_SPLITS:raise ValueError('Lifting split is one of '+', '.join(starter_programs.LIFT_SPLITS))
    in_row=raw.get('max_lift_days_in_row',4)
    if isinstance(in_row,bool) or not isinstance(in_row,int) or not 1<=in_row<=5:raise ValueError('Lifting days in a row is 1-5')
    return {'first_sport':first,'available_days':sorted(set(available)),'rest_days':sorted(set(rest)),'allow_doubles':bool(raw.get('allow_doubles',False)),
            'lift_split':split,'max_lift_days_in_row':in_row}


# What each session loads, for spacing and same-day pairing: running and cycling share the legs, swimming the
# shoulders; lifting depends on its focus.
def tissue(sport,focus=None):
    import starter_programs as S
    if sport=='gym':
        focus=focus or 'full'
        legs=focus in S.LIFT_LEGS;upper=focus in ('full','upper','push','pull','upper_push','upper_pull')
        return ({'legs'} if legs else set())|({'shoulders'} if upper else set())
    return {'run':{'legs','impact'},'ride':{'legs'},'swim':{'shoulders'}}.get(sport,set())


def review_changes(d,phases,start,end):
    import training_block
    old=[p for p in d.get('phase_profiles',[]) if p['end']>start.isoformat()]
    changes=[]
    for i,p in enumerate(phases):
        previous=old[i] if i<len(old) else None
        if not previous or any(previous.get(k)!=p.get(k) for k in ('label','start','end','modes','weights','weekly_pattern','date_placements','color','stage')):
            changes.append({'previous':previous,'proposed':p})
    retained=[];conflicts=[]
    for day,plan in sorted(d.get('plans',{}).items()):
        if not start.isoformat()<=day<end.isoformat():continue
        ss=training_block.sessions(plan)
        if not ss:continue
        retained.append({'date':day,'sessions':len(ss)})
        phase=next((p for p in phases if p['start']<=day<p['end']),None)
        for session in ss:
            if phase and phase.get('modes',{}).get(session.get('sport'))=='pause':conflicts.append({'date':day,'sport':session['sport'],'reason':'Saved workout conflicts with a paused priority'})
    return {'apply_from':start.isoformat(),'phase_changes':changes,'removed_phases':old[len(phases):], 'retained_workout_days':retained,'conflicts':conflicts,'workout_policy':'Existing detailed workouts remain saved. Review conflicts before training; this applies phase intent and tentative placement only.'}


def sessions_for(stage,hours):
    """Sessions a week by stage: about one per 40 available minutes at the peak (2-6), fewer before and after."""
    cap=max(2,min(6,round(hours*60/40)))
    return {'assessment':min(4,cap),'recovery':max(2,cap-3),'base':max(2,cap-2),'build':max(2,cap-1),'peak':cap,
            'specific':max(2,cap-1),'taper':max(2,cap-2)}.get(stage,max(2,cap-1))


def macro_weeks(phases,start,target,focus,sport,restricted,hours,plans=None,options=None):
    """Tentative sport slots only. No sets, minutes, target power, or load clearance."""
    options=validate_options(options or {})
    import starter_programs as S
    split=S.LIFT_SPLITS[options['lift_split']];lift_turn=0;lift_row=0
    result=[];cursor=start;previous_sport=None
    while cursor<target:
        end=min(target,cursor+dt.timedelta(days=7));slots=[]
        for offset in range((end-cursor).days):
            day=cursor+dt.timedelta(days=offset)
            phase=next((p for p in phases if p['start']<=day.isoformat()<p['end']),None)
            if phase is None:
                slots.append({'date':day.isoformat(),'sport':'rest','purpose':'Phase gap — review program','conditional':True});continue
            # Existing prescriptions are authoritative; a macro template cannot replace them.
            import training_block
            scheduled=training_block.sessions((plans or {}).get(day.isoformat()) or {})
            if scheduled:
                for session in scheduled:
                    blocked=session.get('sport')=='run' and restricted
                    slots.append({'date':day.isoformat(),'sport':'rest' if blocked else session['sport'],
                        'purpose':'Running held — review saved session' if blocked else session.get('name') or session.get('note') or 'Scheduled workout',
                        'conditional':blocked,'source':'scheduled'})
                continue
            dated=(phase.get('date_placements') or {}).get(day.isoformat())
            if dated:
                for slot in dated:
                    blocked=slot['sport']=='run' and restricted
                    slots.append({'date':day.isoformat(),'sport':'rest' if blocked else slot['sport'],'purpose':'Running held — no run prescribed' if blocked else slot['purpose'],'conditional':True,'source':'dated placement'})
                continue
            pattern=phase.get('weekly_pattern')
            if pattern:
                chosen=pattern[day.weekday()]
                for slot in chosen if isinstance(chosen,list) else [chosen]:
                    blocked=slot['sport']=='run' and restricted
                    slots.append({'date':day.isoformat(),'sport':'rest' if blocked else slot['sport'],
                        'purpose':'Running held — no run prescribed' if blocked else slot['purpose'],'conditional':True,'source':'phase template'})
                continue
            stage=phase.get('stage',phase['kind'])
            # Capacity to attend is not evidence of physiological capacity: sessions grow with the phase,
            # from a few in the foundation to the most the available time supports at the peak.
            count=sessions_for(stage,hours)
            if stage=='build' and (P.date(phase['end'])-cursor).days<=14:
                count=sessions_for('peak',hours)     # the last development weeks carry the most sessions: peak volume
            available=[s for s in P.SPORTS if phase.get('modes',{}).get(s)!='pause' and (s!='run' or not restricted)]
            if not available:
                slots.append({'date':day.isoformat(),'sport':'rest','purpose':'Rest / paused sports','conditional':False});continue
            priority=options['first_sport'] if options['first_sport'] in available else focus if focus in available else sport if sport in available else available[0]
            sequence=[priority]+[s for s in available if s!=priority]
            weights={s:phase.get('weights',{}).get(s,2 if phase.get('modes',{}).get(s)=='improve' else 1) for s in available}
            allowed=[i for i in range((end-cursor).days) if (cursor+dt.timedelta(days=i)).weekday() in options['available_days'] and (cursor+dt.timedelta(days=i)).weekday() not in options['rest_days']]
            count=min(count,len(allowed))
            active_days=sorted(set(allowed[round(j*(len(allowed)-1)/max(1,count-1))] for j in range(count))) if count else []
            if offset in active_days:
                used={s:sum(x['sport']==s for x in slots) for s in available}
                rank=sorted(sequence,key=lambda s:(used[s]/weights[s],s==previous_sport,sequence.index(s)))
                yesterday=previous_sport if offset>0 and offset-1 in active_days else None
                def spaced(s):
                    # Runs never back to back in a starter (the block decides beyond that); full-body lifting needs
                    # 48 h; a split rotates focuses up to the athlete's limit of lifting days in a row. Swims and rides
                    # may repeat on consecutive days.
                    if s=='run':return yesterday!='run'
                    if s=='gym':return yesterday!='gym' if split==['full'] else not (yesterday=='gym' and lift_row>=options['max_lift_days_in_row'])
                    return True
                session=next((s for s in rank if spaced(s)),None)
                if session is None:
                    slots.append({'date':day.isoformat(),'sport':'rest','purpose':'Separate repeated exposures; review tolerance','conditional':True});continue
                slot={'date':day.isoformat(),'sport':session,'purpose':'Assessment / familiarization' if stage=='assessment' else phase['label'],'conditional':True,'source':'suggested','stage':stage}
                if session=='gym':
                    slot['lift_focus']=split[lift_turn%len(split)];lift_turn+=1
                    lift_row=lift_row+1 if yesterday=='gym' else 1
                else:lift_row=0
                slots.append(slot)
                previous_sport=session
                if options['allow_doubles'] and hours>=6 and stage in ('build','specific') and len(available)>1 and active_days.index(offset)==len(active_days)-1:
                    # a second session only if it loads different tissue (swim with a run, a ride with upper-body
                    # lifting); strength goes first when it is the priority, otherwise six hours apart if possible
                    first=tissue(session,slot.get('lift_focus'))
                    second=next((s for s in rank if s!=session and s!='run' and not (tissue(s,split[lift_turn%len(split)] if s=='gym' else None)&first)),None)
                    if second:
                        extra={'date':day.isoformat(),'sport':second,'purpose':'Optional second session — different tissue; six hours apart if you can','conditional':True,'source':'suggested'}
                        if second=='gym':extra['lift_focus']=split[lift_turn%len(split)];lift_turn+=1
                        if 'gym' in (second,session) and priority=='gym' and second=='gym':slots.insert(len(slots)-1,extra)
                        else:slots.append(extra)
            else:slots.append({'date':day.isoformat(),'sport':'rest','purpose':'Rest / open day','conditional':False,'stage':stage})
        result.append({'start':cursor.isoformat(),'end':end.isoformat(),'slots':slots,'running':'On hold — no running slots prescribed' if restricted else 'Recheck readiness before prescribing running','phase':next((copy.deepcopy(p) for p in phases if p['start']<=cursor.isoformat()<p['end']),None),'status':'Proposed placement; detailed dose requires review'})
        cursor=end
    return result
