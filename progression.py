"""Contextual coaching decisions, not injury diagnoses or validated biological cutoffs.

Compare whole-program forecasts before a bounded duration change. Never add sessions
or clear running automatically. Retain symptoms independently of recovery-curve calibration.
"""
import copy
import datetime as dt
import hashlib
import json

LOCATIONS = {
    'achilles': ['calves'], 'calf_belly': ['calves'], 'below_knee': ['quads', 'calves'],
    'behind_knee': ['hamstrings', 'calves'], 'hamstring': ['hamstrings'],
    'shoulder': ['shoulders', 'scapula'], 'lower_back': ['lower_back', 'trunk'],
}


def fingerprint(session):
    return hashlib.sha256(json.dumps(session,sort_keys=True).encode()).hexdigest()


def enable(d):
    import training_block as B
    b=d.get('training_block') or {}
    if b.get('status')!='active': raise ValueError('An active block is required')
    if b.get('progression',{}).get('enabled'):return b['progression']
    b['progression']={'enabled':True,'step_minutes':5,'max_weekly_fraction':.05,
        'sport_phases':{'run':'recovery','gym':'recovery','swim':'base','ride':'base'},
        'applied':{},'increased_weeks':[],
        'scheduled':{date:copy.deepcopy(B.sessions(p)) for date,p in d.get('plans',{}).items() if date>=b['start']},
        'meaning':'Reports are interpreted against purpose, phase, event timing and delayed response. Compare full-program loads before changing one session. No automatic extra sessions, running progression or lifting progression. Cutoffs are provisional coaching policy.'}
    return b['progression']


def context(d,date,sport,session=None):
    import programming,training_block as B
    day=dt.date.fromisoformat(date);session=session or {}
    events=[e for e in d.get('events',[]) if e.get('kind') in ('race','test') and 0<=(dt.date.fromisoformat(e['date'])-day).days<=7]
    if events:
        event=min(events,key=lambda e:e['date'])
        return {'phase':'taper','purpose':'event preparation','why':'Preserve freshness for '+event['name']+' on '+event['date']}
    b=d.get('training_block') or {};phase=None
    if b.get('start') and b['start']<=date<(B.monday(b['start'])+dt.timedelta(weeks=b.get('weeks',1))).isoformat():
        phase=(b.get('progression') or {}).get('sport_phases',{}).get(sport)
        if B.monday(day)==B.monday(b['start'])+dt.timedelta(weeks=b.get('weeks',1)-1):phase='recovery'
    phase=phase or programming.phase(d,day)['phase']
    import phaseblend
    intent=phaseblend.resolve(d,date)['sports'].get(sport)
    if intent:
        if phase not in ('taper','recovery'):phase=intent['phase']
        if intent['role'] in ('maintain','pause','recover'):
            return {'phase':phase,'purpose':intent['role'],'why':'; '.join(intent['why'])}
    text=(session.get('name','')+' '+session.get('note','')).lower()
    purpose='recovery' if any(w in text for w in ('recovery','restorative')) else 'technique' if 'technique' in text else 'aerobic'
    return {'phase':phase,'purpose':purpose,'why':'Saved sport phase and session purpose'}


