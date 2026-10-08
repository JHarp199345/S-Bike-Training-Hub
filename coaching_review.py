"""Read forecasts, compare calendar changes and review capacity; never biological clearance.

Policy thresholds (three observations, two-point report discrepancy, ten-percent
review step) are conservative product heuristics, not research-derived constants.
"""
import copy
import datetime as dt
import json
import secrets
import time
import zlib
import program_drafts

MIN_OBSERVATIONS = 3
REVIEW_STEP = .10


def _rem(load):
    return (((load.get('systems') or {}).get('impact') or {}).get('tissue') or {}).get('remodeling') or {}


def _latest(d, target):
    return next((r for r in reversed(d.get('capacity_adjustments', [])) if r['target']==target), {})


def _prediction(d, date, metric):
    # Use a prediction saved before the workout, never a newly generated historical forecast.
    for record in d.get('load_forecasts', {}).get(date, []):
        if record.get('saved_at', '')[:10] <= date:
            row=next((r for r in record['forecast']['metrics'] if r['key']==metric), {})
            if row.get('after') is not None:return row['after']
    return None


def outlook(d, load, done, workouts, today, days=14):
    import training_block as B, progression
    if not 1 <= days <= 14:raise ValueError('Outlook covers 1–14 days')
    dates=[(dt.date.fromisoformat(today)+dt.timedelta(days=n)).isoformat() for n in range(days)]
    rows=B.projected_loads(d,today,dates,load,done,workouts).values()
    summaries=[];daily=[]
    for row in rows:
        sessions=B.sessions(d.get('plans',{}).get(row['date']) or {})
        if not sessions:continue
        metrics=[{k:m.get(k) for k in ('key','before','after','limit','over_limit','session_dose','unit')} for m in row['metrics']]
        daily.append({'date':row['date'],'readings':metrics})
        run=next((m for m in metrics if m['key']==('run_response' if (load.get('running_response') or {}).get('active') else 'run_mechanical')),{})
        strength=[m for m in metrics if m['key'].startswith('lift_')]
        for i,s in enumerate(sessions):
            if s['sport'] not in ('run','gym'):continue
            selected=[run] if s['sport']=='run' else strength
            unknown=not selected or any(m.get('after') is None for m in selected)
            conflicts=[m for m in selected if m.get('after') is not None and m.get('limit') is not None and m['after']>=m['limit']]
            # a running calibration is a measurement: it ends when tiredness, form or pain says so, and its eight-day
            # watch follows, so the forecast limit doesn't judge it
            test=s['sport']=='run' and (d.get('plans',{}).get(row['date']) or {}).get('test')=='run_calibration'
            summaries.append({'date':row['date'],'index':i,'sport':s['sport'],'name':s.get('name'),'minutes':s.get('minutes'),
                'context':progression.context(d,row['date'],s['sport'],s),'readings':selected,
                'status':'test' if test else 'unknown' if unknown else 'conflict' if conflicts else 'response_review' if s['sport']=='run' and (load.get('running_response') or {}).get('active') else 'within_projected_limits',
                'alternatives':['Shorten or reduce the scheduled dose','Move the exposure and recheck the following week','Replace affected work with an eligible activity or rest'] if conflicts and not test else [],
                'meaning':'Readings include all work on this day; they are not isolated per-session measurements.'})
    gate=B.running_gate(d,load,d.get('checkins',{}).get(today))
    import training_rules
    rules=training_rules.check(d,today,dates[-1])
    return {'as_of':today,'days':days,'sessions':summaries,'daily_readings':daily,'running_gate':gate,'training_rules':rules,
            'active_symptoms':progression.active_symptoms(d,today),
            'running_progression':running_progression(d,load,today,daily,gate),
            'notice':'Check the entire sequence, including openers after peak work. Forecasts do not clear execution holds.'}