def report(d,date,index,fields,done,today):
    import training_block as B
    dt.date.fromisoformat(date)
    if date>today:raise ValueError('Report a completed session, not a future workout')
    ss=B.sessions(d.get('plans',{}).get(date) or {})
    if not 0<=index<len(ss):raise ValueError('Choose a scheduled session')
    session=ss[index];sport=session['sport']
    import coach
    marked=coach.attach_completions(d,date,copy.deepcopy(ss),copy.deepcopy(done.get(date,[])))
    completion=marked[index].get('completion')
    if not completion:raise ValueError('Import or log the completed workout before reporting effort')
    effort=fields.get('effort')
    if effort not in ('too_easy','as_intended','too_hard'):raise ValueError('effort is too_easy, as_intended or too_hard')
    rpe=fields.get('rpe')
    if rpe is not None and (isinstance(rpe,bool) or not isinstance(rpe,(int,float)) or not 0<=rpe<=10):raise ValueError('RPE is 0–10')
    symptoms=fields.get('symptoms') or []
    if not isinstance(symptoms,list):raise ValueError('symptoms must be a list')
    cleaned=[]
    for x in symptoms:
        if not isinstance(x,dict) or x.get('location') not in LOCATIONS or x.get('side') not in ('left','right','both','unspecified'):
            raise ValueError('Choose a recognized symptom location and side')
        severity=x.get('severity')
        if isinstance(severity,bool) or not isinstance(severity,(int,float)) or not 0<=severity<=10:raise ValueError('Symptom severity is 0–10')
        cleaned.append({'location':x['location'],'side':x['side'],'severity':severity,'regions':LOCATIONS[x['location']]})
    hr=fields.get('heart_rate_issue',False)
    if not isinstance(hr,bool):raise ValueError('heart_rate_issue must be true or false')
    key=date+':'+str(index);old=d.get('training_feedback',{}).get(key) or {}
    if old and not d.get('progression_symptom_reviews',{}).get(key):
        for prior in old.get('symptoms',[]):
            if prior['severity']>0 and not any(x['location']==prior['location'] and x['side']==prior['side'] and x['severity']>0 for x in cleaned):
                cleaned.append(copy.deepcopy(prior))
    elif any(x['severity']>0 for x in cleaned):
        d.get('progression_symptom_reviews',{}).pop(key,None)
    entry={'date':date,'session_index':index,'sport':sport,'session_name':session.get('name'),
        'planned_minutes':session.get('minutes',0),'effort':effort,'rpe':rpe,'symptoms':cleaned,
        'heart_rate_issue':hr,'note':str(fields.get('note') or '')[:1000],
        'actual_minutes':completion.get('minutes'),'context':context(d,date,sport,session)}
    if old:
        d.setdefault('feedback_edits',[]).append(copy.deepcopy(old))
        if old.get('adapted'):entry['adapted']=old['adapted']
    d.setdefault('training_feedback',{})[key]=entry
    return entry


def feedback(d,e):
    phase=e['context']['phase'];purpose=e['context']['purpose'];effort=e['effort']
    if any(x['severity']>0 for x in e.get('symptoms',[])):
        decision='regression_candidate';why='Localized discomfort: stop progression of affected work and compare unloading alternatives. Location does not establish a diagnosis.'
    elif e.get('heart_rate_issue') or effort=='too_hard':
        decision='regression_candidate';why='Cost exceeded the intention: compare a shorter or easier session and rest; review diagnostic baseline, conditions and next-day response.'
    elif effort=='too_easy' and (phase in ('recovery','taper') or purpose in ('recovery','technique','maintain','pause','recover')):
        decision='purpose_met';why='Easy meets this session’s purpose. '+e['context']['why']+'; retain the intended dose.'
    elif effort=='too_easy' and phase in ('base','build'):
        decision='progression_candidate';why='Consider a small change to the next scheduled session after delayed-response and full-program load checks.'
    else:
        decision='purpose_met';why='Report supports the intended dose. Retain the plan and check subsequent recovery.'
    return {'decision':decision,'why':why,'phase':phase,'purpose':purpose,
        'conditioning_note':'Conditioning is a 42-day weighted load average; a lower score during reduced training does not directly measure lost fitness.'}


def active_symptoms(d,today):
    """An unresolved location remains a restriction until explicitly reviewed, not timed away."""
    resolved=(d.get('progression_symptom_reviews') or {})
    found=[]
    for key,e in d.get('training_feedback',{}).items():
        if e['date']>today or resolved.get(key):continue
        for x in e.get('symptoms',[]):
            if x['severity']>0:found.append({**x,'report_key':key,'date':e['date']})
    return found


def affected(session,symptoms):
    import bodymap,lifting
    sport={'ride':'bike'}.get(session['sport'],session['sport'])
    regions=set(r for x in symptoms for r in x['regions'])
    if sport=='gym':
        if not session.get('lifts'):return bool(regions) # unknown prescription cannot establish avoidance
        used={r for lift in session['lifts'] for r,v in (lift.get('regions') or {}).items() if v>0}
        return bool(used.intersection(regions))
    return any(bodymap.REGIONS.get(r,('',{}))[1].get(sport,0)>=.2 for r in regions)


def _resize(session,minutes):
    import re
    s=copy.deepcopy(session);delta=minutes-s['minutes']
    if s.get('workout') or s.get('test') or s['sport'] not in ('ride','swim'):return None
    text=s.get('steps') or []
    ids=[i for i,x in enumerate(text) if re.match(r'^\d+(?:\.\d+)? min',x) and any(w in x.lower() for w in ('aerobic','endurance'))]
    if not ids:return None
    i=ids[0];value=float(text[i].split()[0])+delta
    if value<=0:return None
    if s.get('bike_plan'):
        steps=s['bike_plan']['power_steps']
        if len(steps)<3 or steps[1]['minutes']+delta<=0:return None
        steps[1]['minutes']+=delta
    text[i]=re.sub(r'^\d+(?:\.\d+)?',f'{value:g}',text[i]);s['minutes']=minutes
    return s


def _easier(session):
    s=copy.deepcopy(session)
    if s.get('workout') or s.get('test'):return None
    if s.get('bike_plan'):
        for step in s['bike_plan']['power_steps']:
            for key in ('watts','pct'):
                if key in step:step[key]=round(step[key]*.9,2)
        s['steps']=['Follow saved power stages, reduced by 10%; keep effort comfortable.']
        return s
    return None # never pretend changing a label changes the dose