# Running load targets, in blocks carried on run days (the 1.5-block line stays the hard limit). Provisional
# product policy (the rider's design, 2026-10-03): when running is building, hold 0.8-1.5 and wave it week to week
# (light, middle, heavy) so the build can last; when running isn't the focus, keep a third of the middle (0.4) for
# maintenance; negative reports deload to 0.4 automatically, then 0.1 if they persist past a week.
RUN_BAND = (0.8, 1.45)
RUN_WAVE = {'light': (0.8, 1.0), 'middle': (1.0, 1.2), 'heavy': (1.2, 1.45)}
RUN_TARGETS = {'assessment': (.4, .8), 'base': (.8, 1.2), 'taper': (.3, .6), 'recovery': (.1, .4),
               'maintain': (.3, .5), 'pause': (0, .1), 'recover': (.1, .4)}
DELOAD, DEEP_DELOAD, RE_ENTRY = (.3, .4), (0, .1), (.8, .9)
DELOAD_DAYS = 7            # at least a week at 0.4, and two clean mornings, before coming back
WEEKLY_RUN_CAP = 1.15      # planned weekly running load may rise at most 15% over the most of the last three weeks
SYMPTOM_STOP_DAYS = 14     # negative reports this long: stop running and get assessed


def run_triggers(d, today):
    """Dates in the last four weeks with a negative running response, and whether any was a whole-body warning."""
    since=(dt.date.fromisoformat(today)-dt.timedelta(days=28)).isoformat()
    hits,whole={},[]
    for e in d.get('training_feedback',{}).values():
        if since<=e.get('date','')<=today and e.get('sport')=='run':
            sore=[x['location'].replace('_',' ') for x in e.get('symptoms',[]) if x.get('severity',0)>0]
            if sore:hits.setdefault(e['date'],[]).append('run report: '+', '.join(sore))
            if e.get('effort')=='too_hard':hits.setdefault(e['date'],[]).append('run felt too hard')
            if e.get('heart_rate_issue'):whole.append(e['date']+': heart-rate issue in run report')
    last_hops=None
    for date,c in sorted(d.get('checkins',{}).items()):
        if date>today:break
        hops=c.get('hops') if c.get('hops') is not None else min([x for x in (c.get('hops_left'),c.get('hops_right')) if x is not None],default=None)
        if date>=since:
            for k in ('legs','feet'):
                if c.get(k) is not None and c[k]>=6:hits.setdefault(date,[]).append(f'{k} {c[k]}/10 in the morning')
            if hops is not None and last_hops is not None and hops<=last_hops-2:hits.setdefault(date,[]).append(f'hop test dropped to {hops}')
            if c.get('breathing') is not None and c['breathing']>=6:whole.append(date+': short of breath')
        if hops is not None:last_hops=hops
    return hits,whole


def deload_state(d, today):
    """Automatic running deload from negative reports: None, or the target and why. Stateless: recomputed from
    the reports each day, so it ends on its own once the athlete reports clean."""
    hits,whole=run_triggers(d,today)
    if not hits:return None
    days=sorted(hits);last=days[-1];first=last
    for x in reversed(days[:-1]):
        if (dt.date.fromisoformat(first)-dt.date.fromisoformat(x)).days<DELOAD_DAYS:first=x
        else:break
    now=dt.date.fromisoformat(today);t=dt.date.fromisoformat(last)
    persisted=(t-dt.date.fromisoformat(first)).days
    clean=[k for k,c in sorted(d.get('checkins',{}).items()) if last<k<=today
           and all(c.get(x) is not None and c[x]<=3 for x in ('feet','legs'))]
    why=[f'{k}: {"; ".join(v)}' for k,v in sorted(hits.items()) if k>=first]
    if (now-t).days<DELOAD_DAYS or len(clean)<2:
        deep=persisted>=DELOAD_DAYS
        return {'status':'deep_deload' if deep else 'deload','target':DEEP_DELOAD if deep else DELOAD,'since':first,'why':why,
                'stop':persisted>=SYMPTOM_STOP_DAYS,'whole_body':whole,
                'ends':'no sooner than '+(t+dt.timedelta(days=DELOAD_DAYS)).isoformat()+', after two clean mornings'}
    exit_day=max(dt.date.fromisoformat(clean[1]),t+dt.timedelta(days=DELOAD_DAYS))
    if (now-exit_day).days<7:
        return {'status':'re_entry','target':RE_ENTRY,'since':exit_day.isoformat(),'why':why,'stop':False,'whole_body':whole,
                'ends':(exit_day+dt.timedelta(days=7)).isoformat()}
    return None


def _wave(d, today):
    goal=d.get('program_goal') or {}
    start=dt.date.fromisoformat(goal['start']) if goal.get('start') else dt.date(2026,1,5)
    now=dt.date.fromisoformat(today)
    week=((now-dt.timedelta(days=now.weekday()))-(start-dt.timedelta(days=start.weekday()))).days//7
    return ('light','middle','heavy')[week%3]


def running_progression(d, load, today, daily, gate):
    """Is the plan challenging running the right amount? The load on the coming week's run days against the target
    for this phase and state (build wave, maintenance, automatic deload), plus the weekly cap on absolute load."""
    import progression, training_block as B
    if (load.get('running_response') or {}).get('active'):
        return {'phase':progression.context(d,today,'run')['phase'],'mode':'reported response',
            'target_blocks':None,'band':None,'planned_week_peak_blocks':None,'planned_week_blocks':None,
            'weekly_cap_blocks':None,'status':'held' if gate.get('status')=='hold' else 'review',
            'advice':'Review recorded exposure, current foot/leg reports, protected checks and conditional response forecasts. Block targets are retired; no personal response threshold is established.'}
    # One calendar week, so the wave's target and the runs it judges agree: the rest of this week through
    # Friday, then next week from the weekend on.
    now=dt.date.fromisoformat(today)
    week_start=now if now.weekday()<=4 else now+dt.timedelta(days=7-now.weekday())
    week_end=(week_start+dt.timedelta(days=6-week_start.weekday())).isoformat()
    judged=week_start.isoformat()
    ctx=progression.context(d,judged,'run');phase=ctx['phase'];purpose=ctx.get('purpose')
    # a running calibration is about one full block on purpose: it isn't judged against the week's target
    run_days={r['date'] for r in daily if judged<=r['date']<=week_end and (d.get('plans',{}).get(r['date']) or {}).get('test')!='run_calibration'
              and any(s['sport']=='run' for s in B.sessions(d.get('plans',{}).get(r['date']) or {}))}
    reading=lambda day:next((m for m in day['readings'] if m['key']=='run_mechanical'),{})
    on_runs=[reading(day).get('after') for day in daily if day['date'] in run_days]
    peak=round(max(on_runs),2) if on_runs and None not in on_runs else None
    planned=sum(reading(day).get('session_dose') or 0 for day in daily if today<=day['date']<=(now+dt.timedelta(days=6)).isoformat())
    rem=_rem(load)
    days=load.get('days') or [];ref=rem.get('reference_points')
    prior=[]
    for w in range(3):
        lo=(dt.date.fromisoformat(today)-dt.timedelta(days=7*(w+1))).isoformat();hi=(dt.date.fromisoformat(today)-dt.timedelta(days=7*w)).isoformat()
        prior.append(sum(x.get('sports',{}).get('run',{}).get('impact',0) for x in days if lo<=x['date']<hi)/ref if ref else 0)
    cap=round(max(prior)*WEEKLY_RUN_CAP,2) if prior and max(prior)>0 else None
    learned=rem.get('block_learning') or []
    deload=deload_state(d,today)
    if deload:mode,band=deload['status'],deload['target']
    elif purpose in RUN_TARGETS and purpose in ('maintain','pause','recover'):mode,band=purpose,RUN_TARGETS[purpose]
    elif phase in RUN_TARGETS:mode,band=phase,RUN_TARGETS[phase]
    else:
        wave=_wave(d,judged);mode,band='build: '+wave+' week',RUN_WAVE[wave]
    out={'phase':phase,'mode':mode,'week':[judged,week_end],'target_blocks':list(band),'band':list(RUN_BAND),'planned_week_peak_blocks':peak,
         'planned_week_blocks':round(planned,2),'weekly_cap_blocks':cap,'prior_weeks_blocks':[round(x,2) for x in prior],
         'block_points':ref,'last_block_change':learned[-1] if learned else None,'deload':deload,'status':None,'advice':None}
    if deload and deload.get('whole_body'):
        out['whole_body_warning']='Shortness of breath or a heart-rate issue was reported: ease ALL training, and if it is unusual or persists, see a doctor. '+'; '.join(deload['whole_body'])
    if deload and deload['stop']:
        out['status']='stop';out['advice']='Negative running reports have persisted for two weeks: stop running and have it assessed before continuing.'
    elif run_hold(gate,today)[0]((dt.date.fromisoformat(today)+dt.timedelta(days=1)).isoformat()) or progression.active_symptoms(d,today):
        out['status']='held';out['advice']='Resolve the running hold or symptoms first; do not add running load.'
    elif peak is None:
        out['status']='no_runs_planned';out['advice']='No runs with a forecast this week.'
    elif peak>band[1]:
        out['status']='over_target'
        out['advice']=(f'Runs this week land at up to {peak} blocks; the {mode} target is {band[0]}-{band[1]}. Shorten or space runs'
                       +(' (automatic deload after negative reports: keep a little easy running for maintenance)' if deload else '')+'.')
    elif peak<band[0]:
        out['status']='under_target'
        out['advice']=(f'Runs this week land at up to {peak} blocks; the {mode} target is {band[0]}-{band[1]}. Lengthen the long run or '
                       'add an easy run at least two days from the others, previewing until it reaches the target. Prefer one '
                       'well-spaced step over several stacked runs.')
    else:
        out['status']='on_target';out['advice']=f'Running is in the {mode} target. Read the responses; the block adapts weekly.'
    if cap is not None and planned>cap:
        out['advice']+=f' The week plans {round(planned,2)} blocks of running, over the weekly cap of {cap} (15% over the last three weeks\' most): spread the increase.'
    return out