def _lifting_regression(session,symptoms):
    """Preserve specified unaffected lifts, or reduce sets when effort exceeded intention."""
    if session['sport']!='gym' or not session.get('lifts'):return None
    lifts=session['lifts']
    if any(not x.get('regions') or not x.get('kind') for x in lifts):return None
    regions={r for x in symptoms for r in x['regions']}
    if regions:
        remaining=[copy.deepcopy(x) for x in lifts if not regions.intersection(r for r,v in x['regions'].items() if v>0)]
        if not remaining or len(remaining)==len(lifts):return None
    else:
        if not any(x['sets']>1 for x in lifts):return None
        remaining=copy.deepcopy(lifts)
        for x in remaining:x['sets']=max(1,x['sets']//2)
    import lifting
    s=copy.deepcopy(session);s['lifts']=remaining
    s['minutes']=min(s['minutes'],lifting.estimate_minutes([{'seconds':None,'reps':None,'per_side':False,'tempo':None,**x} for x in remaining]))
    s['name']='Reduced strength: '+s.get('name','Strength')
    s['steps']=[f"{x['name']}: {x['sets']} set(s), "+str(x.get('reps') or x.get('seconds'))+(' reps' if x.get('reps') else ' seconds') for x in remaining]
    s['note']='Affected movements omitted; no replacement load added.' if regions else 'Fewer prescribed sets; retain comfortable resistance and technique.'
    return s


def _summary(forecast):
    keys=('cardio_fatigue','cardio_conditioning','muscle_fatigue','run_mechanical','run_recent','swim_recovery','strength')
    result={}
    for key in keys:
        values=[m['after'] for f in forecast.values() for m in f['metrics'] if m['key']==key]
        result[key]={'peak':max(values) if values and all(v is not None for v in values) else None,
                     'end':values[-1] if values else None}
    return result


def compare(d,today,date,index,load,done=None,workouts=None,trigger=None):
    """Keep / shorten / easier / unload / extend; evaluate the entire affected week and one beyond."""
    import coach,training_block as B,bodymap
    session=B.sessions(d['plans'].get(date) or {})[index]
    if date<=today:raise ValueError('Only future sessions can be revised')
    if (dt.date.fromisoformat(date)-dt.date.fromisoformat(today)).days>21:raise ValueError('Compare changes within the next 21 days')
    end=min(B.monday(date)+dt.timedelta(days=13),dt.date.fromisoformat(today)+dt.timedelta(days=21))
    dates=[(dt.date.fromisoformat(today)+dt.timedelta(days=j)).isoformat() for j in range(1,(end-dt.date.fromisoformat(today)).days+1)]
    baseline=B.projected_loads(d,today,dates,load,done,workouts);summary=_summary(baseline)
    symptoms=active_symptoms(d,today);local=affected(session,symptoms)
    c=(d.get('checkins') or {}).get(today) or {};verdict,hr_reasons=coach.verdict(d,today)
    cx=context(d,date,session['sport'],session)
    proposed=[('keep',copy.deepcopy(session))]
    reduced_lifts=_lifting_regression(session,symptoms if local else [])
    if reduced_lifts:proposed.append(('unload_regions' if local else 'fewer_sets',reduced_lifts))
    shortened=_resize(session,max(15,session['minutes']-max(5,round(session['minutes']*.2/5)*5)))
    if shortened:proposed.append(('shorter',shortened))
    easier=_easier(session)
    if easier:proposed.append(('easier',easier))
    proposed.append(('unload',{'sport':'rest','minutes':0,'name':'Recovery review instead of '+session.get('name',session['sport']),
                              'steps':[],'note':'Review symptoms and comfortable alternatives with the coach. No automatic exercise substitution.'}))
    longer=_resize(session,session.get('minutes',0)+5)
    if longer:proposed.append(('extend',longer))
    policy=(d.get('training_block') or {}).get('progression') or {}
    candidates=[]
    for action,replacement in proposed:
        reasons=[];candidate=copy.deepcopy(d);ss=copy.deepcopy(B.sessions(candidate['plans'][date]));ss[index]=replacement
        coach.set_sessions(candidate,date,ss,_trusted=True)
        projected=baseline if action=='keep' else B.projected_loads(candidate,today,dates,load,done,workouts)
        values=_summary(projected)
        if local and action not in ('unload','unload_regions'):reasons.append('Unresolved localized discomfort overlaps this session')
        if action=='extend':
            if session['sport'] not in ('ride','swim'):reasons.append('Running and lifting progression need a coach-reviewed prescription')
            if cx['phase'] not in ('base','build') or cx['purpose']!='aerobic':reasons.append('Purpose or phase calls for preserving the dose')
            if context(d,today,session['sport'],session)['phase']=='taper':reasons.append('An upcoming event protects freshness')
            if verdict in ('easy','rest'):reasons.extend(hr_reasons)
            if B.monday(date).isoformat() in policy.get('increased_weeks',[]):reasons.append('This week already received a duration increase')
            if 5>B._week(d,B.monday(date))['total_minutes']*policy.get('max_weekly_fraction',.05):reasons.append('Increase exceeds the provisional small-step ceiling')
            if not trigger or feedback(d,trigger)['decision']!='progression_candidate':reasons.append('No qualifying easy-session report')
            else:
                k='shoulders' if session['sport']=='swim' else 'legs'
                if trigger['date']>=today or c.get(k) is None or c[k]>4 or c.get('legs',0)>4 or c.get('breathing',0)>4:
                    reasons.append('Mild dated follow-up response is missing')
                if (trigger.get('actual_minutes') or 0)<.8*trigger.get('planned_minutes',1):reasons.append('The prescribed dose was not sufficiently completed')
            required=['cardio_fatigue','cardio_conditioning','muscle_fatigue','strength']
            if session['sport']=='swim':required.append('swim_recovery')
            if any(values[k]['peak'] is None for k in required):reasons.append('Unknown dose or future regional state: complete workout prescriptions')
            for f in projected.values():
                for m in f['metrics']:
                    if (m['key']=='swim_recovery' and session['sport']=='swim' or m['key'].startswith('lift_')) and m.get('limit') is not None and m.get('after') is not None and m['after']>=m['limit']:
                        reasons.append('Projected '+m['name']+' reaches its planning limit')
                region=f.get('regional_overlap') or {}
                if region.get('unavailable_sources'):reasons.append('Future regional overlap contains unknown sources')
                notes=bodymap.overlap_advice(region,{'ride':'bike'}.get(session['sport'],session['sport']))
                if notes:reasons.extend(notes)
            muscle=(load.get('systems') or {}).get('muscle') or {}
            if policy.get('sport_phases',{}).get('run')=='recovery' and values['muscle_fatigue']['end'] is not None and muscle.get('fatigue') is not None and values['muscle_fatigue']['end']>muscle['fatigue']:
                reasons.append('Extra work reverses the desired leg-load decline')
        if session['sport']=='run' and action!='unload' and B.running_gate(d,load,c)['status']!='open_for_review':
            reasons.append('Existing running gate remains closed')
        deltas={k:None if values[k]['end'] is None or summary[k]['end'] is None else round(values[k]['end']-summary[k]['end'],2) for k in summary}
        candidates.append({'action':action,'eligible':not reasons,'reasons':list(dict.fromkeys(reasons)),
                           'replacement':replacement,'forecast':values,'end_delta':deltas})
    run_hold=session['sport']=='run' and B.running_gate(d,load,c)['status']!='open_for_review'
    regression=local or run_hold or trigger and feedback(d,trigger)['decision']=='regression_candidate' or verdict in ('easy','rest')
    priority=['unload'] if run_hold or verdict=='rest' else ['unload_regions','unload'] if local else ['fewer_sets','shorter','easier','unload','keep'] if regression else ['extend','keep']
    chosen=next((x for action in priority for x in candidates if x['action']==action and x['eligible']),None)
    return {'date':date,'session_index':index,'sport':session['sport'],'original':copy.deepcopy(session),
            'fingerprint':fingerprint(session),'context':cx,'baseline':summary,'candidates':candidates,
            'selected':chosen['action'] if chosen else None,'symptoms':symptoms,
            'why':('Running remains held by its existing mechanical and response gates' if run_hold else 'Unload affected work and review localized discomfort' if local else 'Reduce demand in response to reported or diagnostic cost' if regression else 'Use the smallest eligible progression; otherwise retain the session'),
            'evidence':'Scenario estimates and provisional coaching rules; not injury prediction or proof of optimal training.'}


def apply(d,decision,today,load,done=None,workouts=None):
    """Re-evaluate immediately before applying; preserve manual edits and complete history."""
    import coach,training_block as B
    date=decision['date'];index=decision['session_index'];old=B.sessions(d['plans'][date])[index]
    if fingerprint(old)!=decision['fingerprint']:raise ValueError('Session changed since comparison; re-evaluate it')
    trigger=decision.get('trigger')
    current=compare(d,today,date,index,load,done,workouts,trigger)
    if current['selected']!=decision['selected']:raise ValueError('Evidence changed; compare again before applying')
    chosen=next((x for x in current['candidates'] if x['action']==current['selected']),None)
    if not chosen or not chosen['eligible']:raise ValueError('No eligible decision')
    if chosen['action']!='keep':
        ss=copy.deepcopy(B.sessions(d['plans'][date]));ss[index]=chosen['replacement'];coach.set_sessions(d,date,ss,_trusted=True)
        policy=d['training_block']['progression'];policy['scheduled'][date]=copy.deepcopy(B.sessions(d['plans'][date]))
        if chosen['action']=='extend':policy['increased_weeks'].append(B.monday(date).isoformat())
    current['applied_at']=today
    d.setdefault('progression_decisions',[]).append(current)
    return current


def daily_adapt(d,today,done,load,workouts=None):
    """At most one bounded change per check-in; reports never fabricate curve calibration."""
    import training_block as B
    policy=(d.get('training_block') or {}).get('progression') or {}
    if not policy.get('enabled'):return []
    entries=sorted(d.get('training_feedback',{}).items(),reverse=True)
    import phaseblend
    blend=phaseblend.resolve(d,today,headline=load.get('headline'))
    if blend['enabled']:
        entries.sort(key=lambda pair:(feedback(d,pair[1])['decision']=='regression_candidate',
            blend['sports'].get(pair[1]['sport'],{}).get('weight',0),pair[0]),reverse=True)
    for key,e in entries:
        e['assessment']=feedback(d,e)
        if e.get('adapted') and not active_symptoms(d,today):continue
        unresolved=any(x['report_key']==key for x in active_symptoms(d,today))
        if e['date']>today or ((dt.date.fromisoformat(today)-dt.date.fromisoformat(e['date'])).days>7 and not unresolved):continue
        if e['assessment']['decision']=='purpose_met':continue
        symptoms=active_symptoms(d,today)
        for date,p in sorted(d.get('plans',{}).items()):
            if not today<date<=(dt.date.fromisoformat(today)+dt.timedelta(days=7)).isoformat():continue
            ss=B.sessions(p)
            if policy.get('scheduled',{}).get(date)!=ss:continue
            for index,s in enumerate(ss):
                if s['sport']=='rest' or not (s['sport']==e['sport'] or affected(s,symptoms)):continue
                if symptoms and not affected(s,symptoms):continue
                result=compare(d,today,date,index,load,done,workouts,e);result['trigger']={k:copy.deepcopy(v) for k,v in e.items() if k not in ('assessment','comparison','adapted')}
                e['comparison']=result
                if result['selected'] in ('keep',None):
                    record=copy.deepcopy(result);record['reviewed_at']=today
                    history=d.setdefault('progression_comparisons',[])
                    if not history or history[-1]!=record:history.append(record)
                if result['selected'] not in ('keep',None):
                    applied=apply(d,result,today,load,done,workouts)
                    e['adapted']={'date':date,'action':applied['selected']};e['assessment']['why']=applied['why']
                    if symptoms:continue
                    return [applied]
        if symptoms:return [x for x in d.get('progression_decisions',[]) if x.get('applied_at')==today and x.get('symptoms')]
    return []


def apply_review(d,sunday,done,load,workouts=None,today=None):
    """Weekly review uses the same comparisons; high response can regress without 'too hard'."""
    today=today or sunday;policy=(d.get('training_block') or {}).get('progression') or {}
    if not policy.get('enabled'):return None
    if sunday in policy['applied']:return policy['applied'][sunday]
    if dt.date.fromisoformat(sunday).weekday()!=6 or sunday>today:raise ValueError('Review belongs to a completed Sunday')
    r=(d.get('weekly') or {}).get(sunday) or {}
    if not r:return {'status':'hold','why':['Weekly response is missing']}
    changes=daily_adapt(d,today,done,load,workouts)
    if not changes:
        import training_block as B
        for date,p in sorted(d.get('plans',{}).items()):
            if not today<date<=(dt.date.fromisoformat(today)+dt.timedelta(days=7)).isoformat():continue
            if policy.get('scheduled',{}).get(date)!=B.sessions(p):continue
            for index,s in enumerate(B.sessions(p)):
                high=r.get('week',0)>=7 or r.get('legs' if s['sport']=='ride' else 'shoulders' if s['sport']=='swim' else 'week',0)>=6
                if not high or s['sport']=='rest':continue
                trigger={'date':sunday,'sport':s['sport'],'effort':'too_hard','context':context(d,sunday,s['sport'],s)}
                x=compare(d,today,date,index,load,done,workouts,trigger);x['trigger']=trigger
                if x['selected'] not in ('keep',None):changes.append(apply(d,x,today,load,done,workouts));break
            if changes:break
    out={'status':changes[0]['selected'] if changes else 'hold','why':[changes[0]['why']] if changes else ['No eligible change; retain baseline and collect completed-session and delayed-response evidence'],
         'changes':changes,'sunday':sunday,'next_start':(dt.date.fromisoformat(sunday)+dt.timedelta(days=1)).isoformat()}
    policy['applied'][sunday]=out
    return out