def capacity_candidates(d, load, today):
    import lifting, progression, journal
    symptoms=progression.active_symptoms(d,today)
    last_run=_latest(d,'running_block');rem=_rem(load)
    run_events=[]
    for a in sorted(load.get('activities',[]),key=lambda x:x.get('date','')):
        date=a.get('date','')
        if a.get('sport')!='run' or not last_run.get('date','')<date<today:continue
        expected=_prediction(d,date,'run_mechanical')
        if expected is None:continue
        reports=[journal.effective(d.get('checkins',{}).get((dt.date.fromisoformat(date)+dt.timedelta(days=n)).isoformat()) or {}) for n in (1,2)]
        if not all(c.get('feet') is not None and c.get('legs') is not None for c in reports):continue
        feedback=[e for e in d.get('training_feedback',{}).values() if e.get('date')==date and e.get('sport')=='run']
        bad=any(c[k]>=6 for c in reports for k in ('feet','legs')) or any(e.get('heart_rate_issue') or any(x.get('severity',0)>0 for x in e.get('symptoms',[])) for e in feedback)
        clean=all(c[k]<=3 for c in reports for k in ('feet','legs'))
        benchmark=(d.get('benchmarks',{}).get('runs',{}).get(date) or {})
        bad=bad or benchmark.get('pain',False) or any(c.get('hops') is not None and c['hops']<=3 for c in reports)
        graded=benchmark.get('result')=='review_candidate' and benchmark.get('block_after',0)>benchmark.get('block_before',0)
        easy=any(e.get('effort')=='too_easy' and e.get('context',{}).get('phase') in ('base','build') for e in feedback)
        race=any(e.get('kind')=='race' and e.get('sport') in ('run','tri') and e.get('date')==date for e in d.get('events',[]))
        clean=clean and not bad
        direction='decrease' if bad and expected<1.5 else 'increase' if clean and expected>=1.5 and (easy or race or graded) else None
        if graded and clean and not bad:direction='increase'
        if direction:run_events.append({'benchmark':bool(graded),'date':date,'direction':direction,'source':'graded benchmark plus recovery' if graded else 'competition plus recovery' if race else 'completed run plus delayed reports','expected_blocks':expected,'activity_id':a.get('id'),'minutes':a.get('minutes'),'km':a.get('km'),'avg_hr':a.get('avg_hr')})
    lift_events={}
    lift_state=lifting.state(copy.deepcopy(d))
    for log in lift_state['logs']:
        date=log['date']
        if date>=today:continue
        follow=lift_state['followups'].get(date) or {}
        if not (dt.date.fromisoformat(date)+dt.timedelta(days=lifting.FOLLOW_DAYS[0])).isoformat()<=follow.get('date','')<=today:continue
        for region,dose in log.get('regions',{}).items():
            if not dose or date<=_latest(d,'lift_'+region).get('date',''):continue
            predicted=_prediction(d,date,'lift_'+region);observed=follow.get('regions',{}).get(region)
            if predicted is None or observed is None:continue
            expected=lifting._predict(predicted)
            direction='increase' if observed<=3 and expected-observed>=2 else 'decrease' if observed>=6 and observed-expected>=2 else None
            if direction:lift_events.setdefault(region,[]).append({'date':date,'direction':direction,'source':'logged lifting plus regional follow-up','expected_rating':round(expected,1),'reported_rating':observed,'exercises':[{k:x.get(k) for k in ('name','weight','unit','sets','reps','tempo')} for x in log.get('lifts',[]) if region in x.get('regions',{})]})
    candidates=[]
    def append(target,events,reference,blocked):
        # Count dates, not multiple sessions/regions/reports on the same day.
        by_date={x['date']:x for x in events};events=list(by_date.values())[-6:]
        directions={x['direction'] for x in events}
        direction=next(iter(directions)) if len(directions)==1 else None
        enough=(len(events)>=MIN_OBSERVATIONS or target=='running_block' and any(x.get('benchmark') for x in events)) and direction is not None
        candidates.append({'target':target,'reference':reference,'observations':events,'direction':direction,
            'status':'blocked' if blocked else 'review_candidate' if enough and reference else 'more_evidence_needed',
            'reasons':blocked,'suggested_reference':round(reference*(1+REVIEW_STEP if direction=='increase' else 1-REVIEW_STEP),2) if reference and enough and not blocked else None,
            'recommendation':'Review a calibration session or test week when eligible; it may increase, retain or decrease capacity. Do not schedule a benchmark through a hold.'})
    blocked=[]
    current=journal.effective(d.get('checkins',{}).get(today) or {})
    if any(current.get(k) is not None and current[k]>=6 for k in ('feet','legs')) or current.get('hops') is not None and current['hops']<=3 or current.get('gut')=='no':
        blocked.append('Current readiness report does not support running capacity review')
    protected=load.get('run_progression')
    if protected and rem.get('phase')=='plateau':blocked.append('Protected recovery plateau: use the existing 60% review workflow; capacity cannot rescale it here')
    if any(set(s['regions']).intersection(lifting.LEG_REGIONS) for s in symptoms):blocked.append('Unresolved lower-body symptoms')
    if (load.get('running_response') or {}).get('active'):blocked.append('Running blocks retired; review the selected running response model through its MCP protocol')
    append('running_block',run_events,rem.get('reference_points'),blocked)
    regions=(load.get('lifting') or {}).get('regions') or lifting.model(copy.deepcopy(d),dt.date.fromisoformat(today))['regions']
    for region in sorted(set(regions)|set(lift_events)):
        append('lift_'+region,lift_events.get(region,[]),regions.get(region,{}).get('reference'),['Unresolved regional symptoms'] if any(region in s['regions'] for s in symptoms) else [])
    return {'as_of':today,'candidates':candidates,'policy':{'minimum_distinct_dates':MIN_OBSERVATIONS,'review_step_fraction':REVIEW_STEP,'provisional':True},
            'meaning':'A strength estimate is not a recovery-capacity estimate. Competition without delayed recovery evidence cannot grow recovery blocks.'}


def with_capacity(d,load,today,base):
    """Recalculate the affected modeled readings without rewriting any recorded doses."""
    import lifting, loads, damage
    out=copy.deepcopy(load)
    out['lifting']=lifting.model(copy.deepcopy(d),dt.date.fromisoformat(today))
    latest=_latest(d,'running_block')
    if latest and not (out.get('running_response') or {}).get('active'):
        days=out.get('days') or []
        if not days:raise ValueError('Running dose history is unavailable')
        prof=loads.load_profile(base)
        reports=d.get('checkins',{})
        rem=damage.remodeling_response([x['date'] for x in days],[x.get('sports',{}).get('run',{}).get('impact',0) for x in days],
            weight_kg=prof['weight_kg'],feet_reports=reports,walking=loads.walking_inputs(out.get('activities',[]),loads.load_steps(base),prof),
            block=latest['reference'],reviews=(d.get('run_progression') or {}).get('reviews',[]),
            recovery_curve=(d.get('running_recovery_calibration') or {}).get('profile'))
        if not rem:raise ValueError('Running history cannot be recalculated')
        out['systems']['impact']['tissue']['remodeling']=rem
        if out.get('run_progression'):
            import recovery
            out['run_progression']=recovery.status(d,rem,today)
    return out


def run_hold(gate,today):
    """Which dates the current running gate holds runs on, and the projected clear date for a load-only hold.
    A hop test that is due is a precondition the athlete meets on the morning of the run, so it holds only
    today's run. A hold from recent running load alone clears on the model's own projection. Symptoms,
    a failed hop test, readiness and the return-to-run protocol hold every run until reviewed."""
    if gate.get('status')=='open_for_review':return (lambda date:False),None
    reasons=[str(r) for r in gate.get('reasons') or []]
    due=any(r.startswith('hop test first') for r in reasons)
    other=[r for r in reasons if not r.startswith('hop test first')]
    if not other:return (lambda date:due and date==today),None
    if all(r.startswith('mechanical running load') for r in other) and gate.get('model_days') is not None:
        clear_by=(dt.date.fromisoformat(today)+dt.timedelta(days=int(gate['model_days']))).isoformat()
        return (lambda date:date<clear_by or due and date==today),clear_by
    return (lambda date:True),None


def _store(base,payload,revision):
    db=program_drafts.connect(base)
    token=secrets.token_urlsafe(24);expires=time.time()+program_drafts.TTL_SECONDS
    try:
        db.execute('CREATE TABLE IF NOT EXISTS coaching_reviews (id TEXT PRIMARY KEY, revision TEXT, expires REAL, payload BLOB)')
        db.execute('DELETE FROM coaching_reviews WHERE expires < ?',(time.time(),))
        db.execute('INSERT INTO coaching_reviews VALUES (?,?,?,?)',(token,revision,expires,zlib.compress(json.dumps(payload,allow_nan=False).encode())))
        db.execute('DELETE FROM coaching_reviews WHERE id NOT IN (SELECT id FROM coaching_reviews ORDER BY expires DESC LIMIT 8)');db.commit()
    finally:db.close()
    return {**payload,'draft_id':token,'expires_at':dt.datetime.fromtimestamp(expires,dt.timezone.utc).isoformat()}


def preview(d,load,done,workouts,today,base,revision,fields):
    import coach, training_block as B
    candidate=copy.deepcopy(d);kind=fields.get('kind')
    if kind=='capacity':
        target=fields.get('target');row=next((c for c in capacity_candidates(d,load,today)['candidates'] if c['target']==target),None)
        if not row or row['status']!='review_candidate':raise ValueError('Capacity needs repeated matched evidence and no protected restrictions before review')
        record={'target':target,'date':today,'reference':row['suggested_reference'],'before':row['reference'],'direction':row['direction'],'evidence':row['observations'],'note':str(fields.get('note') or '')[:1000]}
        candidate.setdefault('capacity_adjustments',[]).append(record)
        adjusted=with_capacity(candidate,load,today,base)
        payload={'kind':kind,'record':record,'before':outlook(d,load,done,workouts,today),'after':outlook(candidate,adjusted,done,workouts,today),
            'notice':'Capacity is a reviewed estimate. Existing doses, snapshots, plateau reviews and personal minimum waits are retained; forecast changes do not clear running.'}
    elif kind=='calendar':
        changes=fields.get('changes')
        if not isinstance(changes,list) or not 1<=len(changes)<=14:raise ValueError('Give 1–14 day replacements')
        seen=set();originals=[]
        for change in changes:
            date=change['date'];dt.date.fromisoformat(date)
            if not today<=date<=(dt.date.fromisoformat(today)+dt.timedelta(days=13)).isoformat() or date in seen:raise ValueError('Choose distinct dates within the next 14 days')
            if done.get(date):raise ValueError('Completed days cannot be rewritten')
            seen.add(date);originals.append({'date':date,'sessions':copy.deepcopy(B.sessions(d.get('plans',{}).get(date) or {}))})
            coach.set_sessions(candidate,date,change['sessions'])
            candidate['plans'][date].pop('test',None)
        after=outlook(candidate,load,done,workouts,today)
        gate=after['running_gate'];violations=[]
        # A hold from recent running load alone clears on the model's own projection: it blocks runs before that
        # date (later runs still face their forecast). Symptoms, hop tests, readiness or the return-to-run protocol
        # block every run in the window.
        held,clear_by=run_hold(gate,today)
        for row in after['sessions']:
            if row['date'] not in seen:continue
            if row['status'] not in ('within_projected_limits','response_review','test'):violations.append(row['date']+': '+str(row['name'])+' has unknown or excessive projected load')
            if row['sport']=='run' and held(row['date']):violations.append(row['date']+': current running hold remains in force'+(f' (projected to clear {clear_by})' if clear_by else ''))
            if any(__import__('progression').affected(s,[symptom]) for symptom in after['active_symptoms'] for s in B.sessions(candidate['plans'][row['date']])):violations.append(row['date']+': unresolved symptom overlap')
        # Flag newly introduced or worsened limit breaches across all sports, including later days.
        before=outlook(d,load,done,workouts,today)
        prior={(day['date'],m['key']):m for day in before['daily_readings'] for m in day['readings']}
        # Automatic deload: changed runs must sit at or under its target. Weekly cap on absolute running load.
        rp_after=after.get('running_progression') or {};deload=rp_after.get('deload')
        if deload and deload['status'] in ('deload','deep_deload'):
            for day in after['daily_readings']:
                if day['date'] in seen and any(s['sport']=='run' for s in B.sessions(candidate['plans'][day['date']])):
                    m=next((x for x in day['readings'] if x['key']=='run_mechanical'),{})
                    if m.get('after') is not None and m['after']>deload['target'][1]:
                        violations.append(day['date']+f': automatic running deload: runs stay at or under {deload["target"][1]} blocks')
        rp_before=before.get('running_progression') or {}
        cap=rp_after.get('weekly_cap_blocks')
        if cap is not None and rp_after.get('planned_week_blocks',0)>cap and rp_after['planned_week_blocks']>rp_before.get('planned_week_blocks',0)+.005:
            violations.append(today+f': weekly running load {rp_after["planned_week_blocks"]} blocks is over the cap of {cap}')
        for day in after['daily_readings']:
            for m in day['readings']:
                # The combined utilization reading is advisory: its block parts (running, swim, each lifting region)
                # are checked on their own rows, and growth over the usual week is governed by the running targets,
                # deloads and the weekly cap.
                if m['key']=='mechanical':continue
                old=prior.get((day['date'],m['key']),{})
                if m.get('after') is not None and m.get('limit') is not None and m['after']>=m['limit'] and (old.get('after') is None or m['after']>old['after']+.005):
                    violations.append(day['date']+': worsened '+m['key']+' forecast limit')
        for row in after['sessions']:
            if row['status']=='conflict':violations.append(row['date']+': remaining '+str(row['name'])+' conflict in reviewed sequence')
        # Training rules: a change may not introduce a pattern that breaks one; cautions are listed to weigh.
        had={(f['rule'],tuple(f['dates'])) for f in before.get('training_rules',[])}
        for f in after.get('training_rules',[]):
            if f['severity']=='breaks' and (f['rule'],tuple(f['dates'])) not in had and any(x in seen for x in f['dates']):
                violations.append(f['dates'][-1]+': training rule '+f['rule']+' - '+f['why'])
        payload={'kind':kind,'changes' :[{'date':c['date'],'sessions':copy.deepcopy(B.sessions(candidate['plans'][c['date']]))} for c in changes],'original':originals,
            'before':before,'after':after,'violations':sorted(set(violations)),
            'cautions':[f for f in after.get('training_rules',[]) if f['severity']=='caution' and any(x in seen for x in f['dates'])]
                +[{'rule':'test_day_changed','severity':'caution','dates':[o['date']],
                   'why':'This day holds a scheduled test ('+str((d.get('plans',{}).get(o['date']) or {}).get('test'))+'): replacing its sessions removes the test.'}
                  for o in originals if (d.get('plans',{}).get(o['date']) or {}).get('test')],
            'notice':'Review the whole 14-day sequence. Holds, unknown loads and symptom overlap block Apply; compare shortening, spacing, substitutions or rest.'}
    else:raise ValueError('Review kind is calendar or capacity')
    return _store(base,payload,revision)


def apply(d,base,revision,today,draft_id,approved):
    import coach
    if approved is not True:raise ValueError('Explicit athlete approval is required')
    db=program_drafts.connect(base)
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS coaching_reviews (id TEXT PRIMARY KEY, revision TEXT, expires REAL, payload BLOB)')
        row=db.execute('SELECT revision,expires,payload FROM coaching_reviews WHERE id=?',(draft_id,)).fetchone()
        if not row:raise program_drafts.Conflict('Review unavailable; preview again')
        payload=json.loads(zlib.decompress(row[2]))
        receipt=next((r for r in d.get('coaching_review_receipts',[]) if r['draft_id']==draft_id),None)
        if receipt:db.commit();return {**receipt,'already_applied':True}
        if row[1]<time.time() or row[0]!=revision:raise program_drafts.Conflict('Review expired or athlete data changed; preview again')
        if payload.get('violations'):raise ValueError('Resolve forecast, hold and symptom violations before applying')
        if payload['kind']=='calendar':
            for c in payload['changes']:
                coach.set_sessions(d,c['date'],c['sessions'])
                d['plans'][c['date']].pop('test',None)
        else:d.setdefault('capacity_adjustments',[]).append(copy.deepcopy(payload['record']))
        receipt={'draft_id':draft_id,'kind':payload['kind'],'date':today,'proposal_hash':program_drafts.digest(payload)}
        d['coaching_review_receipts']=(d.get('coaching_review_receipts',[])+[receipt])[-8:]
        coach.save(d);db.commit()
        return {**receipt,'already_applied':False,'verify':'Re-read coaching review outlook and saved calendar; no running clearance was issued.'}
    except Exception:db.rollback();raise
    finally:db.close()
